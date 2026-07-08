"""Premium-over-comp high-end specialist experiments.

Experiment track, not the production path — the tiered ensemble in
tiered_ensemble.py won this comparison and is what ml/production_models.py
ships. Kept for comparison reports and future high-end tuning experiments.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

from estate_value_index.analytics.market_normalized_target import (
    _fit_market_normalized_predictions,
    _metric_delta,
    blend_market_predictions,
    select_best_market_blend_weight,
)
from estate_value_index.analytics.residual_calibration import (
    DEFAULT_DATA_FILE,
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
from estate_value_index.analytics.specialist_model import (
    DEFAULT_GATE_COMP_VALUE_MIN,
    DEFAULT_GATE_LUXURY_SCORE_MIN,
    DEFAULT_GATE_MIN_LIVING_AREA,
    DEFAULT_GATE_PREDICTION_MIN,
    DEFAULT_SPECIALIST_MIN_PRICE,
    REPORT_HIGH_END_MIN_PRICE,
    _capture_rate,
    apply_gated_specialist_predictions,
    build_specialist_gate,
    select_best_specialist_weight,
)
from estate_value_index.utils.settings import get_random_state

DEFAULT_OUTPUT_DIR = Path("reports/premium_specialist_experiments")
DEFAULT_MAX_PREMIUM_RATIO = 5.0
DEFAULT_ANCHOR_COLUMNS = (
    "same_size_ppsqm_p90",
    "micro_area_ppsqm_p90",
    "h3_neighbor_ppsqm_p90",
    "same_size_ppsqm_p75",
    "micro_area_ppsqm_p75",
    "same_size_ppsqm_median",
    "micro_area_ppsqm_median",
)


@dataclass(frozen=True)
class PremiumSpecialistFit:
    predictions: np.ndarray
    train_rows: int
    fallback_prediction_rows: int
    anchor_columns: tuple[str, ...]
    max_premium_ratio: float


def run_premium_specialist_experiment(
    *,
    data_file: Path | None = None,
    feature_set: str = "no_list_price_h3_market_tail",
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    n_splits: int = 4,
    random_state: int | None = None,
    specialist_min_price: float = DEFAULT_SPECIALIST_MIN_PRICE,
    gate_prediction_min: float = DEFAULT_GATE_PREDICTION_MIN,
    gate_comp_value_min: float = DEFAULT_GATE_COMP_VALUE_MIN,
    gate_luxury_score_min: float = DEFAULT_GATE_LUXURY_SCORE_MIN,
    gate_min_living_area: float = DEFAULT_GATE_MIN_LIVING_AREA,
    anchor_columns: tuple[str, ...] = DEFAULT_ANCHOR_COLUMNS,
    max_premium_ratio: float = DEFAULT_MAX_PREMIUM_RATIO,
) -> dict[str, object]:
    """Train a global model plus a gated specialist for premium-over-comp ratio."""
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
    premium_fit = _fit_premium_specialist_predictions(
        prepared,
        seed,
        specialist_min_price=specialist_min_price,
        fallback_predictions=normalized_fit.predictions,
        anchor_columns=anchor_columns,
        max_premium_ratio=max_premium_ratio,
    )

    oof = _build_oof_training_data(
        raw_train,
        feature_set=feature_set,
        n_splits=n_splits,
        random_state=seed,
        specialist_min_price=specialist_min_price,
        anchor_columns=anchor_columns,
        max_premium_ratio=max_premium_ratio,
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
        oof["premium_specialist_prediction"].to_numpy(),
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
    premium_blend = apply_gated_specialist_predictions(
        global_blend,
        premium_fit.predictions,
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
        premium_predictions=premium_fit.predictions,
        premium_blend_predictions=premium_blend,
        test_gate=test_gate,
        global_blend_selection=global_blend_selection,
        specialist_selection=specialist_selection,
        premium_fit=premium_fit,
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


def comp_anchor_ppsqm(
    frame: pd.DataFrame,
    anchor_columns: tuple[str, ...] = DEFAULT_ANCHOR_COLUMNS,
) -> pd.Series:
    """Pick the strongest available prior comp PPSQM anchor for each row."""
    anchor = pd.Series(np.nan, index=frame.index, dtype=float)
    for column in anchor_columns:
        if column not in frame.columns:
            continue
        values = pd.to_numeric(frame[column], errors="coerce")
        values = values.where(np.isfinite(values) & values.gt(0))
        anchor = anchor.fillna(values)
    return anchor


def premium_over_comp_target(
    frame: pd.DataFrame,
    anchor_ppsqm: pd.Series,
) -> pd.Series:
    """Return actual sold price divided by comp-anchor value."""
    sold_price = pd.to_numeric(frame.get("sold_price"), errors="coerce")
    living_area = pd.to_numeric(frame.get("living_area"), errors="coerce")
    comp_value = anchor_ppsqm * living_area
    target = sold_price / comp_value
    return target.where(np.isfinite(target) & target.gt(0))


def premium_predictions_to_price(
    premium_predictions: np.ndarray,
    frame: pd.DataFrame,
    fallback_predictions: np.ndarray,
    *,
    anchor_columns: tuple[str, ...] = DEFAULT_ANCHOR_COLUMNS,
) -> np.ndarray:
    """Convert predicted premium-over-comp ratios back to SEK prices."""
    premium = np.asarray(premium_predictions, dtype=float)
    fallback = np.asarray(fallback_predictions, dtype=float)
    anchor = comp_anchor_ppsqm(frame, anchor_columns).to_numpy(dtype=float)
    living_area = pd.to_numeric(frame.get("living_area"), errors="coerce").to_numpy(dtype=float)
    prices = premium * anchor * living_area
    valid = _price_prediction_valid_mask(prices, premium, anchor, living_area)
    return np.where(valid, np.clip(prices, 0, None), fallback)


def _fit_premium_specialist_predictions(
    prepared,
    random_state: int,
    *,
    specialist_min_price: float,
    fallback_predictions: np.ndarray,
    anchor_columns: tuple[str, ...],
    max_premium_ratio: float,
) -> PremiumSpecialistFit:
    X_train, X_test, y_train, _ = _prepare_matrices(prepared)
    train_anchor = comp_anchor_ppsqm(prepared.train_engineered, anchor_columns)
    train_target = premium_over_comp_target(prepared.train_engineered, train_anchor)
    valid_train = (
        y_train.ge(specialist_min_price)
        & train_target.gt(0)
        & train_target.le(max_premium_ratio)
        & train_target.notna()
    )
    if valid_train.sum() < 100:
        raise ValueError("Not enough valid high-end rows to train a premium specialist")

    model = _train_lgbm(
        X_train.loc[valid_train],
        train_target.loc[valid_train],
        prepared.categorical_features,
        random_state,
    )
    premium_predictions = np.expm1(model.predict(X_test))
    test_anchor = comp_anchor_ppsqm(prepared.test_engineered, anchor_columns).to_numpy(dtype=float)
    test_living_area = pd.to_numeric(
        prepared.test_engineered.get("living_area"),
        errors="coerce",
    ).to_numpy(dtype=float)
    test_prices = premium_predictions * test_anchor * test_living_area
    valid_predictions = _price_prediction_valid_mask(
        test_prices,
        premium_predictions,
        test_anchor,
        test_living_area,
    )
    predictions = premium_predictions_to_price(
        premium_predictions,
        prepared.test_engineered,
        fallback_predictions,
        anchor_columns=anchor_columns,
    )
    fallback_rows = int((~valid_predictions).sum())
    return PremiumSpecialistFit(
        predictions=predictions,
        train_rows=int(valid_train.sum()),
        fallback_prediction_rows=fallback_rows,
        anchor_columns=anchor_columns,
        max_premium_ratio=max_premium_ratio,
    )


def _build_oof_training_data(
    train_raw: pd.DataFrame,
    *,
    feature_set: str,
    n_splits: int,
    random_state: int,
    specialist_min_price: float,
    anchor_columns: tuple[str, ...],
    max_premium_ratio: float,
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
        premium_fit = _fit_premium_specialist_predictions(
            prepared,
            random_state,
            specialist_min_price=specialist_min_price,
            fallback_predictions=normalized_fit.predictions,
            anchor_columns=anchor_columns,
            max_premium_ratio=max_premium_ratio,
        )
        fold_frame = prepared.test_engineered.reset_index(drop=True)
        row_data = {
            "fold": fold,
            "actual_price": fold_frame["sold_price"],
            "base_prediction": base_fit.predictions,
            "normalized_prediction": normalized_fit.predictions,
            "premium_specialist_prediction": premium_fit.predictions,
            "living_area": _frame_column(fold_frame, "living_area"),
            "same_size_ppsqm_median": _frame_column(fold_frame, "same_size_ppsqm_median"),
            "micro_area_ppsqm_median": _frame_column(fold_frame, "micro_area_ppsqm_median"),
            "micro_luxury_score": _frame_column(fold_frame, "micro_luxury_score", default=0.0),
        }
        for column in anchor_columns:
            if column not in row_data:
                row_data[column] = _frame_column(fold_frame, column)
        rows.append(pd.DataFrame(row_data))

    return pd.concat(rows, ignore_index=True)


def _build_result_payload(
    *,
    feature_set: str,
    data_file: Path,
    raw_train: pd.DataFrame,
    raw_test: pd.DataFrame,
    test_frame: pd.DataFrame,
    global_predictions: np.ndarray,
    premium_predictions: np.ndarray,
    premium_blend_predictions: np.ndarray,
    test_gate: np.ndarray,
    global_blend_selection: dict[str, object],
    specialist_selection: dict[str, object],
    premium_fit: PremiumSpecialistFit,
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
    diagnostic_frame["calibrated_prediction"] = premium_blend_predictions
    diagnostic_frame["specialist_gate"] = np.asarray(test_gate, dtype=bool)
    diagnostic_frame["sold_month"] = (
        pd.to_datetime(diagnostic_frame["sold_date"]).dt.to_period("M").astype(str)
    )
    diagnostic_frame["price_band"] = diagnostic_frame["sold_price"].apply(_price_band)
    diagnostic_frame["central_area"] = diagnostic_frame["area"].isin(
        {"ostermalm", "vasastan", "sodermalm", "kungsholmen"}
    )
    anchor = comp_anchor_ppsqm(diagnostic_frame, premium_fit.anchor_columns)
    diagnostic_frame["actual_premium_over_comp"] = premium_over_comp_target(
        diagnostic_frame,
        anchor,
    )
    diagnostic_frame["premium_band"] = diagnostic_frame["actual_premium_over_comp"].apply(
        _premium_band
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
        "premium_specialist": {
            "specialist_min_price": specialist_min_price,
            "specialist_train_rows": premium_fit.train_rows,
            "fallback_prediction_rows": premium_fit.fallback_prediction_rows,
            "anchor_columns": list(premium_fit.anchor_columns),
            "max_premium_ratio": premium_fit.max_premium_ratio,
        },
        "gate": {
            "prediction_min": gate_prediction_min,
            "comp_value_min": gate_comp_value_min,
            "luxury_score_min": gate_luxury_score_min,
            "min_living_area": gate_min_living_area,
            "oof_gate_rows": int(np.asarray(oof_gate, dtype=bool).sum()),
            "test_gate_rows": int(np.asarray(test_gate, dtype=bool).sum()),
            "test_gate_rate": float(np.asarray(test_gate, dtype=bool).mean() * 100),
            "test_12m_plus_capture_rate": _capture_rate(
                y_test, test_gate, REPORT_HIGH_END_MIN_PRICE
            ),
        },
        "blend_selection": {
            "global": global_blend_selection,
            "specialist": specialist_selection,
        },
        "global": _prediction_metrics(y_test, global_predictions),
        "premium_specialist_raw": _prediction_metrics(y_test, premium_predictions),
        "premium_specialist_gated": _prediction_metrics(y_test, premium_blend_predictions),
        "delta": _metric_delta(y_test, global_predictions, premium_blend_predictions),
        "by_price_band": _compare_groups(diagnostic_frame, "price_band"),
        "by_premium_band": _compare_groups(diagnostic_frame, "premium_band"),
        "by_month": _compare_groups(diagnostic_frame, "sold_month"),
        "by_central_area": _compare_groups(diagnostic_frame, "central_area"),
        "by_gate": _compare_groups(diagnostic_frame, "specialist_gate"),
        "worst_global_bias_areas": _compare_groups(diagnostic_frame, "area", min_rows=30)[:12],
    }


def _write_outputs(result: dict[str, object], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    feature_set = str(result["metadata"]["feature_set"])
    json_path = output_dir / f"{feature_set}_premium_specialist.json"
    markdown_path = output_dir / f"{feature_set}_premium_specialist.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown_path.write_text(_to_markdown(result), encoding="utf-8")


def _to_markdown(result: dict[str, object]) -> str:
    metadata = result["metadata"]
    gate = result["gate"]
    blend = result["blend_selection"]
    specialist = result["premium_specialist"]
    lines = [
        f"# Premium Specialist Experiment: `{metadata['feature_set']}`",
        "",
        f"Data: `{metadata['data_file']}`",
        f"Split: {metadata['train_rows']:,} train / {metadata['test_rows']:,} test, "
        f"{metadata['test_start']} to {metadata['test_end']}",
        f"OOF rows: {metadata['oof_rows']:,} across {metadata['oof_splits']} splits",
        f"Specialist training rows: {specialist['specialist_train_rows']:,} "
        f"(sold_price >= {specialist['specialist_min_price']:,.0f} SEK)",
        f"Comp anchors: `{', '.join(specialist['anchor_columns'])}`",
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
        "Negative MAE delta is good. `Premium gated` is compared against the global blend.",
        "",
        "### Price Bands",
        _group_table(result["by_price_band"]),
        "",
        "### Premium Over Comp",
        _group_table(result["by_premium_band"]),
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
        ("Premium raw", result["premium_specialist_raw"]),
        ("Premium gated", result["premium_specialist_gated"]),
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
        "| Segment | Rows | Global MAE | Premium MAE | MAE delta | Global bias | Premium bias | Bias delta | Global under | Premium under |",
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


def _premium_band(value: float) -> str:
    if pd.isna(value):
        return "unknown"
    if value <= 0.90:
        return "<=0.90"
    if value <= 1.00:
        return "0.90-1.00"
    if value <= 1.10:
        return "1.00-1.10"
    if value <= 1.25:
        return "1.10-1.25"
    if value <= 1.50:
        return "1.25-1.50"
    return "1.50+"


def _price_prediction_valid_mask(
    prices: np.ndarray,
    premium: np.ndarray,
    anchor: np.ndarray,
    living_area: np.ndarray,
) -> np.ndarray:
    return (
        np.isfinite(prices)
        & np.isfinite(premium)
        & np.isfinite(anchor)
        & np.isfinite(living_area)
        & (premium > 0)
        & (anchor > 0)
        & (living_area > 0)
    )


def _frame_column(frame: pd.DataFrame, column: str, *, default: float = np.nan) -> pd.Series:
    if column in frame.columns:
        return frame[column].reset_index(drop=True)
    return pd.Series(default, index=range(len(frame)))
