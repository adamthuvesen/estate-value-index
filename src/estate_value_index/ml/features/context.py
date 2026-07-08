from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

"""Feature engineering context and timestamp helpers."""


@dataclass
class FeatureEngineeringContext:
    """Cached statistics required to reproduce training-time features during inference.

    This context is built during training and saved with the model to ensure
    consistent feature engineering during prediction.
    """

    reference_date: pd.Timestamp
    area_avg_price: dict[str, float]
    area_listing_count: dict[str, float]
    area_price_tier: dict[str, str]
    area_target_mean: dict[str, float]
    global_target_mean: float
    global_listing_price_mean: float
    area_median_price_1m: dict[str, float]
    area_median_price_3m: dict[str, float]
    area_median_price_6m: dict[str, float]
    area_median_price_12m: dict[str, float]
    area_sales_volume_1m: dict[str, float]
    area_sales_volume_3m: dict[str, float]
    area_sales_volume_6m: dict[str, float]
    area_sales_volume_12m: dict[str, float]
    global_area_median_price_1m: float
    global_area_median_price_3m: float
    global_area_median_price_6m: float
    global_area_median_price_12m: float
    numeric_fill_values: dict[str, float | None]
    categorical_fill_values: dict[str, str]
    area_market_stats: dict[str, dict[str, float]] = None
    micro_area_stats_res10: dict[str, dict[str, float]] = None
    micro_area_stats_res9: dict[str, dict[str, float]] = None
    area_ppsqm_stats: dict[str, dict[str, float]] = None
    same_size_stats_h3_res9: dict[str, dict[str, float]] = None
    same_size_stats_area: dict[str, dict[str, float]] = None
    same_size_stats_global: dict[str, dict[str, float]] = None
    street_area_ppsqm_stats: dict[str, dict[str, float]] = None
    street_size_ppsqm_stats: dict[str, dict[str, float]] = None
    address_ppsqm_stats: dict[str, dict[str, float]] = None
    global_ppsqm_median: float | None = None


def _to_naive_timestamp(value: pd.Timestamp | None) -> pd.Timestamp:
    """Convert timestamp to timezone-naive, defaulting to now if None."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return pd.Timestamp.now(tz=None)

    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts


def _ensure_timestamp(value: Any, index: Any, fallback: pd.Timestamp) -> pd.Series:
    """Ensure a value is a valid timestamp Series."""
    series = pd.to_datetime(value, errors="coerce")
    if not isinstance(series, pd.Series):
        series = pd.Series(series, index=index, dtype="datetime64[ns]")
    if series.isna().all():
        series = pd.Series(fallback, index=index, dtype="datetime64[ns]")
    if getattr(series.dt, "tz", None) is not None:
        series = series.dt.tz_convert("UTC").dt.tz_localize(None)
    return series
