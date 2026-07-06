"""Gated high-end specialist model experiments."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import TimeSeriesSplit

from estate_value_index.analytics.market_normalized_target import (
    DEFAULT_BLEND_WEIGHTS,
    DEFAULT_DATA_FILE,
    _fit_market_normalized_predictions,
    _market_index,
    _metric_delta,
    blend_market_predictions,
    denormalize_market_predictions,
    market_index_reference,
    normalize_prices_to_market_index,
    select_best_market_blend_weight,
)
from estate_value_index.analytics.residual_calibration import (
    _compare_groups,
    _fit_base_model,
    _fmt_pct,
    _fmt_sek,
    _load_temporal_raw_split,
    _prediction_metrics,
    _prepare_matrices,
    _prepare_model_data,
    _price_band,
    _train_lgbm,
)
from estate_value_index.utils.settings import get_random_state

DEFAULT_OUTPUT_DIR = Path("reports/specialist_experiments")
DEFAULT_SPECIALIST_MIN_PRICE = 8_000_000.0
DEFAULT_GATE_PREDICTION_MIN = 8_000_000.0
DEFAULT_GATE_COMP_VALUE_MIN = 9_000_000.0
DEFAULT_GATE_LUXURY_SCORE_MIN = 0.60
DEFAULT_GATE_MIN_LIVING_AREA = 55.0
HIGH_END_REPORT_PRICE = 12_000_000.0


@dataclass(frozen=True)
class SpecialistFit:
    predictions: np.ndarray
    reference_index: float
    train_rows: int
    fallback_prediction_rows: int


def run_specialist_experiment(
    *,
    data_file: Path | None = None,
    feature_set: str = "no_list_price_h3_market_luxury",
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    n_splits: int = 4,
    random_state: int | None = None,
    specialist_min_price: float = DEFAULT_SPECIALIST_MIN_PRICE,
    gate_prediction_min: float = DEFAULT_GATE_PREDICTION_MIN,
    gate_comp_value_min: float = DEFAULT_GATE_COMP_VALUE_MIN,
    gate_luxury_score_min: float = DEFAULT_GATE_LUXURY_SCORE_MIN,
    gate_min_living_area: float = DEFAULT_GATE_MIN_LIVING_AREA,
) -> dict[str, object]:
    """Train a global market-normalized model plus a gated high-end specialist."""
    if n_splits < 2:
        raise ValueError("n_splits must be at least 2")

    seed = get_random_state() if random_state is None else random_state
    raw_train, raw_test = _load_temporal_raw_split(data_file, feature_set)
    prepared = _prepare_model_data(raw_train, raw_test, feature_set)

    base_fit = _fit_base_model(prepared, seed)
    normalized_fit = _fit_market_normalized_predictions(
        prepared,
        seed,
        fallback_predictions=base_fit.predictions,
    )
    specialist_fit = _fit_specialist_predictions(
        prepared,
        seed,
        specialist_min_price=specialist_min_price,
        fallback_predictions=normalized_fit.predictions,
    )

    oof = _build_oof_training_data(
        raw_train,
        feature_set=feature_set,
        n_splits=n_splits,
        random_state=seed,
        specialist_min_price=specialist_min_price,
    )
    global_blend_selection = select_best_market_blend_weight(
        oof["actual_price"].to_numpy(),
        oof["base_prediction"].to_numpy(),
        oof["normalized_prediction"].to_numpy(),
    )
    oof_global_blend = blend_market_predictions(
        oof["base_prediction"].to_numpy(),
        oof["normalized_prediction"].to_numpy(),
        normalized_weight=global_blend_selection["normalized_weight"],
    )
    oof_gate = build_specialist_gate(
        oof,
        oof_global_blend,
        prediction_min=gate_prediction_min,
        comp_value_min=gate_comp_value_min,
        luxury_score_min=gate_luxury_score_min,
        min_living_area=gate_min_living_area,
    )
    specialist_selection = select_best_specialist_weight(
        oof["actual_price"].to_numpy(),
        oof_global_blend,
        oof["specialist_prediction"].to_numpy(),
        oof_gate,
    )

    global_blend = blend_market_predictions(
        base_fit.predictions,
        normalized_fit.predictions,
        normalized_weight=global_blend_selection["normalized_weight"],
    )
    test_frame = prepared.test_engineered.reset_index(drop=True)
    test_gate = build_specialist_gate(
        test_frame,
        global_blend,
        prediction_min=gate_prediction_min,
        comp_value_min=gate_comp_value_min,
        luxury_score_min=gate_luxury_score_min,
        min_living_area=gate_min_living_area,
    )
    specialist_blend = apply_gated_specialist_predictions(
        global_blend,
        specialist_fit.predictions,
        test_gate,
        specialist_weight=specialist_selection["specialist_weight"],
    )

    result = _build_result_payload(
        feature_set=feature_set,
        data_file=data_file or DEFAULT_DATA_FILE,
        raw_train=raw_train,
        raw_test=raw_test,
        test_frame=test_frame,
        global_predictions=global_blend,
        specialist_predictions=specialist_fit.predictions,
        specialist_blend_predictions=specialist_blend,
        test_gate=test_gate,
        global_blend_selection=global_blend_selection,
        specialist_selection=specialist_selection,
        specialist_fit=specialist_fit,
        oof=oof,
        oof_gate=oof_gate,
        n_splits=n_splits,
        specialist_min_price=specialist_min_price,
        gate_prediction_min=gate_prediction_min,
        gate_comp_value_min=gate_comp_value_min,
        gate_luxury_score_min=gate_luxury_score_min,
        gate_min_living_area=gate_min_living_area,
    )
    _write_outputs(result, output_dir)
    return result


def build_specialist_gate(
    frame: pd.DataFrame,
    global_predictions: np.ndarray,
    *,
    prediction_min: float = DEFAULT_GATE_PREDICTION_MIN,
    comp_value_min: float = DEFAULT_GATE_COMP_VALUE_MIN,
    luxury_score_min: float = DEFAULT_GATE_LUXURY_SCORE_MIN,
    min_living_area: float = DEFAULT_GATE_MIN_LIVING_AREA,
) -> np.ndarray:
    """Flag rows where an inference-safe high-end specialist may be useful."""
    global_pred = np.asarray(global_predictions, dtype=float)
    living_area = pd.to_numeric(frame.get("living_area"), errors="coerce").fillna(0.0)
    comp_ppsqm = pd.to_numeric(frame.get("same_size_ppsqm_median"), errors="coerce")
    fallback_ppsqm = pd.to_numeric(frame.get("micro_area_ppsqm_median"), errors="coerce")
    comp_ppsqm = comp_ppsqm.fillna(fallback_ppsqm).fillna(0.0)
    comp_value = comp_ppsqm.to_numpy(dtype=float) * living_area.to_numpy(dtype=float)

    if "micro_luxury_score" in frame.columns:
        luxury_score = pd.to_numeric(frame["micro_luxury_score"], errors="coerce").fillna(0.0)
    else:
        luxury_score = pd.Series(0.0, index=frame.index)

    return (
        (global_pred >= prediction_min)
        | (comp_value >= comp_value_min)
        | (
            (luxury_score.to_numpy(dtype=float) >= luxury_score_min)
            & (living_area.to_numpy(dtype=float) >= min_living_area)
        )
    )


def apply_gated_specialist_predictions(
    global_predictions: np.ndarray,
    specialist_predictions: np.ndarray,
    gate: np.ndarray,
    *,
    specialist_weight: float,
) -> np.ndarray:
    """Blend specialist predictions only for rows selected by the gate."""
    if not 0.0 <= specialist_weight <= 1.0:
        raise ValueError("specialist_weight must be between 0 and 1")

    global_pred = np.asarray(global_predictions, dtype=float)
    specialist_pred = np.asarray(specialist_predictions, dtype=float)
    gate_mask = np.asarray(gate, dtype=bool)
    blended = global_pred.copy()
    blended[gate_mask] = (
        (1.0 - specialist_weight) * global_pred[gate_mask]
        + specialist_weight * specialist_pred[gate_mask]
    )
    return blended


def select_best_specialist_weight(
    y_true: np.ndarray,
    global_predictions: np.ndarray,
    specialist_predictions: np.ndarray,
    gate: np.ndarray,
    *,
    weights: tuple[float, ...] = DEFAULT_BLEND_WEIGHTS,
) -> dict[str, object]:
    """Pick the gated specialist blend weight with lowest OOF MAE."""
    candidates = []
    for weight in weights:
        prediction = apply_gated_specialist_predictions(
            global_predictions,
            specialist_predictions,
            gate,
            specialist_weight=weight,
        )
        candidates.append(
            {
                "specialist_weight": float(weight),
                "mae": float(mean_absolute_error(y_true, prediction)),
            }
        )
    best = min(candidates, key=lambda candidate: candidate["mae"])
    return {
        "specialist_weight": best["specialist_weight"],
        "oof_mae": best["mae"],
        "candidates": candidates,
    }


def _fit_specialist_predictions(
    prepared,
    random_state: int,
    *,
    specialist_min_price: float,
    fallback_predictions: np.ndarray,
) -> SpecialistFit:
    X_train, X_test, y_train, _ = _prepare_matrices(prepared)
    train_index = _market_index(prepared.train_engineered)
    test_index = _market_index(prepared.test_engineered)
    reference_index = market_index_reference(train_index)
    y_normalized = normalize_prices_to_market_index(
        y_train,
        train_index,
        reference_index=reference_index,
    )
    valid_train = (
        y_train.ge(specialist_min_price)
        & y_normalized.gt(0)
        & y_normalized.notna()
        & train_index.gt(0)
        & train_index.notna()
    )
    if valid_train.sum() < 100:
        raise ValueError("Not enough valid high-end rows to train a specialist model")

    model = _train_lgbm(
        X_train.loc[valid_train],
        y_normalized.loc[valid_train],
        prepared.categorical_features,
        random_state,
    )
    normalized_predictions = np.expm1(model.predict(X_test))
    predictions = denormalize_market_predictions(
        normalized_predictions,
        test_index,
        reference_index=reference_index,
        fallback_predictions=fallback_predictions,
    )
    fallback_rows = int((~test_index.gt(0) | test_index.isna()).sum())
    return SpecialistFit(
        predictions=predictions,
        reference_index=reference_index,
        train_rows=int(valid_train.sum()),
        fallback_prediction_rows=fallback_rows,
    )


def _build_oof_training_data(
    train_raw: pd.DataFrame,
    *,
    feature_set: str,
    n_splits: int,
    random_state: int,
    specialist_min_price: float,
) -> pd.DataFrame:
    sorted_train = train_raw.sort_values("sold_date").reset_index(drop=True)
    splitter = TimeSeriesSplit(n_splits=n_splits)
    rows = []

    for fold, (fold_train_idx, fold_valid_idx) in enumerate(splitter.split(sorted_train), start=1):
        fold_train_raw = sorted_train.iloc[fold_train_idx].reset_index(drop=True)
        fold_valid_raw = sorted_train.iloc[fold_valid_idx].reset_index(drop=True)
        prepared = _prepare_model_data(fold_train_raw, fold_valid_raw, feature_set)
        base_fit = _fit_base_model(prepared, random_state)
        normalized_fit = _fit_market_normalized_predictions(
            prepared,
            random_state,
            fallback_predictions=base_fit.predictions,
        )
        specialist_fit = _fit_specialist_predictions(
            prepared,
            random_state,
            specialist_min_price=specialist_min_price,
            fallback_predictions=normalized_fit.predictions,
        )
        fold_frame = prepared.test_engineered.reset_index(drop=True)
        rows.append(
            pd.DataFrame(
                {
                    "fold": fold,
                    "actual_price": fold_frame["sold_price"],
                    "base_prediction": base_fit.predictions,
                    "normalized_prediction": normalized_fit.predictions,
                    "specialist_prediction": specialist_fit.predictions,
                    "living_area": fold_frame["living_area"],
                    "same_size_ppsqm_median": fold_frame.get("same_size_ppsqm_median"),
                    "micro_area_ppsqm_median": fold_frame.get("micro_area_ppsqm_median"),
                    "micro_luxury_score": fold_frame.get("micro_luxury_score", 0.0),
                }
            )
        )

    return pd.concat(rows, ignore_index=True)


def _build_result_payload(
    *,
    feature_set: str,
    data_file: Path,
    raw_train: pd.DataFrame,
    raw_test: pd.DataFrame,
    test_frame: pd.DataFrame,
    global_predictions: np.ndarray,
    specialist_predictions: np.ndarray,
    specialist_blend_predictions: np.ndarray,
    test_gate: np.ndarray,
    global_blend_selection: dict[str, object],
    specialist_selection: dict[str, object],
    specialist_fit: SpecialistFit,
    oof: pd.DataFrame,
    oof_gate: np.ndarray,
    n_splits: int,
    specialist_min_price: float,
    gate_prediction_min: float,
    gate_comp_value_min: float,
    gate_luxury_score_min: float,
    gate_min_living_area: float,
) -> dict[str, object]:
    y_test = test_frame["sold_price"].reset_index(drop=True)
    diagnostic_frame = test_frame.copy().reset_index(drop=True)
    diagnostic_frame["base_prediction"] = global_predictions
    diagnostic_frame["calibrated_prediction"] = specialist_blend_predictions
    diagnostic_frame["specialist_gate"] = np.asarray(test_gate, dtype=bool)
    diagnostic_frame["sold_month"] = pd.to_datetime(diagnostic_frame["sold_date"]).dt.to_period("M").astype(str)
    diagnostic_frame["price_band"] = diagnostic_frame["sold_price"].apply(_price_band)
    diagnostic_frame["central_area"] = diagnostic_frame["area"].isin(
        {"ostermalm", "vasastan", "sodermalm", "kungsholmen"}
    )

    return {
        "metadata": {
            "feature_set": feature_set,
            "data_file": str(data_file),
            "train_rows": int(len(raw_train)),
            "test_rows": int(len(raw_test)),
            "test_start": str(raw_test["sold_date"].min().date()),
            "test_end": str(raw_test["sold_date"].max().date()),
            "oof_rows": int(len(oof)),
            "oof_splits": n_splits,
        },
        "specialist": {
            "specialist_min_price": specialist_min_price,
            "specialist_train_rows": specialist_fit.train_rows,
            "reference_index": specialist_fit.reference_index,
            "fallback_prediction_rows": specialist_fit.fallback_prediction_rows,
        },
        "gate": {
            "prediction_min": gate_prediction_min,
            "comp_value_min": gate_comp_value_min,
            "luxury_score_min": gate_luxury_score_min,
            "min_living_area": gate_min_living_area,
            "oof_gate_rows": int(np.asarray(oof_gate, dtype=bool).sum()),
            "test_gate_rows": int(np.asarray(test_gate, dtype=bool).sum()),
            "test_gate_rate": float(np.asarray(test_gate, dtype=bool).mean() * 100),
            "test_12m_plus_capture_rate": _capture_rate(y_test, test_gate, HIGH_END_REPORT_PRICE),
        },
        "blend_selection": {
            "global": global_blend_selection,
            "specialist": specialist_selection,
        },
        "global": _prediction_metrics(y_test, global_predictions),
        "specialist_raw": _prediction_metrics(y_test, specialist_predictions),
        "specialist_gated": _prediction_metrics(y_test, specialist_blend_predictions),
        "delta": _metric_delta(y_test, global_predictions, specialist_blend_predictions),
        "by_price_band": _compare_groups(diagnostic_frame, "price_band"),
        "by_month": _compare_groups(diagnostic_frame, "sold_month"),
        "by_central_area": _compare_groups(diagnostic_frame, "central_area"),
        "by_gate": _compare_groups(diagnostic_frame, "specialist_gate"),
        "worst_global_bias_areas": _compare_groups(diagnostic_frame, "area", min_rows=30)[:12],
    }


def _capture_rate(y_true: pd.Series, gate: np.ndarray, min_price: float) -> float:
    high_end = y_true.ge(min_price).to_numpy()
    if not high_end.any():
        return 0.0
    return float(np.asarray(gate, dtype=bool)[high_end].mean() * 100)


def _write_outputs(result: dict[str, object], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    feature_set = str(result["metadata"]["feature_set"])
    json_path = output_dir / f"{feature_set}_specialist.json"
    markdown_path = output_dir / f"{feature_set}_specialist.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown_path.write_text(_to_markdown(result), encoding="utf-8")


def _to_markdown(result: dict[str, object]) -> str:
    metadata = result["metadata"]
    gate = result["gate"]
    blend = result["blend_selection"]
    specialist = result["specialist"]
    lines = [
        f"# Specialist Model Experiment: `{metadata['feature_set']}`",
        "",
        f"Data: `{metadata['data_file']}`",
        f"Split: {metadata['train_rows']:,} train / {metadata['test_rows']:,} test, "
        f"{metadata['test_start']} to {metadata['test_end']}",
        f"OOF rows: {metadata['oof_rows']:,} across {metadata['oof_splits']} splits",
        f"Specialist training rows: {specialist['specialist_train_rows']:,} "
        f"(sold_price >= {specialist['specialist_min_price']:,.0f} SEK)",
        f"Gate: {gate['test_gate_rows']:,} test rows ({gate['test_gate_rate']:.2f}%), "
        f"{gate['test_12m_plus_capture_rate']:.2f}% of 12M+ rows captured",
        f"Selected global normalized weight: `{blend['global']['normalized_weight']:.2f}` "
        f"(OOF MAE {blend['global']['oof_mae']:,.0f} SEK)",
        f"Selected specialist gate weight: `{blend['specialist']['specialist_weight']:.2f}` "
        f"(OOF MAE {blend['specialist']['oof_mae']:,.0f} SEK)",
        "",
        "## Headline",
        _metrics_table(result),
        "",
        "## Segment Deltas",
        "Negative MAE delta is good. `Specialist gated` is compared against the global blend.",
        "",
        "### Price Bands",
        _group_table(result["by_price_band"]),
        "",
        "### Gate",
        _group_table(result["by_gate"]),
        "",
        "### Months",
        _group_table(result["by_month"]),
        "",
        "### Central Areas",
        _group_table(result["by_central_area"]),
        "",
        "### Worst Global Bias Areas",
        _group_table(result["worst_global_bias_areas"]),
        "",
    ]
    return "\n".join(lines)


def _metrics_table(result: dict[str, object]) -> str:
    rows = [
        ("Global", result["global"]),
        ("Specialist raw", result["specialist_raw"]),
        ("Specialist gated", result["specialist_gated"]),
        ("Delta", result["delta"]),
    ]
    lines = [
        "| Model | MAE | MAPE | Within 10% | Mean bias | Underpredicted |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for label, metrics in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    label,
                    _fmt_sek(metrics["mae"]),
                    _fmt_pct(metrics["mape"] * 100),
                    _fmt_pct(metrics["within_10_pct"]),
                    _fmt_sek(metrics["mean_bias"]),
                    _fmt_pct(metrics["underprediction_rate"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _group_table(rows: list[dict[str, object]]) -> str:
    lines = [
        "| Segment | Rows | Global MAE | Specialist MAE | MAE delta | Global bias | Specialist bias | Bias delta | Global under | Specialist under |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["segment"]),
                    str(row["rows"]),
                    _fmt_sek(row["base_mae"]),
                    _fmt_sek(row["calibrated_mae"]),
                    _fmt_sek(row["mae_delta"]),
                    _fmt_sek(row["base_bias"]),
                    _fmt_sek(row["calibrated_bias"]),
                    _fmt_sek(row["bias_delta"]),
                    _fmt_pct(row["base_underprediction_rate"]),
                    _fmt_pct(row["calibrated_underprediction_rate"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)
