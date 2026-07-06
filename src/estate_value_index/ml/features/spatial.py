from __future__ import annotations

import numpy as np
import pandas as pd

from estate_value_index.ml.features.address_comps import create_address_comp_features
from estate_value_index.ml.features.area_market import (
    _create_area_market_features,
    _create_area_temporal_metrics,
)
from estate_value_index.ml.features.classifiers import (
    _classify_stockholm_district,
    _extract_postal_code,
)
from estate_value_index.ml.features.context import FeatureEngineeringContext
from estate_value_index.ml.features.heuristics import _calculate_distance_to_center
from estate_value_index.ml.features.micro_area import create_micro_area_features
from estate_value_index.ml.poi import create_poi_features

"""Spatial and location-based feature builders."""


def _create_spatial_features(
    df: pd.DataFrame, context: FeatureEngineeringContext | None
) -> pd.DataFrame:
    """Create location-based and area-level market features."""
    df = create_micro_area_features(df, context)
    df = create_address_comp_features(df, context)

    # Extract postal code information
    df["postal_code"] = df.get("address", pd.Series([None] * len(df), index=df.index)).apply(
        _extract_postal_code
    )
    df["postal_prefix"] = df["postal_code"].apply(lambda x: x[:3] if x and len(x) >= 3 else None)

    # District classification (based on postal code)
    df["stockholm_district"] = df["postal_code"].apply(_classify_stockholm_district)

    # Distance to center (heuristic based on area name)
    df["distance_to_center"] = df.get("area", pd.Series([None] * len(df), index=df.index)).apply(
        _calculate_distance_to_center
    )

    # POI/transit features (geocoding-based, if lat/lon available)
    if "lat" in df.columns and "lon" in df.columns:
        df = create_poi_features(df)
    else:
        df["distance_to_city_center"] = np.nan
        df["distance_to_nearest_metro"] = np.nan
        df["distance_to_nearest_train"] = np.nan
        df["metro_stations_within_500m"] = 0
        df["metro_stations_within_1km"] = 0
        df["transit_accessibility_score"] = np.nan

    # Area-level market microstructure (with leave-one-out during training)
    df = _create_area_market_features(df, context)

    # Area price tier classification
    df = _classify_area_price_tiers(df, context)

    # Rolling area sales metrics (temporal spatial features)
    df = _create_area_temporal_metrics(df, context)

    return df


def _classify_area_price_tiers(
    df: pd.DataFrame, context: FeatureEngineeringContext | None
) -> pd.DataFrame:
    """Classify areas into price tiers.

    Note: This only creates area_price_tier. The area_avg_price and area_listing_count
    features are created in _create_target_encoding.
    """
    # First get area_avg_price if we need to compute tiers
    if context and context.area_price_tier:
        df["area_price_tier"] = df["area"].map(context.area_price_tier).fillna("unknown")
    else:
        # Calculate temporary area average price for tier calculation
        if "area" in df.columns and "listing_price" in df.columns:
            temp_area_stats = df.groupby("area", dropna=False, observed=True)[
                "listing_price"
            ].mean()
            temp_area_avg = df["area"].map(temp_area_stats)

            # Create price tiers using qcut like the original
            if temp_area_avg.nunique(dropna=True) > 1:
                try:
                    n_bins = min(4, temp_area_avg.nunique())
                    tier_feature = pd.qcut(temp_area_avg, q=n_bins, duplicates="drop")
                    labels = ["budget", "mid", "premium", "luxury"][
                        : len(tier_feature.cat.categories)
                    ]
                    df["area_price_tier"] = tier_feature.cat.rename_categories(labels)
                except ValueError:
                    median_price = temp_area_avg.median(skipna=True)
                    df["area_price_tier"] = np.where(
                        temp_area_avg <= median_price, "budget", "premium"
                    )
            else:
                df["area_price_tier"] = "single_tier"
        else:
            df["area_price_tier"] = "unknown"

    return df
