"""Production two-model training and inference.

The public serving contract has two model ids:

- ``no_list_price``: does not use the listing (asking) price.
- ``with_list_price``: uses the listing price when it is available.

``TieredProductionModel`` wraps the tier-spec, gating, and blend-selection
helpers from ``analytics.tiered_ensemble`` — the experiment track that won
over ``analytics.specialist_model`` and ``analytics.premium_specialist``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from estate_value_index.analytics.market_normalized_target import (
    _market_index,
    blend_market_predictions,
    denormalize_market_predictions,
    market_index_reference,
    normalize_prices_to_market_index,
    select_best_market_blend_weight,
)
from estate_value_index.analytics.residual_calibration import (
    CENTRAL_AREAS,
    _feature_set_requires_listing_price,
    _fit_residual_calibrator,
    _prediction_metrics,
    _resolve_features,
    _train_lgbm,
    apply_calibration_correction,
    build_calibration_features,
)
from estate_value_index.analytics.tiered_ensemble import (
    DEFAULT_INFERENCE_GATE_HIGH_MIN,
    DEFAULT_INFERENCE_GATE_LOW_MAX,
    DEFAULT_MIN_SEGMENT_ROWS,
    DEFAULT_TRAIN_TIER_HIGH_MIN_PRICE,
    DEFAULT_TRAIN_TIER_LOW_MAX_PRICE,
    DEFAULT_TRAIN_TIER_MID_MAX_PRICE,
    DEFAULT_TRAIN_TIER_MID_MIN_PRICE,
    DEFAULT_WEIGHT_STEP,
    MODEL_NAMES,
    REPORT_HIGH_END_MIN_PRICE,
    TierSpec,
    _build_oof_training_data,
    _prediction_frame,
    _tier_mask,
    _tier_specs,
    apply_gated_expert_blend,
    prediction_tier_labels,
    select_best_expert_weights,
    select_gated_expert_weights,
)
from estate_value_index.ml import (
    build_feature_context,
    create_optimized_features,
    create_temporal_holdout_split,
    filter_valid_listings,
)
from estate_value_index.ml.features.context import FeatureEngineeringContext
from estate_value_index.ml.training_workflow.data import load_training_dataframe
from estate_value_index.ml.training_workflow.runner import _context_payload
from estate_value_index.model_artifacts import (
    DEFAULT_MODEL_PREFIX,
    LISTING_MODEL_ID,
    NO_LIST_MODEL_ID,
    production_artifact_names,
)
from estate_value_index.utils.gcs import (
    is_gcs_enabled,
    upload_model_artifacts,
    write_sha256_sidecar,
)
from estate_value_index.utils.settings import get_random_state, get_test_size

logger = logging.getLogger(__name__)

DEFAULT_NO_LIST_FEATURE_SET = "no_list_price_v1"
DEFAULT_LISTING_FEATURE_SET = "with_list_price_v1"
ASK_PRICE_COLUMNS = ("listing_price", "price_per_sqm", "relative_area_price", "price_change")

# Residual calibration is applied only to the no_list_price model, and only to high
# predictions where the tiered model still underpredicts. Offline proof showed
# global calibration worsened aggregate bias by nudging the well-calibrated
# mid-market down; restricting to the tail improves MAE, bias, and the high-end
# at once. See analytics/production_residual_calibration.py.
DEFAULT_CALIBRATION_MAX_ABS = 1_000_000.0
DEFAULT_CALIBRATION_MAX_FRAC = 0.12
DEFAULT_CALIBRATION_MIN_PREDICTION = 8_000_000.0


@dataclass(frozen=True)
class ProductionModelSpec:
    model_id: str
    feature_set: str
    requires_listing_price: bool


@dataclass(frozen=True)
class ProductionTrainingResult:
    model: TieredProductionModel
    metrics: dict[str, object]
    artifact_paths: dict[str, str]


@dataclass
class TieredProductionModel:
    """Serializable price-tiered gated-ensemble production model."""

    model_id: str
    feature_set: str
    requires_listing_price: bool
    numeric_features: list[str]
    categorical_features: list[str]
    context: FeatureEngineeringContext
    base_model: Any
    normalized_model: Any
    tier_models: dict[str, Any | None]
    reference_index: float
    market_blend_weight: float
    overall_weights: dict[str, float]
    gated_weights_by_gate: dict[str, dict[str, float]]
    fallback_weights: dict[str, float]
    gate_low_max: float = DEFAULT_INFERENCE_GATE_LOW_MAX
    gate_high_min: float = DEFAULT_INFERENCE_GATE_HIGH_MIN
    residual_calibrator: Any | None = None
    calibration_max_abs: float = DEFAULT_CALIBRATION_MAX_ABS
    calibration_max_frac: float = DEFAULT_CALIBRATION_MAX_FRAC
    calibration_min_prediction: float = DEFAULT_CALIBRATION_MIN_PREDICTION

    @property
    def model_type(self) -> str:
        return "price_tiered_ensemble"

    def predict(self, X_raw: pd.DataFrame, *, apply_calibration: bool = True) -> np.ndarray:
        raw = _prepare_raw_for_model(X_raw, requires_listing_price=self.requires_listing_price)
        engineered = create_optimized_features(raw, context=self.context)
        X = _feature_matrix(
            engineered,
            self.numeric_features,
            self.categorical_features,
            self.context,
        )

        base_predictions = np.expm1(self.base_model.predict(X))
        market_index = _market_index(engineered)
        normalized_predictions = _predict_market_model(
            self.normalized_model,
            X,
            market_index,
            reference_index=self.reference_index,
            fallback_predictions=base_predictions,
        )
        global_predictions = blend_market_predictions(
            base_predictions,
            normalized_predictions,
            normalized_weight=self.market_blend_weight,
        )

        tier_predictions = {}
        for name, model in self.tier_models.items():
            if model is None:
                tier_predictions[name] = normalized_predictions
            else:
                tier_predictions[name] = _predict_market_model(
                    model,
                    X,
                    market_index,
                    reference_index=self.reference_index,
                    fallback_predictions=normalized_predictions,
                )

        expert_predictions = _prediction_frame(
            global_predictions=global_predictions,
            tier_predictions=tier_predictions,
        )
        gate = prediction_tier_labels(
            global_predictions,
            low_max=self.gate_low_max,
            high_min=self.gate_high_min,
        )
        gated_predictions = apply_gated_expert_blend(
            expert_predictions,
            gate,
            self.gated_weights_by_gate,
            fallback_weights=self.fallback_weights,
        )
        if apply_calibration:
            return self._apply_calibration(engineered, gated_predictions)
        return gated_predictions

    def _apply_calibration(
        self,
        engineered: pd.DataFrame,
        gated_predictions: np.ndarray,
    ) -> np.ndarray:
        if self.residual_calibrator is None or self.model_id != NO_LIST_MODEL_ID:
            return gated_predictions
        correction = self.residual_calibrator.predict(
            build_calibration_features(engineered, gated_predictions)
        )
        return apply_calibration_correction(
            gated_predictions,
            correction,
            max_abs=self.calibration_max_abs,
            max_frac=self.calibration_max_frac,
            min_base_prediction=self.calibration_min_prediction,
        )


def production_specs(
    *,
    no_list_feature_set: str = DEFAULT_NO_LIST_FEATURE_SET,
    listing_feature_set: str = DEFAULT_LISTING_FEATURE_SET,
) -> tuple[ProductionModelSpec, ProductionModelSpec]:
    return (
        ProductionModelSpec(
            model_id=NO_LIST_MODEL_ID,
            feature_set=no_list_feature_set,
            requires_listing_price=False,
        ),
        ProductionModelSpec(
            model_id=LISTING_MODEL_ID,
            feature_set=listing_feature_set,
            requires_listing_price=True,
        ),
    )


def load_raw_training_frame(
    *,
    data_source: str,
    data_file: str | Path | None,
) -> pd.DataFrame:
    frame, skip_feature_engineering = load_training_dataframe(
        use_materialized_features=False,
        data_source=data_source,
        data_file=data_file,
    )
    if skip_feature_engineering:
        raise ValueError("Production model training requires raw listings")
    return frame


def train_and_persist_production_models(
    *,
    raw_frame: pd.DataFrame,
    model_dir: Path,
    model_prefix: str = DEFAULT_MODEL_PREFIX,
    specs: tuple[ProductionModelSpec, ...] | None = None,
    n_splits: int = 4,
    random_state: int | None = None,
) -> dict[str, ProductionTrainingResult]:
    """Run temporal evaluation, refit on all rows, and persist both models."""
    model_dir.mkdir(parents=True, exist_ok=True)
    seed = get_random_state() if random_state is None else random_state
    resolved_specs = specs or production_specs()
    results: dict[str, ProductionTrainingResult] = {}

    for spec in resolved_specs:
        logger.info("Training production model %s (%s)", spec.model_id, spec.feature_set)
        filtered = filter_training_rows(raw_frame, spec.feature_set)
        train_raw, test_raw = create_temporal_holdout_split(
            filtered,
            test_size=get_test_size(),
            date_column="sold_date",
        )
        evaluation_model = fit_tiered_production_model(
            train_raw,
            spec=spec,
            n_splits=n_splits,
            random_state=seed,
        )
        eval_test = test_raw.reset_index(drop=True)
        y_test = eval_test["sold_price"]
        predictions = evaluation_model.predict(eval_test)
        heldout_metrics = _prediction_metrics(y_test, predictions)
        calibration = _calibration_report(evaluation_model, eval_test, y_test, served=predictions)

        production_model = fit_tiered_production_model(
            filtered,
            spec=spec,
            n_splits=n_splits,
            random_state=seed,
        )
        metrics = _metrics_payload(
            production_model,
            heldout_metrics=heldout_metrics,
            calibration=calibration,
            train_rows=len(train_raw),
            test_rows=len(test_raw),
            production_rows=len(filtered),
            test_start=str(test_raw["sold_date"].min().date()),
            test_end=str(test_raw["sold_date"].max().date()),
        )
        artifact_paths = persist_production_model(
            production_model,
            model_dir=model_dir,
            model_prefix=model_prefix,
            metrics=metrics,
        )
        results[spec.model_id] = ProductionTrainingResult(
            model=production_model,
            metrics=metrics,
            artifact_paths=artifact_paths,
        )

    return results


def filter_training_rows(raw_frame: pd.DataFrame, feature_set: str) -> pd.DataFrame:
    filtered = filter_valid_listings(
        raw_frame,
        min_price=3_000_000,
        drop_na_features=False,
        require_listing_price=_feature_set_requires_listing_price(feature_set),
    )
    filtered = filtered.copy()
    filtered["sold_date"] = pd.to_datetime(filtered["sold_date"], errors="coerce")
    filtered = filtered.loc[filtered["sold_date"].notna()].reset_index(drop=True)
    if filtered.empty:
        raise ValueError(f"No valid training rows for feature set {feature_set}")
    return filtered


def fit_tiered_production_model(
    raw_frame: pd.DataFrame,
    *,
    spec: ProductionModelSpec,
    n_splits: int,
    random_state: int,
    low_max_price: float = DEFAULT_TRAIN_TIER_LOW_MAX_PRICE,
    mid_min_price: float = DEFAULT_TRAIN_TIER_MID_MIN_PRICE,
    mid_max_price: float = DEFAULT_TRAIN_TIER_MID_MAX_PRICE,
    high_min_price: float = DEFAULT_TRAIN_TIER_HIGH_MIN_PRICE,
    gate_low_max: float = DEFAULT_INFERENCE_GATE_LOW_MAX,
    gate_high_min: float = DEFAULT_INFERENCE_GATE_HIGH_MIN,
    weight_step: float = DEFAULT_WEIGHT_STEP,
    min_segment_rows: int = DEFAULT_MIN_SEGMENT_ROWS,
) -> TieredProductionModel:
    if n_splits < 2:
        raise ValueError("n_splits must be at least 2")

    raw = _prepare_raw_for_model(raw_frame, requires_listing_price=spec.requires_listing_price)
    engineered = create_optimized_features(raw)
    context = build_feature_context(engineered)
    numeric_features, categorical_features = _resolve_features(engineered, spec.feature_set)
    X = _feature_matrix(engineered, numeric_features, categorical_features, context)
    y = engineered["sold_price"].copy()

    base_model = _train_lgbm(X, y, categorical_features, random_state)
    train_index = _market_index(engineered)
    reference_index = market_index_reference(train_index)
    y_normalized = normalize_prices_to_market_index(
        y,
        train_index,
        reference_index=reference_index,
    )
    valid_market = (
        y.gt(0)
        & y_normalized.gt(0)
        & y_normalized.notna()
        & train_index.gt(0)
        & train_index.notna()
    )
    if valid_market.sum() < 100:
        raise ValueError("Not enough valid market-index rows to train production model")

    normalized_model = _train_lgbm(
        X.loc[valid_market],
        y_normalized.loc[valid_market],
        categorical_features,
        random_state,
    )

    tier_specs = _tier_specs(
        low_max_price=low_max_price,
        mid_min_price=mid_min_price,
        mid_max_price=mid_max_price,
        high_min_price=high_min_price,
    )
    tier_models = _fit_tier_models(
        X,
        y,
        y_normalized,
        train_index,
        valid_market,
        categorical_features,
        tier_specs=tier_specs,
        random_state=random_state,
    )
    fit_calibrator = spec.model_id == NO_LIST_MODEL_ID
    blend = _select_blend(
        raw,
        spec.feature_set,
        n_splits,
        random_state,
        tier_specs,
        weight_step,
        min_segment_rows,
        include_calibration_features=fit_calibrator,
    )

    model = TieredProductionModel(
        model_id=spec.model_id,
        feature_set=spec.feature_set,
        requires_listing_price=spec.requires_listing_price,
        numeric_features=numeric_features,
        categorical_features=categorical_features,
        context=context,
        base_model=base_model,
        normalized_model=normalized_model,
        tier_models=tier_models,
        reference_index=reference_index,
        market_blend_weight=float(blend["global"]["normalized_weight"]),
        overall_weights=dict(blend["overall_ensemble"]["weights"]),
        gated_weights_by_gate={
            key: dict(value) for key, value in blend["gated_ensemble"]["weights_by_gate"].items()
        },
        fallback_weights=dict(blend["overall_ensemble"]["weights"]),
        gate_low_max=gate_low_max,
        gate_high_min=gate_high_min,
    )
    if fit_calibrator:
        # Calibrator uses the model's own selected blend weights, so it must be fit
        # after the model exists. Trained on out-of-fold residuals only.
        model.residual_calibrator = _fit_model_residual_calibrator(
            model,
            blend["oof"],
            tier_specs,
            random_state,
        )
    return model


def persist_production_model(
    model: TieredProductionModel,
    *,
    model_dir: Path,
    model_prefix: str,
    metrics: dict[str, object],
) -> dict[str, str]:
    names = production_artifact_names(model.model_id, model_prefix)
    model_path = model_dir / names.model
    metrics_path = model_dir / names.metrics
    context_path = model_dir / names.context
    importance_path = model_dir / names.importance

    joblib.dump(model, model_path)
    sidecar_path = write_sha256_sidecar(model_path)
    metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    context_path.write_text(
        json.dumps(_context_payload(model.context), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    importance_path.write_text(
        json.dumps(_feature_importance_payload(model), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if is_gcs_enabled():
        upload_model_artifacts(model_dir, names.stem)

    return {
        "model": str(model_path),
        "model_sha256": str(sidecar_path),
        "metrics": str(metrics_path),
        "context": str(context_path),
        "importance": str(importance_path),
    }


def _prepare_raw_for_model(raw_frame: pd.DataFrame, *, requires_listing_price: bool) -> pd.DataFrame:
    raw = raw_frame.copy()
    if not requires_listing_price:
        for column in ASK_PRICE_COLUMNS:
            raw[column] = np.nan
    return raw


def _engineer_for_model(raw_frame: pd.DataFrame, model: TieredProductionModel) -> pd.DataFrame:
    """Engineer rows the same way ``model.predict`` does, for offline calibration inputs."""
    raw = _prepare_raw_for_model(
        raw_frame.reset_index(drop=True),
        requires_listing_price=model.requires_listing_price,
    )
    return create_optimized_features(raw, context=model.context)


def _feature_matrix(
    engineered: pd.DataFrame,
    numeric_features: list[str],
    categorical_features: list[str],
    context: FeatureEngineeringContext,
) -> pd.DataFrame:
    X = pd.DataFrame(index=engineered.index)

    for column in numeric_features:
        values = engineered[column] if column in engineered.columns else np.nan
        X[column] = pd.to_numeric(values, errors="coerce")
        fill_value = context.numeric_fill_values.get(column)
        X[column] = X[column].fillna(0 if fill_value is None or pd.isna(fill_value) else fill_value)

    for column in categorical_features:
        values = engineered[column] if column in engineered.columns else "unknown"
        X[column] = values
        fill_value = context.categorical_fill_values.get(column, "unknown") or "unknown"
        X[column] = X[column].fillna(fill_value).astype("category")

    return X


def _predict_market_model(
    model: Any,
    X: pd.DataFrame,
    market_index: pd.Series,
    *,
    reference_index: float,
    fallback_predictions: np.ndarray,
) -> np.ndarray:
    normalized_predictions = np.expm1(model.predict(X))
    return denormalize_market_predictions(
        normalized_predictions,
        market_index,
        reference_index=reference_index,
        fallback_predictions=fallback_predictions,
    )


def _fit_tier_models(
    X: pd.DataFrame,
    y: pd.Series,
    y_normalized: pd.Series,
    train_index: pd.Series,
    valid_market: pd.Series,
    categorical_features: list[str],
    *,
    tier_specs: tuple[TierSpec, ...],
    random_state: int,
) -> dict[str, Any | None]:
    models: dict[str, Any | None] = {}
    for tier_spec in tier_specs:
        valid_tier = valid_market & _tier_mask(y, tier_spec)
        if valid_tier.sum() < 100:
            models[tier_spec.name] = None
            continue
        models[tier_spec.name] = _train_lgbm(
            X.loc[valid_tier],
            y_normalized.loc[valid_tier],
            categorical_features,
            random_state,
        )
    return models


def _select_blend(
    raw_frame: pd.DataFrame,
    feature_set: str,
    n_splits: int,
    random_state: int,
    tier_specs: tuple[TierSpec, ...],
    weight_step: float,
    min_segment_rows: int,
    include_calibration_features: bool = False,
) -> dict[str, object]:
    oof = _build_oof_training_data(
        raw_frame,
        feature_set=feature_set,
        n_splits=n_splits,
        random_state=random_state,
        tier_specs=tier_specs,
        include_calibration_features=include_calibration_features,
    )
    global_selection = select_best_market_blend_weight(
        oof["actual_price"].to_numpy(),
        oof["base_prediction"].to_numpy(),
        oof["normalized_prediction"].to_numpy(),
    )
    oof_global_blend = blend_market_predictions(
        oof["base_prediction"].to_numpy(),
        oof["normalized_prediction"].to_numpy(),
        normalized_weight=global_selection["normalized_weight"],
    )
    oof_predictions = _prediction_frame(
        global_predictions=oof_global_blend,
        tier_predictions={
            tier_spec.name: oof[f"{tier_spec.name}_prediction"].to_numpy()
            for tier_spec in tier_specs
        },
    )
    overall_selection = select_best_expert_weights(
        oof["actual_price"].to_numpy(),
        oof_predictions,
        weight_step=weight_step,
        model_names=MODEL_NAMES,
    )
    oof_gate = prediction_tier_labels(oof_global_blend)
    gated_selection = select_gated_expert_weights(
        oof["actual_price"].to_numpy(),
        oof_predictions,
        oof_gate,
        fallback_weights=overall_selection["weights"],
        weight_step=weight_step,
        min_segment_rows=min_segment_rows,
        model_names=MODEL_NAMES,
    )
    return {
        "global": global_selection,
        "overall_ensemble": overall_selection,
        "gated_ensemble": gated_selection,
        "oof": oof,
    }


def _oof_final_blend(
    model: TieredProductionModel,
    oof: pd.DataFrame,
    tier_specs: tuple[TierSpec, ...],
) -> np.ndarray:
    """Reproduce the model's gated-blend prediction on the out-of-fold rows."""
    global_blend = blend_market_predictions(
        oof["base_prediction"].to_numpy(dtype=float),
        oof["normalized_prediction"].to_numpy(dtype=float),
        normalized_weight=model.market_blend_weight,
    )
    expert_predictions = _prediction_frame(
        global_predictions=global_blend,
        tier_predictions={
            spec.name: oof[f"{spec.name}_prediction"].to_numpy(dtype=float)
            for spec in tier_specs
        },
    )
    gate = prediction_tier_labels(
        global_blend,
        low_max=model.gate_low_max,
        high_min=model.gate_high_min,
    )
    return apply_gated_expert_blend(
        expert_predictions,
        gate,
        model.gated_weights_by_gate,
        fallback_weights=model.fallback_weights,
    )


def _fit_model_residual_calibrator(
    model: TieredProductionModel,
    oof: pd.DataFrame,
    tier_specs: tuple[TierSpec, ...],
    random_state: int,
):
    """Fit a residual calibrator on genuinely out-of-fold gated-blend residuals."""
    oof_final = _oof_final_blend(model, oof, tier_specs)
    features = build_calibration_features(oof, oof_final)
    features["residual"] = oof["actual_price"].to_numpy(dtype=float) - oof_final
    return _fit_residual_calibrator(features, random_state=random_state)


def _metrics_payload(
    model: TieredProductionModel,
    *,
    heldout_metrics: dict[str, float],
    calibration: dict[str, object],
    train_rows: int,
    test_rows: int,
    production_rows: int,
    test_start: str,
    test_end: str,
) -> dict[str, object]:
    return {
        "model_id": model.model_id,
        "model_type": model.model_type,
        "feature_set": model.feature_set,
        "requires_listing_price": model.requires_listing_price,
        "served_prediction": calibration["served"],
        "mae": heldout_metrics["mae"],
        "rmse": heldout_metrics["rmse"],
        "mape": heldout_metrics["mape"],
        "median_ape": heldout_metrics["median_ape"],
        "within_10_pct": heldout_metrics["within_10_pct"],
        "within_20_pct": heldout_metrics["within_20_pct"],
        "features_used": model.numeric_features + model.categorical_features,
        "numeric_features": model.numeric_features,
        "categorical_features": model.categorical_features,
        "heldout": heldout_metrics,
        "calibration": calibration,
        "n_train": train_rows,
        "n_test": test_rows,
        "production_n_train": production_rows,
        "test_start": test_start,
        "test_end": test_end,
        "market_blend_weight": model.market_blend_weight,
        "overall_weights": model.overall_weights,
        "gated_weights_by_gate": model.gated_weights_by_gate,
    }


def _calibration_report(
    model: TieredProductionModel,
    test_raw: pd.DataFrame,
    y_test: pd.Series,
    *,
    served: np.ndarray,
) -> dict[str, object]:
    """Compare calibrated vs uncalibrated heldout predictions for the served model.

    Makes the served prediction explicit and records the acceptance-gate signals:
    overall and high-end MAE/bias, underprediction rate, and the correction
    distribution. ``listing`` (no calibrator) reports ``served="uncalibrated"``.
    """
    has_calibrator = model.residual_calibrator is not None and model.model_id == NO_LIST_MODEL_ID
    if not has_calibrator:
        return {"served": "uncalibrated", "applied": False}

    y = y_test.to_numpy(dtype=float)
    calibrated = np.asarray(served, dtype=float)
    uncalibrated = np.asarray(model.predict(test_raw, apply_calibration=False), dtype=float)
    correction = calibrated - uncalibrated

    high_end = y >= REPORT_HIGH_END_MIN_PRICE
    central = test_raw.get("area")
    central_high_end = (
        high_end & central.astype("string").isin(CENTRAL_AREAS).to_numpy()
        if central is not None
        else np.zeros_like(high_end)
    )
    adjusted = np.abs(correction) > 1.0
    cap = np.minimum(
        model.calibration_max_abs,
        model.calibration_max_frac * np.abs(uncalibrated),
    )
    at_cap = adjusted & np.isclose(np.abs(correction), cap, rtol=1e-3, atol=1.0)
    adjusted_corrections = correction[adjusted]

    return {
        "served": "calibrated",
        "applied": True,
        "min_prediction_threshold": model.calibration_min_prediction,
        "max_abs": model.calibration_max_abs,
        "max_frac": model.calibration_max_frac,
        "uncalibrated": _served_metrics(y, uncalibrated),
        "calibrated": _served_metrics(y, calibrated),
        "high_end_12m": {
            "rows": int(high_end.sum()),
            "uncalibrated": _served_metrics(y[high_end], uncalibrated[high_end]),
            "calibrated": _served_metrics(y[high_end], calibrated[high_end]),
        },
        "central_high_end_12m": {
            "rows": int(central_high_end.sum()),
            "uncalibrated": _served_metrics(y[central_high_end], uncalibrated[central_high_end]),
            "calibrated": _served_metrics(y[central_high_end], calibrated[central_high_end]),
        },
        "correction": {
            "n_adjusted": int(adjusted.sum()),
            "share_adjusted": float(adjusted.mean()),
            "median": float(np.median(adjusted_corrections)) if adjusted.any() else 0.0,
            "p90": float(np.quantile(np.abs(adjusted_corrections), 0.90)) if adjusted.any() else 0.0,
            "p95": float(np.quantile(np.abs(adjusted_corrections), 0.95)) if adjusted.any() else 0.0,
            "share_at_cap": float(at_cap.sum() / adjusted.sum()) if adjusted.any() else 0.0,
        },
    }


def _served_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float] | None:
    if len(y_true) == 0:
        return None
    metrics = _prediction_metrics(pd.Series(y_true), y_pred)
    return {
        "mae": metrics["mae"],
        "median_ape": metrics["median_ape"],
        "within_10_pct": metrics["within_10_pct"],
        "within_20_pct": metrics["within_20_pct"],
        "mean_bias": metrics["mean_bias"],
        "median_bias": metrics["median_bias"],
        "underprediction_rate": metrics["underprediction_rate"],
    }


def _feature_importance_payload(model: TieredProductionModel) -> dict[str, object]:
    features = model.numeric_features + model.categorical_features

    def importance(estimator: Any) -> dict[str, float]:
        values = getattr(estimator, "feature_importances_", None)
        if values is None:
            return {}
        total = float(np.sum(values))
        if total <= 0:
            return {feature: float(value) for feature, value in zip(features, values, strict=False)}
        return {
            feature: float(value / total)
            for feature, value in zip(features, values, strict=False)
        }

    return {
        "base": importance(model.base_model),
        "normalized": importance(model.normalized_model),
        "tiers": {
            name: importance(estimator) if estimator is not None else {}
            for name, estimator in model.tier_models.items()
        },
    }
