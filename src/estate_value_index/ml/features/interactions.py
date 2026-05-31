from __future__ import annotations

import numpy as np
import pandas as pd

from estate_value_index.ml.features.utils import _safe_divide

"""Interaction and composite feature builders."""


def _create_interaction_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create interaction and composite features."""
    # Property efficiency features
    df["rooms_per_sqm"] = _safe_divide(df.get("rooms"), df.get("living_area"), df.index)
    df["fee_efficiency"] = _safe_divide(df.get("monthly_fee"), df.get("living_area"), df.index)
    total_cost = df.get("monthly_fee") * 12 + df.get("listing_price")
    df["total_cost_per_sqm"] = _safe_divide(total_cost, df.get("living_area"), df.index)

    # Space utilization categories
    df["space_efficiency"] = pd.cut(
        df["rooms_per_sqm"],
        bins=[-np.inf, 0.03, 0.06, 0.10, np.inf],
        labels=["luxury_spacious", "spacious", "efficient", "cramped"],
    )

    # Higher-order interaction features
    df["area_location_score"] = df["distance_to_center"] * df["construction_quality_score"]
    df["timing_location_interaction"] = df["market_timing_score"] * df["area_liquidity"]

    df["efficiency_quality_score"] = df["energy_efficiency_est"] * df["construction_quality_score"]
    df["size_era_interaction"] = df["living_area"] * df["construction_quality_score"]
    df["rooms_efficiency_interaction"] = df["rooms_per_sqm"] * df["energy_efficiency_est"]
    df["volatility_timing_interaction"] = df["area_volatility_score"] * df["market_timing_score"]
    df["liquidity_season_interaction"] = df["area_liquidity"] * df["is_summer_peak"]
    df["momentum_distance_interaction"] = (df["dom_momentum"] == "hot_market").astype(int) * (
        5 - df["distance_to_center"]
    )

    df["area_age_interaction"] = df["living_area"] * df["property_age"]
    df["rooms_age_interaction"] = df["rooms"] * df["property_age"]
    df["fee_price_interaction"] = df["monthly_fee"] / (df["listing_price"] + 1)

    # Premium and value scores
    price_median = df["price_per_sqm"].median(skipna=True)
    living_area_median = df["living_area"].median(skipna=True)
    price_norm = _safe_divide(
        df["price_per_sqm"], price_median if price_median else np.nan, df.index
    )
    area_norm = _safe_divide(
        df["living_area"], living_area_median if living_area_median else np.nan, df.index
    )
    df["luxury_score"] = price_norm * area_norm * (df["construction_quality_score"] / 10)
    df["value_score"] = _safe_divide(
        df["living_area"], df["listing_price"] + df["monthly_fee"] * 12, df.index
    )

    # Composite desirability score (weighted factors)
    desirability = (
        df["construction_quality_score"] / 10 * 0.3
        + (6 - df["distance_to_center"]) / 5 * 0.25
        + df["energy_efficiency_est"] / 10 * 0.2
        + df["area_liquidity"] / df["area_liquidity"].quantile(0.95) * 0.15
        + (df["market_timing_score"] + 3) / 6 * 0.1
    )
    df["property_desirability_score"] = desirability.clip(0, 1)

    renovation_boost = (df["renovation_likelihood"] == "high").astype(int) * 0.1
    era_boost = (
        (df["architectural_era"] == "functionalism") | (df["architectural_era"] == "pre_war")
    ).astype(int) * 0.15
    location_boost = (df["stockholm_district"] == "central_stockholm").astype(int) * 0.2

    df["enhancement_potential"] = renovation_boost + era_boost + location_boost

    # Derived market indicators
    df["price_acceleration_3m"] = _safe_divide(
        df.get("area_sold_price_median_1m", 0) - df.get("area_sold_price_median_3m", 0),
        df.get("area_sold_price_median_3m", 1),
        df.index,
    )
    total_ownership_cost = df.get("listing_price") + (df.get("monthly_fee", 0) * 12 * 5)
    df["cost_benefit_ratio"] = _safe_divide(
        df.get("living_area", 1) * df.get("energy_efficiency_est", 5),
        total_ownership_cost,
        df.index,
    )
    trend_1m = _safe_divide(
        df.get("area_sold_price_median_1m"), df.get("area_sold_price_median_3m", 1), df.index
    )
    trend_3m = _safe_divide(
        df.get("area_sold_price_median_3m"), df.get("area_sold_price_median_6m", 1), df.index
    )
    df["temporal_price_trend"] = (trend_1m + trend_3m) / 2
    base_price_per_sqm = df.get("price_per_sqm", 0)
    efficiency_factor = df.get("energy_efficiency_est", 5) / 10
    quality_factor = df.get("construction_quality_score", 5) / 10
    df["efficiency_premium"] = base_price_per_sqm * efficiency_factor * quality_factor
    df["demand_supply_ratio"] = _safe_divide(
        df.get("area_sales_volume_3m", 0), df.get("area_inventory", 50), df.index
    )

    return df
