"""Build reusable feature-engineering context from training data."""

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
from estate_value_index.ml.features.context import FeatureEngineeringContext
from estate_value_index.ml.features.registry import (
    CATEGORICAL_FEATURE_NAMES,
    NUMERIC_FEATURE_NAMES,
)

logger = logging.getLogger(__name__)


def _resolve_reference_date(training_frame: pd.DataFrame) -> pd.Timestamp:
    """Anchor relative-time features to sold_date, then scraped_at, then now."""
    sold = training_frame.get("sold_date")
    reference_date = sold.dropna().max() if sold is not None else None
    if reference_date is None or pd.isna(reference_date):
        scraped = training_frame.get("scraped_at")
        reference_date = scraped.dropna().max() if scraped is not None else None
    if reference_date is None or pd.isna(reference_date):
        reference_date = pd.Timestamp.now()
    return pd.Timestamp(reference_date)


def _price_tier(avg_price: float) -> str:
    if avg_price > PRICE_TIER_LUXURY:
        return "ultra_premium"
    if avg_price > PRICE_TIER_PREMIUM:
        return "premium"
    if avg_price > PRICE_TIER_HIGH:
        return "upper"
    if avg_price > PRICE_TIER_MID:
        return "medium"
    return "affordable"


def _area_avg_price(training_frame: pd.DataFrame) -> dict[str, float]:
    return (
        training_frame.groupby("area", dropna=False, observed=True)["listing_price"]
        .mean()
        .dropna()
        .to_dict()
    )


def _area_listing_count(training_frame: pd.DataFrame) -> dict[str, int]:
    return training_frame.groupby("area", dropna=False, observed=True).size().to_dict()


def _area_target_mean(training_frame: pd.DataFrame) -> tuple[float, dict[str, float]]:
    if "sold_price" not in training_frame.columns:
        return float("nan"), {}

    return (
        float(training_frame["sold_price"].mean()),
        (
            training_frame.groupby("area", dropna=False, observed=True)["sold_price"]
            .mean()
            .dropna()
            .to_dict()
        ),
    )


def _latest_area_metric(training_frame: pd.DataFrame, column: str) -> dict[str, float]:
    if column not in training_frame.columns:
        return {}

    subset = training_frame[["area", "sold_date", column]].dropna(subset=["area", column]).copy()
    if subset.empty:
        return {}

    subset = subset.sort_values(["area", "sold_date"])
    latest = subset.groupby("area", observed=True)[column].last().dropna()
    return latest.astype(float).to_dict()


def _global_median(training_frame: pd.DataFrame, column: str, default: float) -> float:
    if column in training_frame.columns:
        median_val = training_frame[column].median()
        if pd.notna(median_val):
            return float(median_val)
    return default


def _fill_values(
    training_frame: pd.DataFrame,
) -> tuple[dict[str, float | None], dict[str, str]]:
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

    return numeric_fill_values, categorical_fill_values


def _float_or_default(value: Any, default: float) -> float:
    return float(value) if pd.notna(value) else default


def _area_market_stats(training_frame: pd.DataFrame) -> dict[str, dict[str, float]]:
    if "area" not in training_frame.columns or "listing_price" not in training_frame.columns:
        return {}

    try:
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

        has_price_change = "price_change" in training_frame.columns
        if has_price_change:
            agg_dict["price_change"] = ["mean", "count"]
            col_names.extend(["area_price_change_mean", "area_price_change_count"])

        market_stats_df = training_frame.groupby("area", observed=True).agg(agg_dict)
        market_stats_df.columns = col_names
    except (KeyError, ValueError) as exc:
        logger.warning("Failed to build area market stats: %s. Using empty stats.", exc)
        return {}

    area_market_stats = {}
    for area in market_stats_df.index:
        stats = {
            "area_inventory": _float_or_default(market_stats_df.loc[area, "area_inventory"], 50.0),
            "area_price_volatility": _float_or_default(
                market_stats_df.loc[area, "area_price_volatility"], 500000.0
            ),
            "area_price_median": _float_or_default(
                market_stats_df.loc[area, "area_price_median"], 5000000.0
            ),
            "area_days_on_market_median": _float_or_default(
                market_stats_df.loc[area, "area_days_on_market_median"], 20.0
            ),
        }
        if has_price_change:
            stats["area_price_change_mean"] = _float_or_default(
                market_stats_df.loc[area, "area_price_change_mean"], 350000.0
            )
            stats["area_price_change_count"] = _float_or_default(
                market_stats_df.loc[area, "area_price_change_count"], 10.0
            )
        else:
            stats["area_price_change_mean"] = 350000.0
            stats["area_price_change_count"] = 10.0
        area_market_stats[area] = stats

    return area_market_stats


def build_feature_context(training_frame: pd.DataFrame) -> FeatureEngineeringContext:
    """Create a reusable context with statistics derived from the training data.

    The reference date is anchored to the latest non-null ``sold_date`` so that
    "days since" features track label time, not scrape time. Falls back to
    ``scraped_at.max()`` only if every row has a NaT ``sold_date``, and to
    ``pd.Timestamp.now()`` only when both columns are unusable.
    """
    area_avg_price = _area_avg_price(training_frame)
    global_target_mean, area_target_mean = _area_target_mean(training_frame)
    numeric_fill_values, categorical_fill_values = _fill_values(training_frame)

    return FeatureEngineeringContext(
        reference_date=_resolve_reference_date(training_frame),
        area_avg_price=area_avg_price,
        area_listing_count=_area_listing_count(training_frame),
        area_price_tier={
            area: _price_tier(avg_price) for area, avg_price in area_avg_price.items()
        },
        area_target_mean=area_target_mean,
        global_target_mean=global_target_mean,
        global_listing_price_mean=float(training_frame["listing_price"].mean()),
        area_median_price_1m=_latest_area_metric(training_frame, "area_sold_price_median_1m"),
        area_median_price_3m=_latest_area_metric(training_frame, "area_sold_price_median_3m"),
        area_median_price_6m=_latest_area_metric(training_frame, "area_sold_price_median_6m"),
        area_median_price_12m=_latest_area_metric(training_frame, "area_sold_price_median_12m"),
        area_sales_volume_1m=_latest_area_metric(training_frame, "area_sales_volume_1m"),
        area_sales_volume_3m=_latest_area_metric(training_frame, "area_sales_volume_3m"),
        area_sales_volume_6m=_latest_area_metric(training_frame, "area_sales_volume_6m"),
        area_sales_volume_12m=_latest_area_metric(training_frame, "area_sales_volume_12m"),
        global_area_median_price_1m=_global_median(
            training_frame, "area_sold_price_median_1m", 5000000.0
        ),
        global_area_median_price_3m=_global_median(
            training_frame, "area_sold_price_median_3m", 5000000.0
        ),
        global_area_median_price_6m=_global_median(
            training_frame, "area_sold_price_median_6m", 5000000.0
        ),
        global_area_median_price_12m=_global_median(
            training_frame, "area_sold_price_median_12m", 5000000.0
        ),
        numeric_fill_values=numeric_fill_values,
        categorical_fill_values=categorical_fill_values,
        area_market_stats=_area_market_stats(training_frame),
    )
