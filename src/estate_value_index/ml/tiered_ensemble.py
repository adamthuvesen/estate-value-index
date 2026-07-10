"""Tiered low/mid/high expert ensemble experiments.

This is the experiment track that won: ml/production_models.py's
TieredProductionModel imports the tier-spec, gating, and blend-selection
helpers defined here to build the shipped no_list/listing models. See
specialist_model.py and premium_specialist.py for the two experiment tracks
that did not make it to production.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import TimeSeriesSplit

from estate_value_index.ml.market_normalized_target import (
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
from estate_value_index.ml.residual_calibration import (
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

DEFAULT_OUTPUT_DIR = Path("reports/tiered_ensemble_experiments")
DEFAULT_TRAIN_TIER_LOW_MAX_PRICE = 5_000_000.0
DEFAULT_TRAIN_TIER_MID_MIN_PRICE = 5_000_000.0
DEFAULT_TRAIN_TIER_MID_MAX_PRICE = 10_000_000.0
DEFAULT_TRAIN_TIER_HIGH_MIN_PRICE = 8_000_000.0
DEFAULT_INFERENCE_GATE_LOW_MAX = 5_000_000.0
DEFAULT_INFERENCE_GATE_HIGH_MIN = 10_000_000.0
DEFAULT_WEIGHT_STEP = 0.05
DEFAULT_MIN_SEGMENT_ROWS = 200
REPORT_HIGH_END_MIN_PRICE = 12_000_000.0
MODEL_NAMES = ("global", "low", "mid", "high")


@dataclass(frozen=True)
class TierSpec:
    name: str
    min_price: float | None
    max_price: float | None


@dataclass(frozen=True)
class TierExpertFit:
    predictions: dict[str, np.ndarray]
    reference_index: float
    train_rows: dict[str, int]
    fallback_prediction_rows: int


def run_tiered_ensemble_experiment(
    *,
    data_file: Path | None = None,
    feature_set: str = "no_list_price_h3_market_street",
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    n_splits: int = 4,
    random_state: int | None = None,
    low_max_price: float = DEFAULT_TRAIN_TIER_LOW_MAX_PRICE,
    mid_min_price: float = DEFAULT_TRAIN_TIER_MID_MIN_PRICE,
    mid_max_price: float = DEFAULT_TRAIN_TIER_MID_MAX_PRICE,
    high_min_price: float = DEFAULT_TRAIN_TIER_HIGH_MIN_PRICE,
    gate_low_max: float = DEFAULT_INFERENCE_GATE_LOW_MAX,
    gate_high_min: float = DEFAULT_INFERENCE_GATE_HIGH_MIN,
    weight_step: float = DEFAULT_WEIGHT_STEP,
    min_segment_rows: int = DEFAULT_MIN_SEGMENT_ROWS,
) -> dict[str, object]:
    """Train global plus low/mid/high experts and evaluate OOF-selected blends."""
    if n_splits < 2:
        raise ValueError("n_splits must be at least 2")
    _validate_thresholds(
        low_max_price=low_max_price,
        mid_min_price=mid_min_price,
        mid_max_price=mid_max_price,
        high_min_price=high_min_price,
        gate_low_max=gate_low_max,
        gate_high_min=gate_high_min,
    )

    seed = get_random_state() if random_state is None else random_state
    raw_train, raw_test = _load_temporal_raw_split(data_file, feature_set)
    tier_specs = _tier_specs(
        low_max_price=low_max_price,
        mid_min_price=mid_min_price,
        mid_max_price=mid_max_price,
        high_min_price=high_min_price,
    )
    prepared = _prepare_model_data(raw_train, raw_test, feature_set)

    base_fit = _fit_base_model(prepared, seed)
    normalized_fit = _fit_market_normalized_predictions(
        prepared,
        seed,
        fallback_predictions=base_fit.predictions,
    )
    tier_fit = _fit_tier_expert_predictions(
        prepared,
        seed,
        tier_specs=tier_specs,
        fallback_predictions=normalized_fit.predictions,
    )

    oof = _build_oof_training_data(
        raw_train,
        feature_set=feature_set,
        n_splits=n_splits,
        random_state=seed,
        tier_specs=tier_specs,
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
    oof_predictions = _prediction_frame(
        global_predictions=oof_global_blend,
        tier_predictions={
            spec.name: oof[f"{spec.name}_prediction"].to_numpy() for spec in tier_specs
        },
    )
    overall_selection = select_best_expert_weights(
        oof["actual_price"].to_numpy(),
        oof_predictions,
        weight_step=weight_step,
    )
    oof_gate = prediction_tier_labels(
        oof_global_blend,
        low_max=gate_low_max,
        high_min=gate_high_min,
    )
    gated_selection = select_gated_expert_weights(
        oof["actual_price"].to_numpy(),
        oof_predictions,
        oof_gate,
        fallback_weights=overall_selection["weights"],
        weight_step=weight_step,
        min_segment_rows=min_segment_rows,
    )

    global_blend = blend_market_predictions(
        base_fit.predictions,
        normalized_fit.predictions,
        normalized_weight=global_blend_selection["normalized_weight"],
    )
    test_predictions = _prediction_frame(
        global_predictions=global_blend,
        tier_predictions=tier_fit.predictions,
    )
    overall_blend = apply_expert_blend(test_predictions, overall_selection["weights"])
    test_gate = prediction_tier_labels(
        global_blend,
        low_max=gate_low_max,
        high_min=gate_high_min,
    )
    gated_blend = apply_gated_expert_blend(
        test_predictions,
        test_gate,
        gated_selection["weights_by_gate"],
        fallback_weights=overall_selection["weights"],
    )

    result = _build_result_payload(
        feature_set=feature_set,
        data_file=data_file or DEFAULT_DATA_FILE,
        raw_train=raw_train,
        raw_test=raw_test,
        test_frame=base_fit.test_frame,
        global_predictions=global_blend,
        expert_predictions=test_predictions,
        overall_blend_predictions=overall_blend,
        gated_blend_predictions=gated_blend,
        test_gate=test_gate,
        tier_specs=tier_specs,
        tier_fit=tier_fit,
        global_blend_selection=global_blend_selection,
        overall_selection=overall_selection,
        gated_selection=gated_selection,
        oof=oof,
        oof_gate=oof_gate,
        n_splits=n_splits,
        gate_low_max=gate_low_max,
        gate_high_min=gate_high_min,
        weight_step=weight_step,
        min_segment_rows=min_segment_rows,
    )
    _write_outputs(result, output_dir)
    return result


def prediction_tier_labels(
    predictions: np.ndarray | pd.Series,
    *,
    low_max: float = DEFAULT_INFERENCE_GATE_LOW_MAX,
    high_min: float = DEFAULT_INFERENCE_GATE_HIGH_MIN,
) -> np.ndarray:
    """Assign inference-safe low/mid/high gates from predicted price only."""
    values = np.asarray(predictions, dtype=float)
    labels = np.full(values.shape, "mid", dtype=object)
    finite = np.isfinite(values)
    labels[finite & (values < low_max)] = "low"
    labels[finite & (values >= high_min)] = "high"
    return labels


def apply_expert_blend(
    predictions: pd.DataFrame,
    weights: dict[str, float],
) -> np.ndarray:
    """Apply a convex expert blend."""
    _validate_weights(weights)
    missing = [name for name in weights if name not in predictions.columns]
    if missing:
        raise ValueError(f"Missing prediction columns: {', '.join(missing)}")

    blended = np.zeros(len(predictions), dtype=float)
    for name, weight in weights.items():
        blended += float(weight) * predictions[name].to_numpy(dtype=float)
    return np.clip(blended, 0, None)


def select_best_expert_weights(
    y_true: np.ndarray | pd.Series,
    predictions: pd.DataFrame,
    *,
    weight_step: float = DEFAULT_WEIGHT_STEP,
    model_names: tuple[str, ...] = MODEL_NAMES,
) -> dict[str, object]:
    """Pick one convex blend across all rows using OOF MAE."""
    y = np.asarray(y_true, dtype=float)
    best: dict[str, object] | None = None
    candidate_count = 0

    for weights in _weight_grid(model_names, weight_step):
        candidate_count += 1
        blended = apply_expert_blend(predictions, weights)
        mae = float(mean_absolute_error(y, blended))
        if best is None or mae < best["oof_mae"]:
            best = {"weights": weights, "oof_mae": mae}

    if best is None:
        raise ValueError("No expert weight candidates were generated")
    return {
        "weights": best["weights"],
        "oof_mae": best["oof_mae"],
        "candidate_count": candidate_count,
        "weight_step": weight_step,
    }


def select_gated_expert_weights(
    y_true: np.ndarray | pd.Series,
    predictions: pd.DataFrame,
    gate_labels: np.ndarray | pd.Series,
    *,
    fallback_weights: dict[str, float],
    weight_step: float = DEFAULT_WEIGHT_STEP,
    min_segment_rows: int = DEFAULT_MIN_SEGMENT_ROWS,
    model_names: tuple[str, ...] = MODEL_NAMES,
) -> dict[str, object]:
    """Pick separate convex expert weights per predicted-price gate."""
    if min_segment_rows < 1:
        raise ValueError("min_segment_rows must be at least 1")

    y = np.asarray(y_true, dtype=float)
    labels = np.asarray(gate_labels, dtype=object)
    weights_by_gate: dict[str, dict[str, float]] = {}
    segments: dict[str, dict[str, object]] = {}

    for label in ("low", "mid", "high"):
        mask = labels == label
        rows = int(mask.sum())
        if rows >= min_segment_rows:
            selection = select_best_expert_weights(
                y[mask],
                predictions.loc[mask].reset_index(drop=True),
                weight_step=weight_step,
                model_names=model_names,
            )
            weights = selection["weights"]
            oof_mae = selection["oof_mae"]
            used_fallback = False
        else:
            weights = dict(fallback_weights)
            oof_mae = (
                float(
                    mean_absolute_error(
                        y[mask],
                        apply_expert_blend(predictions.loc[mask], weights),
                    )
                )
                if rows
                else 0.0
            )
            used_fallback = True

        weights_by_gate[label] = dict(weights)
        segments[label] = {
            "rows": rows,
            "weights": dict(weights),
            "oof_mae": float(oof_mae),
            "used_fallback": used_fallback,
        }

    blended = apply_gated_expert_blend(
        predictions,
        labels,
        weights_by_gate,
        fallback_weights=fallback_weights,
    )
    return {
        "weights_by_gate": weights_by_gate,
        "segments": segments,
        "oof_mae": float(mean_absolute_error(y, blended)),
        "weight_step": weight_step,
        "min_segment_rows": min_segment_rows,
    }


def apply_gated_expert_blend(
    predictions: pd.DataFrame,
    gate_labels: np.ndarray | pd.Series,
    weights_by_gate: dict[str, dict[str, float]],
    *,
    fallback_weights: dict[str, float],
) -> np.ndarray:
    """Apply per-gate expert weights selected from OOF predictions."""
    labels = np.asarray(gate_labels, dtype=object)
    blended = apply_expert_blend(predictions, fallback_weights)

    for label, weights in weights_by_gate.items():
        mask = labels == label
        if mask.any():
            blended[mask] = apply_expert_blend(
                predictions.loc[mask].reset_index(drop=True),
                weights,
            )
    return blended


def _fit_tier_expert_predictions(
    prepared,
    random_state: int,
    *,
    tier_specs: tuple[TierSpec, ...],
    fallback_predictions: np.ndarray,
) -> TierExpertFit:
    X_train, X_test, y_train, _ = _prepare_matrices(prepared)
    train_index = _market_index(prepared.train_engineered)
    test_index = _market_index(prepared.test_engineered)
    reference_index = market_index_reference(train_index)
    y_normalized = normalize_prices_to_market_index(
        y_train,
        train_index,
        reference_index=reference_index,
    )
    base_valid = (
        y_train.gt(0)
        & y_normalized.gt(0)
        & y_normalized.notna()
        & train_index.gt(0)
        & train_index.notna()
    )
    fallback_rows = int((~test_index.gt(0) | test_index.isna()).sum())
    predictions: dict[str, np.ndarray] = {}
    train_rows: dict[str, int] = {}

    for spec in tier_specs:
        valid_train = base_valid & _tier_mask(y_train, spec)
        train_rows[spec.name] = int(valid_train.sum())
        if valid_train.sum() < 100:
            predictions[spec.name] = np.asarray(fallback_predictions, dtype=float)
            continue

        model = _train_lgbm(
            X_train.loc[valid_train],
            y_normalized.loc[valid_train],
            prepared.categorical_features,
            random_state,
        )
        normalized_predictions = np.expm1(model.predict(X_test))
        predictions[spec.name] = denormalize_market_predictions(
            normalized_predictions,
            test_index,
            reference_index=reference_index,
            fallback_predictions=fallback_predictions,
        )

    return TierExpertFit(
        predictions=predictions,
        reference_index=reference_index,
        train_rows=train_rows,
        fallback_prediction_rows=fallback_rows,
    )


def _build_oof_training_data(
    train_raw: pd.DataFrame,
    *,
    feature_set: str,
    n_splits: int,
    random_state: int,
    tier_specs: tuple[TierSpec, ...],
    include_calibration_features: bool = False,
) -> pd.DataFrame:
    """Build out-of-fold expert predictions via a forward-chaining time split.

    With ``include_calibration_features`` the engineered valid-fold columns are
    carried alongside the predictions, so a residual calibrator can be trained on
    genuinely out-of-fold rows (each valid fold is scored by models that never saw
    it). The default return shape is unchanged so blend selection stays untouched.
    """
    sorted_train = train_raw.sort_values("sold_date").reset_index(drop=True)
    splitter = TimeSeriesSplit(n_splits=n_splits)
    rows = []

    for fold, (fold_train_idx, fold_valid_idx) in enumerate(
        splitter.split(sorted_train),
        start=1,
    ):
        fold_train_raw = sorted_train.iloc[fold_train_idx].reset_index(drop=True)
        fold_valid_raw = sorted_train.iloc[fold_valid_idx].reset_index(drop=True)
        prepared = _prepare_model_data(fold_train_raw, fold_valid_raw, feature_set)
        base_fit = _fit_base_model(prepared, random_state)
        normalized_fit = _fit_market_normalized_predictions(
            prepared,
            random_state,
            fallback_predictions=base_fit.predictions,
        )
        tier_fit = _fit_tier_expert_predictions(
            prepared,
            random_state,
            tier_specs=tier_specs,
            fallback_predictions=normalized_fit.predictions,
        )
        fold_frame = prepared.test_engineered.reset_index(drop=True)
        if include_calibration_features:
            fold_rows = fold_frame.copy()
            fold_rows["fold"] = fold
            fold_rows["actual_price"] = fold_frame["sold_price"].to_numpy()
        else:
            fold_rows = pd.DataFrame(
                {
                    "fold": fold,
                    "actual_price": fold_frame["sold_price"],
                }
            )
        fold_rows["base_prediction"] = base_fit.predictions
        fold_rows["normalized_prediction"] = normalized_fit.predictions
        for spec in tier_specs:
            fold_rows[f"{spec.name}_prediction"] = tier_fit.predictions[spec.name]
        rows.append(fold_rows)

    return pd.concat(rows, ignore_index=True)


def _build_result_payload(
    *,
    feature_set: str,
    data_file: Path,
    raw_train: pd.DataFrame,
    raw_test: pd.DataFrame,
    test_frame: pd.DataFrame,
    global_predictions: np.ndarray,
    expert_predictions: pd.DataFrame,
    overall_blend_predictions: np.ndarray,
    gated_blend_predictions: np.ndarray,
    test_gate: np.ndarray,
    tier_specs: tuple[TierSpec, ...],
    tier_fit: TierExpertFit,
    global_blend_selection: dict[str, object],
    overall_selection: dict[str, object],
    gated_selection: dict[str, object],
    oof: pd.DataFrame,
    oof_gate: np.ndarray,
    n_splits: int,
    gate_low_max: float,
    gate_high_min: float,
    weight_step: float,
    min_segment_rows: int,
) -> dict[str, object]:
    y_test = test_frame["sold_price"].reset_index(drop=True)
    diagnostic_frame = test_frame.copy().reset_index(drop=True)
    diagnostic_frame["base_prediction"] = global_predictions
    diagnostic_frame["calibrated_prediction"] = gated_blend_predictions
    diagnostic_frame["overall_ensemble_prediction"] = overall_blend_predictions
    diagnostic_frame["predicted_tier"] = test_gate
    diagnostic_frame["sold_month"] = (
        pd.to_datetime(diagnostic_frame["sold_date"]).dt.to_period("M").astype(str)
    )
    diagnostic_frame["price_band"] = diagnostic_frame["sold_price"].apply(_price_band)
    diagnostic_frame["central_area"] = diagnostic_frame["area"].isin(
        {"ostermalm", "vasastan", "sodermalm", "kungsholmen"}
    )

    expert_metrics = {
        name: _prediction_metrics(y_test, expert_predictions[name].to_numpy(dtype=float))
        for name in MODEL_NAMES
        if name in expert_predictions.columns
    }

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
        "tiers": [
            {
                "name": spec.name,
                "min_price": spec.min_price,
                "max_price": spec.max_price,
                "train_rows": tier_fit.train_rows[spec.name],
            }
            for spec in tier_specs
        ],
        "market_normalization": {
            "reference_index": tier_fit.reference_index,
            "fallback_prediction_rows": tier_fit.fallback_prediction_rows,
        },
        "gate": {
            "low_max": gate_low_max,
            "high_min": gate_high_min,
            "oof_rows_by_gate": _count_labels(oof_gate),
            "test_rows_by_gate": _count_labels(test_gate),
            "test_12m_plus_capture_rate": _capture_rate(
                y_test, test_gate, REPORT_HIGH_END_MIN_PRICE
            ),
        },
        "blend_selection": {
            "global": global_blend_selection,
            "overall_ensemble": overall_selection,
            "gated_ensemble": gated_selection,
            "weight_step": weight_step,
            "min_segment_rows": min_segment_rows,
        },
        "global": _prediction_metrics(y_test, global_predictions),
        "experts": expert_metrics,
        "overall_ensemble": _prediction_metrics(y_test, overall_blend_predictions),
        "gated_ensemble": _prediction_metrics(y_test, gated_blend_predictions),
        "overall_delta_vs_global": _metric_delta(
            y_test, global_predictions, overall_blend_predictions
        ),
        "gated_delta_vs_global": _metric_delta(y_test, global_predictions, gated_blend_predictions),
        "by_price_band": _compare_groups(diagnostic_frame, "price_band"),
        "by_predicted_tier": _compare_groups(diagnostic_frame, "predicted_tier"),
        "by_month": _compare_groups(diagnostic_frame, "sold_month"),
        "by_central_area": _compare_groups(diagnostic_frame, "central_area"),
        "worst_global_bias_areas": _compare_groups(diagnostic_frame, "area", min_rows=30)[:12],
    }


def _tier_specs(
    *,
    low_max_price: float,
    mid_min_price: float,
    mid_max_price: float,
    high_min_price: float,
) -> tuple[TierSpec, ...]:
    return (
        TierSpec("low", None, low_max_price),
        TierSpec("mid", mid_min_price, mid_max_price),
        TierSpec("high", high_min_price, None),
    )


def _tier_mask(prices: pd.Series, spec: TierSpec) -> pd.Series:
    mask = pd.Series(True, index=prices.index)
    if spec.min_price is not None:
        mask &= prices.ge(spec.min_price)
    if spec.max_price is not None:
        mask &= prices.lt(spec.max_price)
    return mask


def _prediction_frame(
    *,
    global_predictions: np.ndarray,
    tier_predictions: dict[str, np.ndarray],
) -> pd.DataFrame:
    frame = pd.DataFrame({"global": np.asarray(global_predictions, dtype=float)})
    for name in ("low", "mid", "high"):
        frame[name] = np.asarray(tier_predictions[name], dtype=float)
    return frame


def _weight_grid(
    model_names: tuple[str, ...],
    weight_step: float,
) -> list[dict[str, float]]:
    if not 0.0 < weight_step <= 1.0:
        raise ValueError("weight_step must be between 0 and 1")
    units_float = 1.0 / weight_step
    units = int(round(units_float))
    if not np.isclose(units_float, units):
        raise ValueError("weight_step must divide 1.0 evenly")

    return [
        {name: float(part / units) for name, part in zip(model_names, composition, strict=True)}
        for composition in _integer_compositions(units, len(model_names))
    ]


def _integer_compositions(total: int, size: int) -> list[tuple[int, ...]]:
    if size == 1:
        return [(total,)]

    compositions: list[tuple[int, ...]] = []
    for value in range(total + 1):
        for tail in _integer_compositions(total - value, size - 1):
            compositions.append((value, *tail))
    return compositions


def _validate_weights(weights: dict[str, float]) -> None:
    total = sum(float(value) for value in weights.values())
    if not np.isclose(total, 1.0):
        raise ValueError("Expert weights must sum to 1")
    if any(float(value) < 0.0 for value in weights.values()):
        raise ValueError("Expert weights must be non-negative")


def _validate_thresholds(
    *,
    low_max_price: float,
    mid_min_price: float,
    mid_max_price: float,
    high_min_price: float,
    gate_low_max: float,
    gate_high_min: float,
) -> None:
    thresholds = {
        "low_max_price": low_max_price,
        "mid_min_price": mid_min_price,
        "mid_max_price": mid_max_price,
        "high_min_price": high_min_price,
        "gate_low_max": gate_low_max,
        "gate_high_min": gate_high_min,
    }
    for name, value in thresholds.items():
        if value <= 0 or not np.isfinite(value):
            raise ValueError(f"{name} must be a positive finite value")
    if mid_min_price >= mid_max_price:
        raise ValueError("mid_min_price must be lower than mid_max_price")
    if gate_low_max >= gate_high_min:
        raise ValueError("gate_low_max must be lower than gate_high_min")


def _count_labels(labels: np.ndarray | pd.Series) -> dict[str, int]:
    series = pd.Series(np.asarray(labels, dtype=object))
    return {label: int((series == label).sum()) for label in ("low", "mid", "high")}


def _capture_rate(y_true: pd.Series, gate_labels: np.ndarray, min_price: float) -> float:
    high_end = y_true.ge(min_price).to_numpy()
    if not high_end.any():
        return 0.0
    labels = np.asarray(gate_labels, dtype=object)
    return float((labels[high_end] == "high").mean() * 100)


def _write_outputs(result: dict[str, object], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    feature_set = str(result["metadata"]["feature_set"])
    json_path = output_dir / f"{feature_set}_tiered_ensemble.json"
    markdown_path = output_dir / f"{feature_set}_tiered_ensemble.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown_path.write_text(_to_markdown(result), encoding="utf-8")


def _to_markdown(result: dict[str, object]) -> str:
    metadata = result["metadata"]
    blend = result["blend_selection"]
    gate = result["gate"]
    lines = [
        f"# Tiered Ensemble Experiment: `{metadata['feature_set']}`",
        "",
        f"Data: `{metadata['data_file']}`",
        f"Split: {metadata['train_rows']:,} train / {metadata['test_rows']:,} test, "
        f"{metadata['test_start']} to {metadata['test_end']}",
        f"OOF rows: {metadata['oof_rows']:,} across {metadata['oof_splits']} splits",
        f"Global normalized weight: `{blend['global']['normalized_weight']:.2f}` "
        f"(OOF MAE {blend['global']['oof_mae']:,.0f} SEK)",
        f"Overall ensemble OOF MAE: `{blend['overall_ensemble']['oof_mae']:,.0f}` SEK",
        f"Gated ensemble OOF MAE: `{blend['gated_ensemble']['oof_mae']:,.0f}` SEK",
        f"Gate rows: low {gate['test_rows_by_gate']['low']:,}, "
        f"mid {gate['test_rows_by_gate']['mid']:,}, "
        f"high {gate['test_rows_by_gate']['high']:,}; "
        f"{gate['test_12m_plus_capture_rate']:.2f}% of 12M+ rows predicted high",
        "",
        "## Tier Training Rows",
        _tier_table(result["tiers"]),
        "",
        "## Selected Weights",
        _weights_table(blend),
        "",
        "## Headline",
        _metrics_table(result),
        "",
        "## Segment Deltas",
        "Negative MAE delta is good. `Gated ensemble` is compared against the global blend.",
        "",
        "### Price Bands",
        _group_table(result["by_price_band"]),
        "",
        "### Predicted Tiers",
        _group_table(result["by_predicted_tier"]),
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


def _tier_table(tiers: list[dict[str, object]]) -> str:
    lines = [
        "| Tier | Min price | Max price | Train rows |",
        "| --- | ---: | ---: | ---: |",
    ]
    for tier in tiers:
        min_price = _fmt_sek(tier["min_price"]) if tier["min_price"] is not None else ""
        max_price = _fmt_sek(tier["max_price"]) if tier["max_price"] is not None else ""
        lines.append(f"| {tier['name']} | {min_price} | {max_price} | {tier['train_rows']:,} |")
    return "\n".join(lines)


def _weights_table(blend: dict[str, object]) -> str:
    overall = blend["overall_ensemble"]["weights"]
    gated = blend["gated_ensemble"]["segments"]
    lines = [
        "| Gate | Rows | Global | Low | Mid | High | OOF MAE |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        _weight_row("overall", None, overall, blend["overall_ensemble"]["oof_mae"]),
    ]
    for gate_name in ("low", "mid", "high"):
        segment = gated[gate_name]
        lines.append(
            _weight_row(
                gate_name,
                segment["rows"],
                segment["weights"],
                segment["oof_mae"],
            )
        )
    return "\n".join(lines)


def _weight_row(
    label: str,
    rows: int | None,
    weights: dict[str, float],
    oof_mae: float,
) -> str:
    row_label = str(rows) if rows is not None else ""
    return (
        f"| {label} | {row_label} | {weights['global']:.2f} | "
        f"{weights['low']:.2f} | {weights['mid']:.2f} | {weights['high']:.2f} | "
        f"{_fmt_sek(oof_mae)} |"
    )


def _metrics_table(result: dict[str, object]) -> str:
    rows = [
        ("Global", result["global"]),
        ("Low expert", result["experts"]["low"]),
        ("Mid expert", result["experts"]["mid"]),
        ("High expert", result["experts"]["high"]),
        ("Overall ensemble", result["overall_ensemble"]),
        ("Gated ensemble", result["gated_ensemble"]),
        ("Gated delta", result["gated_delta_vs_global"]),
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
        "| Segment | Rows | Global MAE | Gated MAE | MAE delta | Global bias | Gated bias | Bias delta | Global under | Gated under |",
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
