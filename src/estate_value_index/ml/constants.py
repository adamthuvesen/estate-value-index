"""Constants for ML feature engineering.

Centralizes magic numbers and configuration values to prevent drift
and make tuning easier.
"""

import numpy as np

# Price tier boundaries (SEK) for area classification
PRICE_TIER_LUXURY = 7_000_000
PRICE_TIER_PREMIUM = 6_000_000
PRICE_TIER_HIGH = 5_000_000
PRICE_TIER_MID = 4_000_000

# Minimum valid price threshold (SEK) for filtering listings
MIN_VALID_PRICE = 3_000_000

# Default fallback values when data is missing
DEFAULT_MEDIAN_PRICE = 5_000_000.0
DEFAULT_AREA_INVENTORY = 50.0
DEFAULT_PRICE_VOLATILITY = 500_000.0
DEFAULT_DAYS_ON_MARKET = 20.0
DEFAULT_PRICE_CHANGE = 350_000.0  # Typical Stockholm premium

# Building age bucket boundaries (years)
AGE_BUCKET_BINS: tuple[float, ...] = (-np.inf, 10, 30, np.inf)
AGE_BUCKET_LABELS: tuple[str, ...] = ("new", "modern", "old")

# Rooms per sqm efficiency bins
ROOMS_EFFICIENCY_BINS: tuple[float, ...] = (-np.inf, 0.03, 0.06, 0.10, np.inf)
ROOMS_EFFICIENCY_LABELS: tuple[str, ...] = ("spacious", "normal", "compact", "dense")

# Quantiles for normalization
AREA_LIQUIDITY_QUANTILE = 0.95

# Target encoding smoothing parameter
TARGET_ENCODING_SMOOTHING = 10

# Swedish energy efficiency ratings (A-G scale)
ENERGY_EFFICIENCY_SCORES: dict[str, float] = {
    "A": 9.0,
    "B": 7.5,
    "C": 6.0,
    "D": 4.5,
    "E": 3.0,
    "F": 1.5,
    "G": 0.0,
}

# Temporal window definitions (days, suffix)
TEMPORAL_WINDOWS: tuple[tuple[int, str], ...] = (
    (30, "1m"),
    (90, "3m"),
    (180, "6m"),
    (365, "12m"),
)

# Feature weights for composite scores
LOCATION_SCORE_WEIGHTS = {
    "relative_area_price": 0.35,
    "area_liquidity": 0.15,
    "distance_to_center": 0.25,
    "area_volatility_score": 0.25,
}

DESIRABILITY_SCORE_WEIGHTS = {
    "luxury_score": 0.25,
    "location_score": 0.25,
    "efficiency_quality_score": 0.20,
    "amenity_score": 0.15,
    "market_timing_score": 0.15,
}
