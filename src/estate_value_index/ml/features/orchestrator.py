"""Feature engineering orchestration entrypoints."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from estate_value_index.ml.constants import (
    PRICE_TIER_HIGH,
    PRICE_TIER_LUXURY,
    PRICE_TIER_MID,
    PRICE_TIER_PREMIUM,
)
from estate_value_index.ml.features.basic import (
    _create_amenity_features,
    _create_architectural_features,
    _create_basic_features,
)
from estate_value_index.ml.features.context import FeatureEngineeringContext, _to_naive_timestamp
from estate_value_index.ml.features.interactions import _create_interaction_features
from estate_value_index.ml.features.registry import (
    CATEGORICAL_FEATURE_NAMES,
    NUMERIC_FEATURE_NAMES,
)
from estate_value_index.ml.features.spatial import _create_spatial_features
from estate_value_index.ml.features.target_encoding import _create_target_encoding
from estate_value_index.ml.features.temporal import _create_temporal_features

logger = logging.getLogger(__name__)


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
    5. Interaction features (composite scores)
    6. Target encoding (area-level pricing)

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
    df = _create_interaction_features(df)
    df = _create_target_encoding(df, context)

    return df


def build_feature_context(training_frame: pd.DataFrame) -> FeatureEngineeringContext:
    """Create a reusable context with statistics derived from the training data.

    The reference date is anchored to the latest non-null ``sold_date`` so that
    "days since" features track label time, not scrape time. Falls back to
    ``scraped_at.max()`` only if every row has a NaT ``sold_date``, and to
    ``pd.Timestamp.now()`` only when both columns are unusable.
    """
    sold = training_frame.get("sold_date")
    reference_date = sold.dropna().max() if sold is not None else None
    if reference_date is None or pd.isna(reference_date):
        scraped = training_frame.get("scraped_at")
        reference_date = scraped.dropna().max() if scraped is not None else None
    if reference_date is None or pd.isna(reference_date):
        reference_date = pd.Timestamp.now()

    # Area average prices
    area_avg_price = (
        training_frame.groupby("area", dropna=False, observed=True)["listing_price"]
        .mean()
        .dropna()
        .to_dict()
    )
    global_listing_price_mean = float(training_frame["listing_price"].mean())

    # Area listing counts
    area_listing_count = (
        training_frame.groupby("area", dropna=False, observed=True).size().to_dict()
    )

    # Area price tiers
    area_price_tier: dict[str, str] = {}
    for area, avg_price in area_avg_price.items():
        if avg_price > PRICE_TIER_LUXURY:
            tier = "ultra_premium"
        elif avg_price > PRICE_TIER_PREMIUM:
            tier = "premium"
        elif avg_price > PRICE_TIER_HIGH:
            tier = "upper"
        elif avg_price > PRICE_TIER_MID:
            tier = "medium"
        else:
            tier = "affordable"
        area_price_tier[area] = tier

    # Target encoding statistics
    global_target_mean = float("nan")
    area_target_mean: dict[str, float] = {}
    if "sold_price" in training_frame.columns:
        global_target_mean = float(training_frame["sold_price"].mean())
        area_target_mean = (
            training_frame.groupby("area", dropna=False, observed=True)["sold_price"]
            .mean()
            .dropna()
            .to_dict()
        )

    # Rolling area metrics
    def _latest_area_metric(column):
        if column not in training_frame.columns:
            return {}
        subset = (
            training_frame[["area", "sold_date", column]].dropna(subset=["area", column]).copy()
        )
        if subset.empty:
            return {}
        subset = subset.sort_values(["area", "sold_date"])
        latest = subset.groupby("area", observed=True)[column].last().dropna()
        return latest.astype(float).to_dict()

    area_median_price_1m = _latest_area_metric("area_sold_price_median_1m")
    area_median_price_3m = _latest_area_metric("area_sold_price_median_3m")
    area_median_price_6m = _latest_area_metric("area_sold_price_median_6m")
    area_median_price_12m = _latest_area_metric("area_sold_price_median_12m")
    area_sales_volume_1m = _latest_area_metric("area_sales_volume_1m")
    area_sales_volume_3m = _latest_area_metric("area_sales_volume_3m")
    area_sales_volume_6m = _latest_area_metric("area_sales_volume_6m")
    area_sales_volume_12m = _latest_area_metric("area_sales_volume_12m")

    def _global_median(column: str, default: float) -> float:
        if column in training_frame.columns:
            median_val = training_frame[column].median()
            if pd.notna(median_val):
                return float(median_val)
        return default

    global_area_median_price_1m = _global_median("area_sold_price_median_1m", 5000000.0)
    global_area_median_price_3m = _global_median("area_sold_price_median_3m", 5000000.0)
    global_area_median_price_6m = _global_median("area_sold_price_median_6m", 5000000.0)
    global_area_median_price_12m = _global_median("area_sold_price_median_12m", 5000000.0)

    # Missing value fill statistics
    numeric_fill_values = {}
    categorical_fill_values = {}

    for col in NUMERIC_FEATURE_NAMES:
        if col in training_frame.columns:
            median_val = training_frame[col].median()
            numeric_fill_values[col] = float(median_val) if pd.notna(median_val) else None

    for col in CATEGORICAL_FEATURE_NAMES:
        if col in training_frame.columns:
            mode_series = training_frame[col].mode()
            mode_val = mode_series.iloc[0] if not mode_series.empty else None
            categorical_fill_values[col] = str(mode_val) if mode_val is not None else "unknown"

    # Build area market statistics for enhanced spatial features
    area_market_stats = {}
    if "area" in training_frame.columns and "listing_price" in training_frame.columns:
        try:
            # Build aggregation dict conditionally based on available columns
            agg_dict: dict[str, Any] = {
                "listing_price": ["count", "std", "median"],
                "days_on_market": "median",
            }
            col_names = [
                "area_inventory",
                "area_price_volatility",
                "area_price_median",
                "area_days_on_market_median",
            ]

            # Only include price_change if column exists
            has_price_change = "price_change" in training_frame.columns
            if has_price_change:
                agg_dict["price_change"] = ["mean", "count"]
                col_names.extend(["area_price_change_mean", "area_price_change_count"])

            market_stats_df = training_frame.groupby("area", observed=True).agg(agg_dict)
            market_stats_df.columns = col_names

            for area in market_stats_df.index:
                stats = {
                    "area_inventory": float(market_stats_df.loc[area, "area_inventory"])
                    if pd.notna(market_stats_df.loc[area, "area_inventory"])
                    else 50.0,
                    "area_price_volatility": float(
                        market_stats_df.loc[area, "area_price_volatility"]
                    )
                    if pd.notna(market_stats_df.loc[area, "area_price_volatility"])
                    else 500000.0,
                    "area_price_median": float(market_stats_df.loc[area, "area_price_median"])
                    if pd.notna(market_stats_df.loc[area, "area_price_median"])
                    else 5000000.0,
                    "area_days_on_market_median": float(
                        market_stats_df.loc[area, "area_days_on_market_median"]
                    )
                    if pd.notna(market_stats_df.loc[area, "area_days_on_market_median"])
                    else 20.0,
                }
                # Add price_change stats if available, otherwise use defaults
                if has_price_change:
                    stats["area_price_change_mean"] = (
                        float(market_stats_df.loc[area, "area_price_change_mean"])
                        if pd.notna(market_stats_df.loc[area, "area_price_change_mean"])
                        else 350000.0
                    )
                    stats["area_price_change_count"] = (
                        float(market_stats_df.loc[area, "area_price_change_count"])
                        if pd.notna(market_stats_df.loc[area, "area_price_change_count"])
                        else 10.0
                    )
                else:
                    stats["area_price_change_mean"] = 350000.0
                    stats["area_price_change_count"] = 10.0
                area_market_stats[area] = stats
        except (KeyError, ValueError) as e:
            logger.warning("Failed to build area market stats: %s. Using empty stats.", e)
            area_market_stats = {}

    return FeatureEngineeringContext(
        reference_date=pd.Timestamp(reference_date),
        area_avg_price=area_avg_price,
        area_listing_count=area_listing_count,
        area_price_tier=area_price_tier,
        area_target_mean=area_target_mean,
        global_target_mean=global_target_mean,
        global_listing_price_mean=global_listing_price_mean,
        area_median_price_1m=area_median_price_1m,
        area_median_price_3m=area_median_price_3m,
        area_median_price_6m=area_median_price_6m,
        area_median_price_12m=area_median_price_12m,
        area_sales_volume_1m=area_sales_volume_1m,
        area_sales_volume_3m=area_sales_volume_3m,
        area_sales_volume_6m=area_sales_volume_6m,
        area_sales_volume_12m=area_sales_volume_12m,
        global_area_median_price_1m=global_area_median_price_1m,
        global_area_median_price_3m=global_area_median_price_3m,
        global_area_median_price_6m=global_area_median_price_6m,
        global_area_median_price_12m=global_area_median_price_12m,
        numeric_fill_values=numeric_fill_values,
        categorical_fill_values=categorical_fill_values,
        area_market_stats=area_market_stats,
    )
