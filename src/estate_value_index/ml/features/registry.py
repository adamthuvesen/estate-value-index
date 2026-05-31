from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from estate_value_index.ml.features.utils import _coerce_nullable_bool

"""Feature name registry and missing-value handling."""

NUMERIC_FEATURE_NAMES: tuple[str, ...] = (
    # Original core features
    "listing_price",
    "living_area",
    "rooms",
    "monthly_fee",
    "days_on_market",
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
    # Temporal features (listing-based only to avoid leakage)
    "days_since_scraped",
    "days_since_listed",
    "listed_month",
    "listed_quarter",
    "listed_weekday",
    "is_weekend_listing",
    "listed_month_sin",
    "listed_month_cos",
    "listed_quarter_sin",
    "listed_quarter_cos",
    # Phase 2: Advanced temporal features
    "is_tax_month",
    "is_summer_peak",
    "is_holiday_period",
    "market_timing_score",
    # Property efficiency features
    "rooms_per_sqm",
    "fee_efficiency",
    "total_cost_per_sqm",
    # Phase 1: Enhanced spatial features
    "distance_to_center",
    "distance_to_city_center",  # True geocoding-based distance (meters)
    "area_inventory",
    "area_price_volatility",
    "area_price_median",
    "area_days_on_market_median",
    "area_price_change_mean",
    "area_price_change_count",
    "area_liquidity",
    "relative_area_price",
    "area_volatility_score",
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
    # Phase 3: Enhanced interactions
    "area_location_score",
    "timing_location_interaction",
    "efficiency_quality_score",
    "size_era_interaction",
    "rooms_efficiency_interaction",
    "volatility_timing_interaction",
    "liquidity_season_interaction",
    "momentum_distance_interaction",
    "property_desirability_score",
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
)

CATEGORICAL_FEATURE_NAMES: tuple[str, ...] = (
    # Original categorical features
    "area",
    "age_bucket",
    "space_efficiency",
    "area_price_tier",
    # Phase 2: Advanced temporal features
    "market_cycle",
    "swedish_season",
    "school_period",
    "dom_momentum",
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

    Uses conservative imputation strategies:
    - Numeric: median (or 0 if all null)
    - Boolean (elevator, balcony): False (conservative assumption)
    - Categorical: mode (or 'unknown')
    """
    X_train = X_train.copy()
    X_test = X_test.copy()

    # Conservative defaults for boolean features (assume absence if unknown)
    BOOLEAN_FEATURES = {"elevator", "balcony"}
    BOOLEAN_DEFAULT = False
    BOOLEAN_DTYPE = pd.CategoricalDtype(categories=[False, True])

    numeric_fill_values = {}
    for col in numeric_features:
        if col in X_train.columns:
            median_val = X_train[col].median()
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
            # Use conservative False for boolean amenity features
            if col in BOOLEAN_FEATURES:
                fill_val = BOOLEAN_DEFAULT
                categorical_fill_values[col] = fill_val

                train_series = _coerce_nullable_bool(X_train[col]).fillna(fill_val)
                X_train.loc[:, col] = train_series.astype(BOOLEAN_DTYPE)

                if col in X_test.columns:
                    test_series = _coerce_nullable_bool(X_test[col]).fillna(fill_val)
                    X_test.loc[:, col] = test_series.astype(BOOLEAN_DTYPE)

                continue
            else:
                # Use mode for other categorical features
                mode_val = X_train[col].mode()[0] if not X_train[col].mode().empty else "unknown"
                if pd.isna(mode_val):
                    mode_val = "unknown"
                fill_val = mode_val
                categorical_fill_values[col] = str(fill_val)

            filled_train = X_train[col].fillna(fill_val)
            X_train.loc[:, col] = filled_train.infer_objects(copy=False).astype("category")
            if col in X_test.columns:
                filled_test = X_test[col].fillna(fill_val)
                X_test.loc[:, col] = filled_test.infer_objects(copy=False).astype("category")

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
