"""Feature engineering package for property price prediction.

The package's public API is re-exported here as the stable import surface.
"""

from estate_value_index.ml.features.context import FeatureEngineeringContext
from estate_value_index.ml.features.context_builder import build_feature_context
from estate_value_index.ml.features.orchestrator import (
    create_optimized_features,
)
from estate_value_index.ml.features.pipeline import SimplePredictionPipeline
from estate_value_index.ml.features.registry import (
    ALL_FEATURE_NAMES,
    CATEGORICAL_FEATURE_NAMES,
    NUMERIC_FEATURE_NAMES,
    get_categorical_indices,
    get_feature_lists,
    handle_missing_values,
)
from estate_value_index.ml.features.utils import _coerce_nullable_bool, _safe_divide

__all__ = [
    "FeatureEngineeringContext",
    "SimplePredictionPipeline",
    "build_feature_context",
    "create_optimized_features",
    "get_categorical_indices",
    "get_feature_lists",
    "handle_missing_values",
    "ALL_FEATURE_NAMES",
    "CATEGORICAL_FEATURE_NAMES",
    "NUMERIC_FEATURE_NAMES",
    "_coerce_nullable_bool",
    "_safe_divide",
]
