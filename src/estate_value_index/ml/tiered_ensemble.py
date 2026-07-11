"""Tier specifications, fitting, gating, and blending for production models."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import TimeSeriesSplit

from estate_value_index.ml.market_normalized_target import (
    _fit_market_normalized_predictions,
    _market_index,
    denormalize_market_predictions,
    market_index_reference,
    normalize_prices_to_market_index,
)
from estate_value_index.ml.residual_calibration import (
    _fit_base_model,
    _prepare_matrices,
    _prepare_model_data,
    _train_lgbm,
)

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
