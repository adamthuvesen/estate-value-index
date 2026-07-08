"""Market-index-normalized target experiments for no-list-price model variants."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import TimeSeriesSplit

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
from estate_value_index.utils.settings import get_random_state

DEFAULT_OUTPUT_DIR = Path("reports/market_normalized_experiments")
DEFAULT_BLEND_WEIGHTS = tuple(round(value, 2) for value in np.linspace(0.0, 1.0, 21))
MARKET_INDEX_COLUMN = "market_ppsqm_index"


@dataclass(frozen=True)
class MarketNormalizedFit:
    predictions: np.ndarray
    reference_index: float
    train_rows: int
    fallback_prediction_rows: int


def run_market_normalized_experiment(
    *,
    data_file: Path | None = None,
    feature_set: str = "no_list_price_h3_market",
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    n_splits: int = 4,
    random_state: int | None = None,
) -> dict[str, object]:
    """Train a base model plus market-normalized target model and evaluate a blend."""
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

    oof = _build_oof_blend_training_data(
        raw_train,
        feature_set=feature_set,
        n_splits=n_splits,
        random_state=seed,
    )
    blend_selection = select_best_market_blend_weight(
        oof["actual_price"].to_numpy(),
        oof["base_prediction"].to_numpy(),
        oof["normalized_prediction"].to_numpy(),
    )
    blend_weight = blend_selection["normalized_weight"]
    blended_predictions = blend_market_predictions(
        base_fit.predictions,
        normalized_fit.predictions,
        normalized_weight=blend_weight,
    )

    result = _build_result_payload(
        feature_set=feature_set,
        data_file=data_file or DEFAULT_DATA_FILE,
        raw_train=raw_train,
        raw_test=raw_test,
        test_frame=base_fit.test_frame,
        base_predictions=base_fit.predictions,
        normalized_predictions=normalized_fit.predictions,
        blended_predictions=blended_predictions,
        normalized_fit=normalized_fit,
        blend_selection=blend_selection,
        oof=oof,
        n_splits=n_splits,
    )
    _write_outputs(result, output_dir)
    return result


def normalize_prices_to_market_index(
    prices: pd.Series | np.ndarray,
    market_index: pd.Series | np.ndarray,
    *,
    reference_index: float,
) -> pd.Series:
    """Convert SEK prices to a common market-index level."""
    if not np.isfinite(reference_index) or reference_index <= 0:
        raise ValueError("reference_index must be a positive finite value")

    price_series = _as_numeric_series(prices)
    index_series = _as_numeric_series(market_index, index=price_series.index)
    return price_series * reference_index / index_series


def denormalize_market_predictions(
    normalized_predictions: np.ndarray,
    market_index: pd.Series | np.ndarray,
    *,
    reference_index: float,
    fallback_predictions: np.ndarray,
) -> np.ndarray:
    """Convert market-normalized SEK predictions back to row-month SEK prices."""
    if not np.isfinite(reference_index) or reference_index <= 0:
        raise ValueError("reference_index must be a positive finite value")

    normalized = np.asarray(normalized_predictions, dtype=float)
    index_values = _as_numeric_series(market_index).to_numpy(dtype=float)
    fallback = np.asarray(fallback_predictions, dtype=float)
    prices = normalized * index_values / reference_index
    valid = (
        np.isfinite(prices)
        & np.isfinite(normalized)
        & np.isfinite(index_values)
        & (index_values > 0)
    )
    return np.where(valid, np.clip(prices, 0, None), fallback)


def market_index_reference(market_index: pd.Series | np.ndarray) -> float:
    """Use the median valid training market index as the normalizing baseline."""
    valid = _as_numeric_series(market_index)
    valid = valid[np.isfinite(valid) & (valid > 0)]
    if valid.empty:
        raise ValueError("At least one positive market index is required")
    return float(valid.median())


def blend_market_predictions(
    base_predictions: np.ndarray,
    normalized_predictions: np.ndarray,
    *,
    normalized_weight: float,
) -> np.ndarray:
    """Blend base SEK predictions with market-normalized-target SEK predictions."""
    if not 0.0 <= normalized_weight <= 1.0:
        raise ValueError("normalized_weight must be between 0 and 1")
    base = np.asarray(base_predictions, dtype=float)
    normalized = np.asarray(normalized_predictions, dtype=float)
    return (1.0 - normalized_weight) * base + normalized_weight * normalized


def select_best_market_blend_weight(
    y_true: np.ndarray,
    base_predictions: np.ndarray,
    normalized_predictions: np.ndarray,
    *,
    weights: tuple[float, ...] = DEFAULT_BLEND_WEIGHTS,
) -> dict[str, object]:
    """Pick the normalized-target blend weight with lowest OOF MAE."""
    candidates = []
    for weight in weights:
        prediction = blend_market_predictions(
            base_predictions,
            normalized_predictions,
            normalized_weight=weight,
        )
        candidates.append(
            {
                "normalized_weight": float(weight),
                "mae": float(mean_absolute_error(y_true, prediction)),
            }
        )
    best = min(candidates, key=lambda candidate: candidate["mae"])
    return {
        "normalized_weight": best["normalized_weight"],
        "oof_mae": best["mae"],
        "candidates": candidates,
    }


def _fit_market_normalized_predictions(
    prepared,
    random_state: int,
    *,
    fallback_predictions: np.ndarray,
) -> MarketNormalizedFit:
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
        y_train.gt(0)
        & y_normalized.gt(0)
        & y_normalized.notna()
        & train_index.gt(0)
        & train_index.notna()
    )
    if valid_train.sum() < 100:
        raise ValueError("Not enough valid market index rows to train a normalized target model")

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
    return MarketNormalizedFit(
        predictions=predictions,
        reference_index=reference_index,
        train_rows=int(valid_train.sum()),
        fallback_prediction_rows=fallback_rows,
    )


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
        base_fit = _fit_base_model(prepared, random_state)
        normalized_fit = _fit_market_normalized_predictions(
            prepared,
            random_state,
            fallback_predictions=base_fit.predictions,
        )
        rows.append(
            pd.DataFrame(
                {
                    "fold": fold,
                    "actual_price": prepared.test_engineered["sold_price"].reset_index(drop=True),
                    "base_prediction": base_fit.predictions,
                    "normalized_prediction": normalized_fit.predictions,
                    "reference_index": normalized_fit.reference_index,
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
    normalized_predictions: np.ndarray,
    blended_predictions: np.ndarray,
    normalized_fit: MarketNormalizedFit,
    blend_selection: dict[str, object],
    oof: pd.DataFrame,
    n_splits: int,
) -> dict[str, object]:
    y_test = test_frame["sold_price"].reset_index(drop=True)
    diagnostic_frame = test_frame.copy().reset_index(drop=True)
    diagnostic_frame["base_prediction"] = base_predictions
    diagnostic_frame["normalized_prediction"] = normalized_predictions
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
            "market_index_column": MARKET_INDEX_COLUMN,
        },
        "market_normalization": {
            "reference_index": normalized_fit.reference_index,
            "normalized_train_rows": normalized_fit.train_rows,
            "fallback_prediction_rows": normalized_fit.fallback_prediction_rows,
        },
        "blend_selection": blend_selection,
        "base": _prediction_metrics(y_test, base_predictions),
        "normalized": _prediction_metrics(y_test, normalized_predictions),
        "blend": _prediction_metrics(y_test, blended_predictions),
        "normalized_delta_vs_base": _metric_delta(y_test, base_predictions, normalized_predictions),
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
    json_path = output_dir / f"{feature_set}_market_normalized.json"
    markdown_path = output_dir / f"{feature_set}_market_normalized.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown_path.write_text(_to_markdown(result), encoding="utf-8")


def _to_markdown(result: dict[str, object]) -> str:
    metadata = result["metadata"]
    blend = result["blend_selection"]
    normalization = result["market_normalization"]
    lines = [
        f"# Market-Normalized Target Experiment: `{metadata['feature_set']}`",
        "",
        f"Data: `{metadata['data_file']}`",
        f"Split: {metadata['train_rows']:,} train / {metadata['test_rows']:,} test, "
        f"{metadata['test_start']} to {metadata['test_end']}",
        f"OOF blend training rows: {metadata['oof_rows']:,} across {metadata['oof_splits']} splits",
        f"Reference market index: `{normalization['reference_index']:,.0f}` "
        f"({normalization['normalized_train_rows']:,} normalized training rows)",
        f"Selected normalized-target blend weight: `{blend['normalized_weight']:.2f}` "
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
        ("Normalized", result["normalized"]),
        ("Blend", result["blend"]),
        ("Normalized delta", result["normalized_delta_vs_base"]),
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


def _market_index(frame: pd.DataFrame) -> pd.Series:
    if MARKET_INDEX_COLUMN not in frame.columns:
        raise ValueError(f"{MARKET_INDEX_COLUMN} is required for market-normalized target training")
    return pd.to_numeric(frame[MARKET_INDEX_COLUMN], errors="coerce")


def _as_numeric_series(values: pd.Series | np.ndarray, *, index=None) -> pd.Series:
    if isinstance(values, pd.Series):
        return pd.to_numeric(values, errors="coerce")
    return pd.to_numeric(pd.Series(values, index=index), errors="coerce")
