"""Feature engineering orchestration entrypoints."""

from __future__ import annotations

import pandas as pd

from estate_value_index.ml.features.basic import (
    _create_amenity_features,
    _create_architectural_features,
    _create_basic_features,
)
from estate_value_index.ml.features.context import FeatureEngineeringContext, _to_naive_timestamp
from estate_value_index.ml.features.context_builder import build_feature_context
from estate_value_index.ml.features.interactions import _create_interaction_features
from estate_value_index.ml.features.market import create_market_features
from estate_value_index.ml.features.spatial import _create_spatial_features
from estate_value_index.ml.features.target_encoding import _create_target_encoding
from estate_value_index.ml.features.temporal import _create_temporal_features
from estate_value_index.ml.features.text import create_description_features

__all__ = ["build_feature_context", "create_optimized_features"]


def create_optimized_features(
    df: pd.DataFrame,
    context: FeatureEngineeringContext | None = None,
) -> pd.DataFrame:
    """Create comprehensive engineered features for price prediction.

    This function orchestrates all feature engineering in a logical order:
    1. Basic property features (ratios, age, etc.)
    2. Architectural features (era, quality, efficiency)
    3. Spatial features (location, distance, area dynamics)
    4. Temporal features (seasonality, market timing)
    5. Description features (renovation, condition, premium cues)
    6. Interaction features (composite scores)
    7. Target encoding (area-level pricing)

    Args:
        df: Raw property listings dataframe
        context: Optional context with training statistics for inference

    Returns:
        DataFrame with all engineered features added
    """
    df = df.copy()
    reference_date = _to_naive_timestamp(context.reference_date if context else None)
    current_year = reference_date.year

    df = _create_basic_features(df, current_year)
    df = _create_amenity_features(df)
    df = _create_architectural_features(df)
    df = _create_spatial_features(df, context)
    df = _create_temporal_features(df, reference_date)
    df = create_market_features(df, context)
    df = create_description_features(df)
    df = _create_interaction_features(df)
    df = _create_target_encoding(df, context)

    return df
