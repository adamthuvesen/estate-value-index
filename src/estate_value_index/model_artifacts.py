"""Shared production model artifact contract."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_MODEL_PREFIX = "price_prediction_model"
NO_LIST_MODEL_ID = "no_list_price"
LISTING_MODEL_ID = "with_list_price"
PRODUCTION_MODEL_IDS = (NO_LIST_MODEL_ID, LISTING_MODEL_ID)


@dataclass(frozen=True)
class ProductionArtifactNames:
    model_id: str
    stem: str
    model: str
    sidecar: str
    metrics: str
    context: str
    importance: str

    @property
    def files(self) -> tuple[str, ...]:
        return (self.model, self.sidecar, self.context, self.metrics, self.importance)


def production_artifact_names(
    model_id: str, model_prefix: str = DEFAULT_MODEL_PREFIX
) -> ProductionArtifactNames:
    if model_id not in PRODUCTION_MODEL_IDS:
        raise ValueError(f"Unknown production model id: {model_id}")

    stem = f"{model_prefix}_{model_id}"
    model = f"{stem}.joblib"
    return ProductionArtifactNames(
        model_id=model_id,
        stem=stem,
        model=model,
        sidecar=f"{model}.sha256",
        metrics=f"{stem}_metrics.json",
        context=f"{stem}_feature_context.json",
        importance=f"{stem}_feature_importance.json",
    )


def production_model_files(model_prefix: str = DEFAULT_MODEL_PREFIX) -> dict[str, str]:
    return {
        model_id: production_artifact_names(model_id, model_prefix).model
        for model_id in PRODUCTION_MODEL_IDS
    }


def required_production_artifact_files(model_prefix: str = DEFAULT_MODEL_PREFIX) -> tuple[str, ...]:
    return tuple(
        filename
        for model_id in PRODUCTION_MODEL_IDS
        for filename in production_artifact_names(model_id, model_prefix).files
    )
