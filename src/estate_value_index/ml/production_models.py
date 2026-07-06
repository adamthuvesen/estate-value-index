"""Production two-model training and inference.

The public serving contract has two model ids:

- ``no_list``: does not use asking price.
- ``listing``: uses asking price when it is available.
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
    _feature_set_requires_listing_price,
    _prediction_metrics,
    _resolve_features,
    _train_lgbm,
)
from estate_value_index.analytics.tiered_ensemble import (
    DEFAULT_GATE_HIGH_MIN,
    DEFAULT_GATE_LOW_MAX,
    DEFAULT_HIGH_MIN_PRICE,
    DEFAULT_LOW_MAX_PRICE,
    DEFAULT_MID_MAX_PRICE,
    DEFAULT_MID_MIN_PRICE,
    DEFAULT_MIN_SEGMENT_ROWS,
    DEFAULT_WEIGHT_STEP,
    MODEL_NAMES,
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
from estate_value_index.utils.gcs import (
    is_gcs_enabled,
    upload_model_artifacts,
    write_sha256_sidecar,
)
from estate_value_index.utils.settings import get_random_state, get_test_size

logger = logging.getLogger(__name__)

DEFAULT_MODEL_PREFIX = "price_prediction_model"
NO_LIST_MODEL_ID = "no_list"
LISTING_MODEL_ID = "listing"
DEFAULT_NO_LIST_FEATURE_SET = "no_list_price_h3_market_street_rfe25"
DEFAULT_LISTING_FEATURE_SET = "listing_price_h3_market_street_aligned30"
ASK_PRICE_COLUMNS = ("listing_price", "price_per_sqm", "relative_area_price", "price_change")


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
    """Serializable max/tiered production model."""

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
    gate_low_max: float = DEFAULT_GATE_LOW_MAX
    gate_high_min: float = DEFAULT_GATE_HIGH_MIN

    @property
    def model_type(self) -> str:
        return "tiered_max"

    def predict(self, X_raw: pd.DataFrame) -> np.ndarray:
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
        return apply_gated_expert_blend(
            expert_predictions,
            gate,
            self.gated_weights_by_gate,
            fallback_weights=self.fallback_weights,
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
        predictions = evaluation_model.predict(test_raw.reset_index(drop=True))
        heldout_metrics = _prediction_metrics(
            test_raw["sold_price"].reset_index(drop=True),
            predictions,
        )

        production_model = fit_tiered_production_model(
            filtered,
            spec=spec,
            n_splits=n_splits,
            random_state=seed,
        )
        metrics = _metrics_payload(
            production_model,
            heldout_metrics=heldout_metrics,
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
    low_max_price: float = DEFAULT_LOW_MAX_PRICE,
    mid_min_price: float = DEFAULT_MID_MIN_PRICE,
    mid_max_price: float = DEFAULT_MID_MAX_PRICE,
    high_min_price: float = DEFAULT_HIGH_MIN_PRICE,
    gate_low_max: float = DEFAULT_GATE_LOW_MAX,
    gate_high_min: float = DEFAULT_GATE_HIGH_MIN,
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
    blend = _select_blend(raw, spec.feature_set, n_splits, random_state, tier_specs, weight_step, min_segment_rows)

    return TieredProductionModel(
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


def persist_production_model(
    model: TieredProductionModel,
    *,
    model_dir: Path,
    model_prefix: str,
    metrics: dict[str, object],
) -> dict[str, str]:
    stem = f"{model_prefix}_{model.model_id}"
    model_path = model_dir / f"{stem}.joblib"
    metrics_path = model_dir / f"{stem}_metrics.json"
    context_path = model_dir / f"{stem}_feature_context.json"
    importance_path = model_dir / f"{stem}_feature_importance.json"

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
        upload_model_artifacts(model_dir, stem)

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
) -> dict[str, object]:
    oof = _build_oof_training_data(
        raw_frame,
        feature_set=feature_set,
        n_splits=n_splits,
        random_state=random_state,
        tier_specs=tier_specs,
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
    }


def _metrics_payload(
    model: TieredProductionModel,
    *,
    heldout_metrics: dict[str, float],
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
        "mae": heldout_metrics["mae"],
        "rmse": heldout_metrics["rmse"],
        "mape": heldout_metrics["mape"],
        "within_10_pct": heldout_metrics["within_10_pct"],
        "features_used": model.numeric_features + model.categorical_features,
        "numeric_features": model.numeric_features,
        "categorical_features": model.categorical_features,
        "heldout": heldout_metrics,
        "n_train": train_rows,
        "n_test": test_rows,
        "production_n_train": production_rows,
        "test_start": test_start,
        "test_end": test_end,
        "market_blend_weight": model.market_blend_weight,
        "overall_weights": model.overall_weights,
        "gated_weights_by_gate": model.gated_weights_by_gate,
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
