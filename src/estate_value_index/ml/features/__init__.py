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
from estate_value_index.ml.features.utils import coerce_nullable_bool, safe_divide

__all__ = [
    "ALL_FEATURE_NAMES",
    "CATEGORICAL_FEATURE_NAMES",
    "NUMERIC_FEATURE_NAMES",
    "FeatureEngineeringContext",
    "SimplePredictionPipeline",
    "build_feature_context",
    "coerce_nullable_bool",
    "create_optimized_features",
    "get_categorical_indices",
    "get_feature_lists",
    "handle_missing_values",
    "safe_divide",
]
