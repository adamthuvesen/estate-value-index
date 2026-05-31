from __future__ import annotations

import numpy as np
import pandas as pd

from estate_value_index.ml.features.classifiers import (
    _classify_dom_momentum,
    _classify_market_cycle,
    _classify_school_period,
    _classify_swedish_season,
)
from estate_value_index.ml.features.context import _ensure_timestamp

"""Temporal and seasonality feature builders."""


def _create_temporal_features(df: pd.DataFrame, reference_date: pd.Timestamp) -> pd.DataFrame:
    """Create time-based features including seasonality and market timing."""
    # Parse dates - use scraped_at and derive listing_date from days_on_market
    fallback_timestamp = reference_date
    df["sold_date"] = _ensure_timestamp(df.get("sold_date"), df.index, fallback_timestamp)
    df["scraped_at"] = _ensure_timestamp(df.get("scraped_at"), df.index, fallback_timestamp)

    # Calculate listing_date from scraped_at and days_on_market
    if "days_on_market" in df.columns:
        days_on_market = pd.to_numeric(df["days_on_market"], errors="coerce").fillna(0)
    else:
        days_on_market = 0
    df["listing_date"] = df["scraped_at"] - pd.to_timedelta(days_on_market, unit="days")

    # Market timing features based on available information
    df["days_since_scraped"] = (reference_date - df["scraped_at"]).dt.days
    df["days_since_listed"] = (reference_date - df["listing_date"]).dt.days

    # Listing timing features
    df["listed_month"] = df["listing_date"].dt.month
    df["listed_quarter"] = df["listing_date"].dt.quarter
    df["listed_weekday"] = df["listing_date"].dt.weekday
    df["is_weekend_listing"] = df["listed_weekday"].isin([5, 6]).astype(int)

    # Cyclical encoding for months and quarters
    df["listed_month_sin"] = np.sin(2 * np.pi * df["listed_month"] / 12)
    df["listed_month_cos"] = np.cos(2 * np.pi * df["listed_month"] / 12)
    df["listed_quarter_sin"] = np.sin(2 * np.pi * df["listed_quarter"] / 4)
    df["listed_quarter_cos"] = np.cos(2 * np.pi * df["listed_quarter"] / 4)

    # Note: a listing's own sold_* fields are not used as features; only its
    # listing-time attributes. Other properties' historical sold_dates feed the
    # area statistics (area_sold_price_median_*).

    # Market cycle based on listing_date (uses year-based cycle)
    df["market_cycle"] = _classify_market_cycle(df["listing_date"])
    df["swedish_season"] = df["listed_month"].apply(_classify_swedish_season)
    df["school_period"] = df["listed_month"].apply(_classify_school_period)

    # Specific month indicators
    df["is_tax_month"] = df["listed_month"].isin([3, 4]).astype(int)
    df["is_summer_peak"] = df["listed_month"].isin([5, 6, 7, 8]).astype(int)
    df["is_holiday_period"] = df["listed_month"].isin([12, 1, 7]).astype(int)

    # Days on market momentum
    if "days_on_market" not in df.columns:
        df["days_on_market"] = 0
    df["dom_momentum"] = df["days_on_market"].apply(_classify_dom_momentum)

    # Market timing score (combines multiple temporal factors)
    timing_score = 0
    timing_score += (df["swedish_season"] == "summer_peak").astype(int) * 2
    timing_score += (df["school_period"] == "school_start").astype(int) * 1
    timing_score += df["is_summer_peak"] * 1
    timing_score -= df["is_holiday_period"] * 1
    timing_score -= (df["market_cycle"] == "downturn").astype(int) * 2
    df["market_timing_score"] = timing_score

    return df
