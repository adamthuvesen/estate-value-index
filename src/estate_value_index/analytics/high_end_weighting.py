"""High-end sample weighting experiments for no-list-price model variants."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.model_selection import TimeSeriesSplit

from estate_value_index.analytics.market_normalized_target import (
    MarketNormalizedFit,
    _market_index,
    _metric_delta,
    blend_market_predictions,
    denormalize_market_predictions,
    market_index_reference,
    normalize_prices_to_market_index,
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
)
from estate_value_index.ml import get_categorical_indices
from estate_value_index.ml.training import LGBMTrainer
from estate_value_index.utils.settings import get_random_state

DEFAULT_OUTPUT_DIR = Path("reports/high_end_weighting_experiments")
DEFAULT_START_QUANTILE = 0.75
DEFAULT_MAX_WEIGHT = 2.25
DEFAULT_CURVE_POWER = 1.25


@dataclass(frozen=True)
class WeightedFitResult:
    predictions: np.ndarray
    weight_summary: dict[str, float]


def run_high_end_weighting_experiment(
    *,
    data_file: Path | None = None,
    feature_set: str = "no_list_price_h3_market",
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    n_splits: int = 4,
    random_state: int | None = None,
    start_quantile: float = DEFAULT_START_QUANTILE,
    max_weight: float = DEFAULT_MAX_WEIGHT,
    curve_power: float = DEFAULT_CURVE_POWER,
) -> dict[str, object]:
    """Compare unweighted and high-end-weighted market-normalized target models."""
    if n_splits < 2:
        raise ValueError("n_splits must be at least 2")

    seed = get_random_state() if random_state is None else random_state
    raw_train, raw_test = _load_temporal_raw_split(data_file, feature_set)
    prepared = _prepare_model_data(raw_train, raw_test, feature_set)

    weights = make_high_end_sample_weights(
        prepared.train_engineered["sold_price"],
        start_quantile=start_quantile,
        max_weight=max_weight,
        curve_power=curve_power,
    )
    unweighted_base = _fit_base_model(prepared, seed)
    unweighted_normalized = _fit_unweighted_market_normalized_predictions(
        prepared,
        seed,
        fallback_predictions=unweighted_base.predictions,
    )
    weighted_base = _fit_weighted_base_predictions(prepared, seed, sample_weight=weights)
    weighted_normalized = _fit_weighted_market_normalized_predictions(
        prepared,
        seed,
        sample_weight=weights,
        fallback_predictions=weighted_base.predictions,
    )

    oof = _build_oof_training_data(
        raw_train,
        feature_set=feature_set,
        n_splits=n_splits,
        random_state=seed,
        start_quantile=start_quantile,
        max_weight=max_weight,
        curve_power=curve_power,
    )
    unweighted_blend_selection = select_best_market_blend_weight(
        oof["actual_price"].to_numpy(),
        oof["unweighted_base_prediction"].to_numpy(),
        oof["unweighted_normalized_prediction"].to_numpy(),
    )
    weighted_blend_selection = select_best_market_blend_weight(
        oof["actual_price"].to_numpy(),
        oof["weighted_base_prediction"].to_numpy(),
        oof["weighted_normalized_prediction"].to_numpy(),
    )
    hybrid_blend_selection = select_best_market_blend_weight(
        oof["actual_price"].to_numpy(),
        oof["unweighted_base_prediction"].to_numpy(),
        oof["weighted_normalized_prediction"].to_numpy(),
    )
    unweighted_blend = blend_market_predictions(
        unweighted_base.predictions,
        unweighted_normalized.predictions,
        normalized_weight=unweighted_blend_selection["normalized_weight"],
    )
    weighted_blend = blend_market_predictions(
        weighted_base.predictions,
        weighted_normalized.predictions,
        normalized_weight=weighted_blend_selection["normalized_weight"],
    )
    hybrid_blend = blend_market_predictions(
        unweighted_base.predictions,
        weighted_normalized.predictions,
        normalized_weight=hybrid_blend_selection["normalized_weight"],
    )

    result = _build_result_payload(
        feature_set=feature_set,
        data_file=data_file or DEFAULT_DATA_FILE,
        raw_train=raw_train,
        raw_test=raw_test,
        test_frame=prepared.test_engineered.reset_index(drop=True),
        train_frame=prepared.train_engineered.reset_index(drop=True),
        sample_weight=weights.reset_index(drop=True),
        unweighted_base_predictions=unweighted_base.predictions,
        unweighted_normalized_predictions=unweighted_normalized.predictions,
        unweighted_blend_predictions=unweighted_blend,
        weighted_base_predictions=weighted_base.predictions,
        weighted_normalized_predictions=weighted_normalized.predictions,
        weighted_blend_predictions=weighted_blend,
        hybrid_blend_predictions=hybrid_blend,
        unweighted_blend_selection=unweighted_blend_selection,
        weighted_blend_selection=weighted_blend_selection,
        hybrid_blend_selection=hybrid_blend_selection,
        weighted_normalized_fit=weighted_normalized,
        oof=oof,
        n_splits=n_splits,
        start_quantile=start_quantile,
        max_weight=max_weight,
        curve_power=curve_power,
    )
    _write_outputs(result, output_dir)
    return result


def make_high_end_sample_weights(
    prices: pd.Series | np.ndarray,
    *,
    start_quantile: float = DEFAULT_START_QUANTILE,
    max_weight: float = DEFAULT_MAX_WEIGHT,
    curve_power: float = DEFAULT_CURVE_POWER,
) -> pd.Series:
    """Create a smooth target-based training weight ramp for expensive sales."""
    if not 0.0 <= start_quantile < 1.0:
        raise ValueError("start_quantile must be at least 0 and less than 1")
    if max_weight < 1.0:
        raise ValueError("max_weight must be at least 1")
    if curve_power <= 0:
        raise ValueError("curve_power must be positive")

    price_series = pd.to_numeric(pd.Series(prices), errors="coerce")
    ranks = price_series.rank(pct=True, method="average")
    scaled = ((ranks - start_quantile) / (1.0 - start_quantile)).clip(lower=0.0, upper=1.0)
    weights = 1.0 + (max_weight - 1.0) * scaled.pow(curve_power)
    return weights.fillna(1.0).astype(float)


def _fit_unweighted_market_normalized_predictions(
    prepared,
    random_state: int,
    *,
    fallback_predictions: np.ndarray,
) -> MarketNormalizedFit:
    unit_weights = pd.Series(1.0, index=prepared.train_engineered.index)
    return _fit_weighted_market_normalized_predictions(
        prepared,
        random_state,
        sample_weight=unit_weights,
        fallback_predictions=fallback_predictions,
    )


def _fit_weighted_base_predictions(
    prepared,
    random_state: int,
    *,
    sample_weight: pd.Series,
) -> WeightedFitResult:
    X_train, X_test, y_train, _ = _prepare_matrices(prepared)
    model = _train_lgbm_with_sample_weight(
        X_train,
        y_train,
        prepared.categorical_features,
        random_state,
        sample_weight=sample_weight,
    )
    return WeightedFitResult(
        predictions=np.expm1(model.predict(X_test)),
        weight_summary=_weight_summary(sample_weight),
    )


def _fit_weighted_market_normalized_predictions(
    prepared,
    random_state: int,
    *,
    sample_weight: pd.Series,
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

    model = _train_lgbm_with_sample_weight(
        X_train.loc[valid_train],
        y_normalized.loc[valid_train],
        prepared.categorical_features,
        random_state,
        sample_weight=sample_weight.loc[valid_train],
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


def _train_lgbm_with_sample_weight(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    categorical_features: list[str],
    random_state: int,
    *,
    sample_weight: pd.Series,
) -> LGBMRegressor:
    params = {
        "objective": "regression",
        "metric": "mae",
        "boosting_type": "gbdt",
        "random_state": random_state,
        "verbosity": -1,
        "n_jobs": -1,
    }
    params.update(LGBMTrainer.DEFAULT_PARAMS)
    model = LGBMRegressor(**params)
    categorical_indices = get_categorical_indices(X_train, categorical_features)
    fit_kwargs = {"sample_weight": sample_weight.to_numpy(dtype=float)}
    if categorical_indices:
        fit_kwargs["categorical_feature"] = categorical_indices
    model.fit(X_train, np.log1p(y_train), **fit_kwargs)
    return model


def _build_oof_training_data(
    train_raw: pd.DataFrame,
    *,
    feature_set: str,
    n_splits: int,
    random_state: int,
    start_quantile: float,
    max_weight: float,
    curve_power: float,
) -> pd.DataFrame:
    sorted_train = train_raw.sort_values("sold_date").reset_index(drop=True)
    splitter = TimeSeriesSplit(n_splits=n_splits)
    rows = []

    for fold, (fold_train_idx, fold_valid_idx) in enumerate(splitter.split(sorted_train), start=1):
        fold_train_raw = sorted_train.iloc[fold_train_idx].reset_index(drop=True)
        fold_valid_raw = sorted_train.iloc[fold_valid_idx].reset_index(drop=True)
        prepared = _prepare_model_data(fold_train_raw, fold_valid_raw, feature_set)
        weights = make_high_end_sample_weights(
            prepared.train_engineered["sold_price"],
            start_quantile=start_quantile,
            max_weight=max_weight,
            curve_power=curve_power,
        )

        unweighted_base = _fit_base_model(prepared, random_state)
        unweighted_normalized = _fit_unweighted_market_normalized_predictions(
            prepared,
            random_state,
            fallback_predictions=unweighted_base.predictions,
        )
        weighted_base = _fit_weighted_base_predictions(
            prepared,
            random_state,
            sample_weight=weights,
        )
        weighted_normalized = _fit_weighted_market_normalized_predictions(
            prepared,
            random_state,
            sample_weight=weights,
            fallback_predictions=weighted_base.predictions,
        )
        rows.append(
            pd.DataFrame(
                {
                    "fold": fold,
                    "actual_price": prepared.test_engineered["sold_price"].reset_index(drop=True),
                    "unweighted_base_prediction": unweighted_base.predictions,
                    "unweighted_normalized_prediction": unweighted_normalized.predictions,
                    "weighted_base_prediction": weighted_base.predictions,
                    "weighted_normalized_prediction": weighted_normalized.predictions,
                    "mean_weight": float(weights.mean()),
                    "max_weight": float(weights.max()),
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
    train_frame: pd.DataFrame,
    sample_weight: pd.Series,
    unweighted_base_predictions: np.ndarray,
    unweighted_normalized_predictions: np.ndarray,
    unweighted_blend_predictions: np.ndarray,
    weighted_base_predictions: np.ndarray,
    weighted_normalized_predictions: np.ndarray,
    weighted_blend_predictions: np.ndarray,
    hybrid_blend_predictions: np.ndarray,
    unweighted_blend_selection: dict[str, object],
    weighted_blend_selection: dict[str, object],
    hybrid_blend_selection: dict[str, object],
    weighted_normalized_fit: MarketNormalizedFit,
    oof: pd.DataFrame,
    n_splits: int,
    start_quantile: float,
    max_weight: float,
    curve_power: float,
) -> dict[str, object]:
    y_test = test_frame["sold_price"].reset_index(drop=True)
    weighted_candidates = {
        "weighted_normalized": weighted_normalized_predictions,
        "weighted_blend": weighted_blend_predictions,
        "hybrid_blend": hybrid_blend_predictions,
    }
    weighted_candidate_metrics = {
        name: _prediction_metrics(y_test, predictions)
        for name, predictions in weighted_candidates.items()
    }
    best_weighted_model = min(
        weighted_candidate_metrics,
        key=lambda name: weighted_candidate_metrics[name]["mae"],
    )
    diagnostic_frame = test_frame.copy().reset_index(drop=True)
    diagnostic_frame["base_prediction"] = unweighted_blend_predictions
    diagnostic_frame["calibrated_prediction"] = weighted_candidates[best_weighted_model]
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
        "weighting": {
            "strategy": "quantile_ramp",
            "start_quantile": start_quantile,
            "max_weight": max_weight,
            "curve_power": curve_power,
            "summary": _weight_summary(sample_weight),
            "by_price_band": _weight_by_price_band(train_frame, sample_weight),
        },
        "market_normalization": {
            "reference_index": weighted_normalized_fit.reference_index,
            "normalized_train_rows": weighted_normalized_fit.train_rows,
            "fallback_prediction_rows": weighted_normalized_fit.fallback_prediction_rows,
        },
        "blend_selection": {
            "unweighted": unweighted_blend_selection,
            "weighted": weighted_blend_selection,
            "hybrid": hybrid_blend_selection,
        },
        "best_weighted_model": best_weighted_model,
        "unweighted_base": _prediction_metrics(y_test, unweighted_base_predictions),
        "unweighted_normalized": _prediction_metrics(y_test, unweighted_normalized_predictions),
        "unweighted_blend": _prediction_metrics(y_test, unweighted_blend_predictions),
        "weighted_base": _prediction_metrics(y_test, weighted_base_predictions),
        "weighted_normalized": weighted_candidate_metrics["weighted_normalized"],
        "weighted_blend": weighted_candidate_metrics["weighted_blend"],
        "hybrid_blend": weighted_candidate_metrics["hybrid_blend"],
        "weighted_blend_delta_vs_unweighted_blend": _metric_delta(
            y_test,
            unweighted_blend_predictions,
            weighted_blend_predictions,
        ),
        "hybrid_blend_delta_vs_unweighted_blend": _metric_delta(
            y_test,
            unweighted_blend_predictions,
            hybrid_blend_predictions,
        ),
        "weighted_normalized_delta_vs_unweighted_normalized": _metric_delta(
            y_test,
            unweighted_normalized_predictions,
            weighted_normalized_predictions,
        ),
        "by_price_band": _compare_groups(diagnostic_frame, "price_band"),
        "by_month": _compare_groups(diagnostic_frame, "sold_month"),
        "by_central_area": _compare_groups(diagnostic_frame, "central_area"),
        "worst_unweighted_blend_bias_areas": _compare_groups(
            diagnostic_frame,
            "area",
            min_rows=30,
        )[:12],
    }


def _weight_summary(sample_weight: pd.Series) -> dict[str, float]:
    return {
        "min": float(sample_weight.min()),
        "mean": float(sample_weight.mean()),
        "median": float(sample_weight.median()),
        "p75": float(sample_weight.quantile(0.75)),
        "p90": float(sample_weight.quantile(0.90)),
        "p95": float(sample_weight.quantile(0.95)),
        "max": float(sample_weight.max()),
    }


def _weight_by_price_band(frame: pd.DataFrame, sample_weight: pd.Series) -> list[dict[str, object]]:
    work = pd.DataFrame(
        {
            "price_band": frame["sold_price"].apply(_price_band),
            "sample_weight": sample_weight.to_numpy(dtype=float),
        }
    )
    rows = []
    for price_band, group in work.groupby("price_band", sort=True):
        rows.append(
            {
                "price_band": str(price_band),
                "rows": int(len(group)),
                "mean_weight": float(group["sample_weight"].mean()),
                "max_weight": float(group["sample_weight"].max()),
            }
        )
    return rows


def _write_outputs(result: dict[str, object], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    feature_set = str(result["metadata"]["feature_set"])
    json_path = output_dir / f"{feature_set}_high_end_weighting.json"
    markdown_path = output_dir / f"{feature_set}_high_end_weighting.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown_path.write_text(_to_markdown(result), encoding="utf-8")


def _to_markdown(result: dict[str, object]) -> str:
    metadata = result["metadata"]
    weighting = result["weighting"]
    blend = result["blend_selection"]
    lines = [
        f"# High-End Weighting Experiment: `{metadata['feature_set']}`",
        "",
        f"Data: `{metadata['data_file']}`",
        f"Split: {metadata['train_rows']:,} train / {metadata['test_rows']:,} test, "
        f"{metadata['test_start']} to {metadata['test_end']}",
        f"OOF blend training rows: {metadata['oof_rows']:,} across {metadata['oof_splits']} splits",
        "Weighting: "
        f"`{weighting['strategy']}` from q{weighting['start_quantile']:.2f} "
        f"to max `{weighting['max_weight']:.2f}` with curve `{weighting['curve_power']:.2f}`",
        f"Selected unweighted normalized blend weight: `{blend['unweighted']['normalized_weight']:.2f}` "
        f"(OOF MAE {blend['unweighted']['oof_mae']:,.0f} SEK)",
        f"Selected weighted normalized blend weight: `{blend['weighted']['normalized_weight']:.2f}` "
        f"(OOF MAE {blend['weighted']['oof_mae']:,.0f} SEK)",
        f"Selected hybrid normalized blend weight: `{blend['hybrid']['normalized_weight']:.2f}` "
        f"(OOF MAE {blend['hybrid']['oof_mae']:,.0f} SEK)",
        f"Best weighted challenger by holdout MAE: `{result['best_weighted_model']}`",
        "",
        "## Headline",
        _metrics_table(result),
        "",
        "## Weight Distribution",
        _weight_table(weighting["by_price_band"]),
        "",
        "## Segment Deltas",
        "Negative MAE delta is good. `Weighted` is compared against the unweighted blend.",
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
        "### Worst Unweighted Blend Bias Areas",
        _group_table(result["worst_unweighted_blend_bias_areas"]),
        "",
    ]
    return "\n".join(lines)


def _metrics_table(result: dict[str, object]) -> str:
    rows = [
        ("Unweighted base", result["unweighted_base"]),
        ("Unweighted normalized", result["unweighted_normalized"]),
        ("Unweighted blend", result["unweighted_blend"]),
        ("Weighted base", result["weighted_base"]),
        ("Weighted normalized", result["weighted_normalized"]),
        ("Weighted blend", result["weighted_blend"]),
        ("Hybrid blend", result["hybrid_blend"]),
        ("Weighted blend delta", result["weighted_blend_delta_vs_unweighted_blend"]),
        ("Hybrid blend delta", result["hybrid_blend_delta_vs_unweighted_blend"]),
        ("Weighted normalized delta", result["weighted_normalized_delta_vs_unweighted_normalized"]),
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


def _weight_table(rows: list[dict[str, object]]) -> str:
    lines = [
        "| Price band | Rows | Mean weight | Max weight |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["price_band"]),
                    str(row["rows"]),
                    f"{float(row['mean_weight']):.3f}",
                    f"{float(row['max_weight']):.3f}",
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _group_table(rows: list[dict[str, object]]) -> str:
    lines = [
        "| Segment | Rows | Unweighted MAE | Weighted MAE | MAE delta | Unweighted bias | Weighted bias | Bias delta | Unweighted under | Weighted under |",
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
