"""PPSQM target and blend experiments for no-list-price model variants."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import TimeSeriesSplit

from estate_value_index.analytics.residual_calibration import (
    DEFAULT_DATA_FILE,
    _compare_groups,
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

DEFAULT_OUTPUT_DIR = Path("reports/ppsqm_experiments")
DEFAULT_BLEND_WEIGHTS = tuple(round(value, 2) for value in np.linspace(0.0, 1.0, 21))


def run_ppsqm_blend_experiment(
    *,
    data_file: Path | None = None,
    feature_set: str = "no_list_price_h3_comps",
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    n_splits: int = 4,
    random_state: int | None = None,
) -> dict[str, object]:
    """Train base price and PPSQM target models, then evaluate an OOF-chosen blend."""
    if n_splits < 2:
        raise ValueError("n_splits must be at least 2")

    seed = get_random_state() if random_state is None else random_state
    raw_train, raw_test = _load_temporal_raw_split(data_file, feature_set)
    prepared = _prepare_model_data(raw_train, raw_test, feature_set)

    base_predictions = _fit_base_predictions(prepared, seed)
    ppsqm_predictions = _fit_ppsqm_predictions(
        prepared, seed, fallback_predictions=base_predictions
    )

    oof = _build_oof_blend_training_data(
        raw_train,
        feature_set=feature_set,
        n_splits=n_splits,
        random_state=seed,
    )
    blend_selection = select_best_blend_weight(
        oof["actual_price"].to_numpy(),
        oof["base_prediction"].to_numpy(),
        oof["ppsqm_prediction"].to_numpy(),
    )
    blend_weight = blend_selection["ppsqm_weight"]
    blended_predictions = blend_predictions(
        base_predictions,
        ppsqm_predictions,
        ppsqm_weight=blend_weight,
    )

    result = _build_result_payload(
        feature_set=feature_set,
        data_file=data_file or DEFAULT_DATA_FILE,
        raw_train=raw_train,
        raw_test=raw_test,
        test_frame=prepared.test_engineered.reset_index(drop=True),
        base_predictions=base_predictions,
        ppsqm_predictions=ppsqm_predictions,
        blended_predictions=blended_predictions,
        blend_selection=blend_selection,
        oof=oof,
        n_splits=n_splits,
    )
    _write_outputs(result, output_dir)
    return result


def ppsqm_predictions_to_price(
    ppsqm_predictions: np.ndarray,
    living_area: pd.Series | np.ndarray,
    fallback_predictions: np.ndarray,
) -> np.ndarray:
    """Convert PPSQM predictions to SEK, using fallback where living area is invalid."""
    ppsqm = np.asarray(ppsqm_predictions, dtype=float)
    area = pd.to_numeric(pd.Series(living_area), errors="coerce").to_numpy(dtype=float)
    fallback = np.asarray(fallback_predictions, dtype=float)
    price = ppsqm * area
    valid = np.isfinite(price) & np.isfinite(area) & (area > 0)
    return np.where(valid, np.clip(price, 0, None), fallback)


def blend_predictions(
    base_predictions: np.ndarray,
    ppsqm_predictions: np.ndarray,
    *,
    ppsqm_weight: float,
) -> np.ndarray:
    """Blend base SEK predictions with PPSQM-derived SEK predictions."""
    if not 0.0 <= ppsqm_weight <= 1.0:
        raise ValueError("ppsqm_weight must be between 0 and 1")
    base = np.asarray(base_predictions, dtype=float)
    ppsqm = np.asarray(ppsqm_predictions, dtype=float)
    return (1.0 - ppsqm_weight) * base + ppsqm_weight * ppsqm


def select_best_blend_weight(
    y_true: np.ndarray,
    base_predictions: np.ndarray,
    ppsqm_predictions: np.ndarray,
    *,
    weights: tuple[float, ...] = DEFAULT_BLEND_WEIGHTS,
) -> dict[str, object]:
    """Pick the PPSQM blend weight with lowest MAE on out-of-fold predictions."""
    candidates = []
    for weight in weights:
        prediction = blend_predictions(base_predictions, ppsqm_predictions, ppsqm_weight=weight)
        candidates.append(
            {"ppsqm_weight": float(weight), "mae": float(mean_absolute_error(y_true, prediction))}
        )
    best = min(candidates, key=lambda candidate: candidate["mae"])
    return {
        "ppsqm_weight": best["ppsqm_weight"],
        "oof_mae": best["mae"],
        "candidates": candidates,
    }


def _fit_base_predictions(prepared, random_state: int) -> np.ndarray:
    X_train, X_test, y_train, _ = _prepare_matrices(prepared)
    model = _train_lgbm(X_train, y_train, prepared.categorical_features, random_state)
    return np.expm1(model.predict(X_test))


def _fit_ppsqm_predictions(
    prepared,
    random_state: int,
    *,
    fallback_predictions: np.ndarray,
) -> np.ndarray:
    X_train, X_test, y_train, _ = _prepare_matrices(prepared)
    train_area = pd.to_numeric(prepared.train_engineered["living_area"], errors="coerce")
    valid_train = train_area.notna() & train_area.gt(0) & y_train.gt(0)
    if valid_train.sum() < 100:
        raise ValueError("Not enough valid living_area rows to train a PPSQM model")

    y_ppsqm = y_train.loc[valid_train] / train_area.loc[valid_train]
    model = _train_ppsqm_model(
        X_train.loc[valid_train],
        y_ppsqm,
        prepared.categorical_features,
        random_state,
    )
    ppsqm_predictions = np.expm1(model.predict(X_test))
    return ppsqm_predictions_to_price(
        ppsqm_predictions,
        prepared.test_engineered["living_area"],
        fallback_predictions,
    )


def _train_ppsqm_model(
    X_train: pd.DataFrame,
    y_train_ppsqm: pd.Series,
    categorical_features: list[str],
    random_state: int,
) -> LGBMRegressor:
    return _train_lgbm(X_train, y_train_ppsqm, categorical_features, random_state)


def _build_oof_blend_training_data(
    train_raw: pd.DataFrame,
    *,
    feature_set: str,
    n_splits: int,
    random_state: int,
) -> pd.DataFrame:
    sorted_train = train_raw.sort_values("sold_date").reset_index(drop=True)
    splitter = TimeSeriesSplit(n_splits=n_splits)
    rows = []

    for fold, (fold_train_idx, fold_valid_idx) in enumerate(splitter.split(sorted_train), start=1):
        fold_train_raw = sorted_train.iloc[fold_train_idx].reset_index(drop=True)
        fold_valid_raw = sorted_train.iloc[fold_valid_idx].reset_index(drop=True)
        prepared = _prepare_model_data(fold_train_raw, fold_valid_raw, feature_set)
        base_predictions = _fit_base_predictions(prepared, random_state)
        ppsqm_predictions = _fit_ppsqm_predictions(
            prepared,
            random_state,
            fallback_predictions=base_predictions,
        )
        rows.append(
            pd.DataFrame(
                {
                    "fold": fold,
                    "actual_price": prepared.test_engineered["sold_price"].reset_index(drop=True),
                    "base_prediction": base_predictions,
                    "ppsqm_prediction": ppsqm_predictions,
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
    base_predictions: np.ndarray,
    ppsqm_predictions: np.ndarray,
    blended_predictions: np.ndarray,
    blend_selection: dict[str, object],
    oof: pd.DataFrame,
    n_splits: int,
) -> dict[str, object]:
    y_test = test_frame["sold_price"].reset_index(drop=True)
    diagnostic_frame = test_frame.copy().reset_index(drop=True)
    diagnostic_frame["base_prediction"] = base_predictions
    diagnostic_frame["ppsqm_prediction"] = ppsqm_predictions
    diagnostic_frame["calibrated_prediction"] = blended_predictions
    diagnostic_frame["sold_month"] = (
        pd.to_datetime(diagnostic_frame["sold_date"]).dt.to_period("M").astype(str)
    )
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
        "blend_selection": blend_selection,
        "base": _prediction_metrics(y_test, base_predictions),
        "ppsqm": _prediction_metrics(y_test, ppsqm_predictions),
        "blend": _prediction_metrics(y_test, blended_predictions),
        "ppsqm_delta_vs_base": _metric_delta(y_test, base_predictions, ppsqm_predictions),
        "blend_delta_vs_base": _metric_delta(y_test, base_predictions, blended_predictions),
        "by_price_band": _compare_groups(diagnostic_frame, "price_band"),
        "by_month": _compare_groups(diagnostic_frame, "sold_month"),
        "by_central_area": _compare_groups(diagnostic_frame, "central_area"),
        "worst_base_bias_areas": _compare_groups(diagnostic_frame, "area", min_rows=30)[:12],
    }


def _metric_delta(
    y_true: pd.Series,
    base_predictions: np.ndarray,
    challenger_predictions: np.ndarray,
) -> dict[str, float]:
    base = _prediction_metrics(y_true, base_predictions)
    challenger = _prediction_metrics(y_true, challenger_predictions)
    return {
        "mae": challenger["mae"] - base["mae"],
        "rmse": challenger["rmse"] - base["rmse"],
        "mape": challenger["mape"] - base["mape"],
        "within_10_pct": challenger["within_10_pct"] - base["within_10_pct"],
        "mean_bias": challenger["mean_bias"] - base["mean_bias"],
        "underprediction_rate": challenger["underprediction_rate"] - base["underprediction_rate"],
    }


def _write_outputs(result: dict[str, object], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    feature_set = str(result["metadata"]["feature_set"])
    json_path = output_dir / f"{feature_set}_ppsqm_blend.json"
    markdown_path = output_dir / f"{feature_set}_ppsqm_blend.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown_path.write_text(_to_markdown(result), encoding="utf-8")


def _to_markdown(result: dict[str, object]) -> str:
    metadata = result["metadata"]
    blend = result["blend_selection"]
    lines = [
        f"# PPSQM Blend Experiment: `{metadata['feature_set']}`",
        "",
        f"Data: `{metadata['data_file']}`",
        f"Split: {metadata['train_rows']:,} train / {metadata['test_rows']:,} test, "
        f"{metadata['test_start']} to {metadata['test_end']}",
        f"OOF blend training rows: {metadata['oof_rows']:,} across {metadata['oof_splits']} splits",
        f"Selected PPSQM blend weight: `{blend['ppsqm_weight']:.2f}` "
        f"(OOF MAE {blend['oof_mae']:,.0f} SEK)",
        "",
        "## Headline",
        _metrics_table(result),
        "",
        "## Segment Deltas",
        "Negative MAE delta is good. `Blend` is compared against the base price model.",
        "",
        "### Price Bands",
        _group_table(result["by_price_band"]),
        "",
        "### Months",
        _group_table(result["by_month"]),
        "",
        "### Central Areas",
        _group_table(result["by_central_area"]),
        "",
        "### Worst Base Bias Areas",
        _group_table(result["worst_base_bias_areas"]),
        "",
    ]
    return "\n".join(lines)


def _metrics_table(result: dict[str, object]) -> str:
    rows = [
        ("Base", result["base"]),
        ("PPSQM", result["ppsqm"]),
        ("Blend", result["blend"]),
        ("PPSQM delta", result["ppsqm_delta_vs_base"]),
        ("Blend delta", result["blend_delta_vs_base"]),
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
        "| Segment | Rows | Base MAE | Blend MAE | MAE delta | Base bias | Blend bias | Bias delta | Base under | Blend under |",
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
