from __future__ import annotations

import numpy as np
import pandas as pd

from estate_value_index.ml.constants import AGE_BUCKET_BINS, AGE_BUCKET_LABELS
from estate_value_index.ml.features.classifiers import (
    _classify_architectural_era,
    _classify_renovation_likelihood,
    _get_construction_quality_score,
)
from estate_value_index.ml.features.heuristics import _estimate_energy_efficiency_series
from estate_value_index.ml.features.utils import _coerce_nullable_bool, _safe_divide

"""Basic, amenity, and architectural feature builders."""


def _create_basic_features(df: pd.DataFrame, current_year: int) -> pd.DataFrame:
    """Create basic property features (ratios, age, polynomials)."""
    if "price_per_sqm" in df.columns and "_observed_price_per_sqm" not in df.columns:
        df["_observed_price_per_sqm"] = pd.to_numeric(df["price_per_sqm"], errors="coerce")

    # Coerce key numeric columns for robust downstream math
    numeric_cols = [
        "listing_price",
        "living_area",
        "monthly_fee",
        "rooms",
        "construction_year",
        "floor",
    ]
    for column in numeric_cols:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    if "floor" not in df.columns:
        df["floor"] = np.nan

    # Core ratio features
    df["price_per_sqm"] = _safe_divide(df.get("listing_price"), df.get("living_area"), df.index)
    df["monthly_fee_per_sqm"] = _safe_divide(df.get("monthly_fee"), df.get("living_area"), df.index)
    df["floor_per_sqm"] = _safe_divide(df.get("floor"), df.get("living_area"), df.index)

    # Property age
    if "construction_year" in df.columns:
        df["property_age"] = current_year - df["construction_year"]
    else:
        df["property_age"] = np.nan

    # Polynomial features
    df["living_area_squared"] = df["living_area"] ** 2

    df["age_bucket"] = pd.cut(df["property_age"], bins=AGE_BUCKET_BINS, labels=AGE_BUCKET_LABELS)

    return df


def _create_amenity_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create smart features for amenities (elevator, balcony) and floor level.

    Encoding strategy:
    - Boolean features: has_elevator, has_balcony (categorical)
    - Numeric features: floor (as-is), floor_height_premium (non-linear encoding)
    - Categorical features: floor_tier (low/mid/high)
    - Composite score: amenity_score (combines all amenities)
    """
    # Ensure amenity columns exist
    if "elevator" not in df.columns:
        df["elevator"] = False
    if "balcony" not in df.columns:
        df["balcony"] = False
    if "floor" not in df.columns:
        df["floor"] = np.nan

    # Coerce via the canonical truth-table so scraped 'no' / 'nej' stay False
    # and unrecognised tokens fall through to the conservative default below.
    # 'unknown' / NA -> False (treated as amenity-absent for has_* mapping).
    df["elevator"] = _coerce_nullable_bool(df["elevator"]).fillna(False).astype(bool)
    df["balcony"] = _coerce_nullable_bool(df["balcony"]).fillna(False).astype(bool)

    df["has_elevator"] = df["elevator"].map({True: "yes", False: "no"})
    df["has_balcony"] = df["balcony"].map({True: "yes", False: "no"})

    # Log-scaled floor premium (diminishing returns at higher floors)
    df["floor_height_premium"] = df["floor"].apply(
        lambda x: np.log1p(x) if pd.notna(x) and x > 0 else 0
    )

    def categorize_floor(floor):
        if pd.isna(floor):
            return "unknown"
        elif floor <= 0:
            return "ground"  # Ground floor (less desirable)
        elif floor <= 2:
            return "low"  # Floors 1-2
        elif floor <= 5:
            return "mid"  # Floors 3-5 (most desirable)
        else:
            return "high"  # Floors 6+ (elevator-dependent)

    df["floor_tier"] = df["floor"].apply(categorize_floor)

    # Amenity score: weighted sum with floor-elevator interactions
    amenity_score = df["elevator"].astype(float) * 1.5 + df["balcony"].astype(float) * 1.0
    df["floor_no_null"] = df["floor"].fillna(0)
    high_floor_no_elevator = (df["floor_no_null"] > 3) & (~df["elevator"])
    low_floor_with_elevator = (df["floor_no_null"] <= 2) & (df["elevator"])
    amenity_score -= high_floor_no_elevator.astype(float) * 0.8
    amenity_score -= low_floor_with_elevator.astype(float) * 0.3
    df["amenity_score"] = amenity_score

    return df


def _create_architectural_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create features related to construction quality and energy efficiency."""
    # Architectural era classification
    df["architectural_era"] = df["construction_year"].apply(_classify_architectural_era)

    # Construction quality score
    df["construction_quality_score"] = df["architectural_era"].apply(
        _get_construction_quality_score
    )

    # Energy efficiency estimation: vectorised lookup over `construction_year`
    # bins and `living_area` bins. Replaces a `df.apply(axis=1, ...)` that
    # called Python per row.
    df["energy_efficiency_est"] = _estimate_energy_efficiency_series(
        df.get("construction_year"), df.get("living_area")
    )

    # Renovation likelihood
    df["renovation_likelihood"] = df["property_age"].apply(_classify_renovation_likelihood)

    return df
