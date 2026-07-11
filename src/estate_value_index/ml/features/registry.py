from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

"""Feature name registry and missing-value handling."""

NUMERIC_FEATURE_NAMES: tuple[str, ...] = (
    # Original core features
    "listing_price",
    "living_area",
    "rooms",
    "monthly_fee",
    "construction_year",
    "property_age",
    "price_per_sqm",
    "monthly_fee_per_sqm",
    "living_area_squared",
    # Area temporal features
    "area_sold_price_median_1m",
    "area_sold_price_median_3m",
    "area_sold_price_median_6m",
    "area_sold_price_median_12m",
    "area_sales_volume_1m",
    "area_sales_volume_3m",
    "area_sales_volume_6m",
    "area_sales_volume_12m",
    # Temporal features (observation-time only). Listing-time and seasonality
    # features require a true listing/publish date, which the source does not
    # provide; they can be added if that date becomes available.
    "days_since_scraped",
    # Property efficiency features
    "rooms_per_sqm",
    "fee_efficiency",
    "total_cost_per_sqm",
    # Phase 1: Enhanced spatial features
    "distance_to_center",
    "distance_to_city_center",  # True geocoding-based distance (meters)
    "distance_to_nearest_metro",
    "distance_to_nearest_train",
    "metro_stations_within_500m",
    "metro_stations_within_1km",
    "transit_accessibility_score",
    "area_inventory",
    "area_price_volatility",
    "area_price_median",
    "area_days_on_market_median",
    "area_price_change_mean",
    "area_price_change_count",
    "area_liquidity",
    "relative_area_price",
    "area_volatility_score",
    "micro_area_ppsqm_median",
    "micro_area_ppsqm_p75",
    "micro_area_ppsqm_p90",
    "micro_area_ppsqm_count",
    "micro_area_ppsqm_premium_vs_area",
    "micro_area_upper_tail_ratio",
    "h3_neighbor_ppsqm",
    "h3_neighbor_ppsqm_p75",
    "h3_neighbor_ppsqm_p90",
    "h3_neighbor_ppsqm_count",
    "h3_neighbor_premium_vs_micro",
    "h3_neighbor_upper_tail_ratio",
    "same_size_ppsqm_median",
    "same_size_ppsqm_p75",
    "same_size_ppsqm_p90",
    "same_size_ppsqm_count",
    "same_size_premium_vs_area",
    "same_size_upper_tail_ratio",
    "street_area_ppsqm_median",
    "street_area_ppsqm_p75",
    "street_area_ppsqm_p90",
    "street_area_ppsqm_count",
    "street_area_premium_vs_micro",
    "street_area_upper_tail_ratio",
    "street_size_ppsqm_median",
    "street_size_ppsqm_p75",
    "street_size_ppsqm_p90",
    "street_size_ppsqm_count",
    "street_size_premium_vs_street",
    "street_size_upper_tail_ratio",
    "address_ppsqm_median",
    "address_ppsqm_p75",
    "address_ppsqm_p90",
    "address_ppsqm_count",
    "address_premium_vs_street",
    "address_upper_tail_ratio",
    "h3_market_ppsqm_ratio",
    "same_size_market_ppsqm_ratio",
    "neighbor_market_ppsqm_ratio",
    "micro_luxury_score",
    "luxury_location_flag",
    "market_interest_rate",
    "market_interest_rate_change_3m",
    "market_economic_tendency",
    "market_consumer_confidence",
    "market_construction_confidence",
    "market_gdp_growth",
    "market_ppsqm_index",
    "market_ppsqm_index_change_3m",
    "market_sales_volume",
    "market_months_since_2020",
    "market_data_age_months",
    # Phase 3: Advanced architectural features
    "construction_quality_score",
    "energy_efficiency_est",
    # Amenity features
    "floor",
    "floor_height_premium",
    "amenity_score",
    # Advanced interaction features (original)
    "area_age_interaction",
    "rooms_age_interaction",
    "fee_price_interaction",
    "luxury_score",
    "value_score",
    "floor_per_sqm",
    # Enhanced interactions (property/area/quality combinations).
    "area_location_score",
    "efficiency_quality_score",
    "size_era_interaction",
    "rooms_efficiency_interaction",
    "enhancement_potential",
    # New features inspired by top performers
    "price_acceleration_3m",
    "cost_benefit_ratio",
    "temporal_price_trend",
    "efficiency_premium",
    "demand_supply_ratio",
    # Location-based features
    "area_avg_price",
    "area_listing_count",
    "area_target_encoded",
    # Description-derived features
    "description_length",
    "description_word_count",
    "is_renovated",
    "has_modern_kitchen",
    "has_modern_bathroom",
    "has_view",
    "is_quiet_location",
    "needs_renovation",
    "luxury_keyword_count",
    "condition_score",
    "premium_score",
)

CATEGORICAL_FEATURE_NAMES: tuple[str, ...] = (
    # Original categorical features
    "area",
    "age_bucket",
    "space_efficiency",
    "area_price_tier",
    "h3_res10",
    "h3_res9",
    "micro_area_resolution_used",
    "same_size_scope_used",
    "street_name",
    "street_area_scope_used",
    "street_size_scope_used",
    "address_comp_scope_used",
    "luxury_location_tier",
    # Area price momentum (derived from past-only area price-change stats)
    "area_price_momentum",
    # Phase 3: Advanced architectural features
    "architectural_era",
    "renovation_likelihood",
    # Amenity features (categorical)
    "has_elevator",
    "has_balcony",
    "floor_tier",
)

ALL_FEATURE_NAMES = NUMERIC_FEATURE_NAMES + CATEGORICAL_FEATURE_NAMES


def get_feature_lists() -> tuple[list[str], list[str], list[str]]:
    """Get feature lists for model training."""
    return (list(NUMERIC_FEATURE_NAMES), list(CATEGORICAL_FEATURE_NAMES), list(ALL_FEATURE_NAMES))


def handle_missing_values(
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
    numeric_features: list[str],
    categorical_features: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float], dict[str, str]]:
    """Handle missing values consistently across train and test sets.

    Uses consistent imputation strategies:
    - Numeric: median (or 0 if all null)
    - Categorical: mode (or 'unknown')
    """
    X_train = X_train.copy()
    X_test = X_test.copy()

    numeric_fill_values = {}
    for col in numeric_features:
        if col in X_train.columns:
            valid_values = X_train[col].dropna()
            median_val = valid_values.median() if not valid_values.empty else pd.NA
            fill_val = median_val if pd.notna(median_val) else 0

            # Handle Int64 (nullable integer) dtype - must use integer fill value
            col_dtype = X_train[col].dtype
            if pd.api.types.is_integer_dtype(col_dtype):
                fill_val = int(round(fill_val))

            numeric_fill_values[col] = fill_val
            X_train.loc[:, col] = X_train[col].fillna(fill_val)
            if col in X_test.columns:
                X_test.loc[:, col] = X_test[col].fillna(fill_val)

    categorical_fill_values = {}
    for col in categorical_features:
        if col in X_train.columns:
            mode_val = X_train[col].mode()[0] if not X_train[col].mode().empty else "unknown"
            if pd.isna(mode_val):
                mode_val = "unknown"
            fill_val = mode_val
            categorical_fill_values[col] = str(fill_val)

            filled_train = X_train[col].astype("object").fillna(fill_val)
            X_train[col] = filled_train.infer_objects(copy=False).astype("category")
            if col in X_test.columns:
                filled_test = X_test[col].astype("object").fillna(fill_val)
                X_test[col] = filled_test.infer_objects(copy=False).astype("category")

    return X_train, X_test, numeric_fill_values, categorical_fill_values


def get_categorical_indices(X: pd.DataFrame, categorical_features: Sequence[str]) -> list[int]:
    """Get indices of categorical features in the feature matrix."""
    categorical_indices: list[int] = []
    for i, col in enumerate(X.columns):
        if col in categorical_features:
            categorical_indices.append(i)
        elif isinstance(X[col].dtype, pd.CategoricalDtype):
            categorical_indices.append(i)
    return categorical_indices
