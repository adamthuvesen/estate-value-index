from __future__ import annotations

import numpy as np
import pandas as pd

from estate_value_index.ml.features.utils import safe_divide

"""Interaction and composite feature builders."""

CENTRAL_LUXURY_AREAS = frozenset({"ostermalm", "vasastan", "sodermalm", "kungsholmen", "norrmalm"})


def create_interaction_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create interaction and composite features."""
    # Property efficiency features
    df["rooms_per_sqm"] = safe_divide(df.get("rooms"), df.get("living_area"), df.index)
    df["fee_efficiency"] = safe_divide(df.get("monthly_fee"), df.get("living_area"), df.index)
    total_cost = _feature_series(df, "monthly_fee") * 12 + _feature_series(df, "listing_price")
    df["total_cost_per_sqm"] = safe_divide(total_cost, df.get("living_area"), df.index)

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
    price_norm = safe_divide(
        df["price_per_sqm"], price_median if price_median else np.nan, df.index
    )
    area_norm = safe_divide(
        df["living_area"], living_area_median if living_area_median else np.nan, df.index
    )
    df["luxury_score"] = price_norm * area_norm * (df["construction_quality_score"] / 10)
    df["value_score"] = safe_divide(
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
    df["price_acceleration_3m"] = safe_divide(
        df.get("area_sold_price_median_1m", 0) - df.get("area_sold_price_median_3m", 0),
        df.get("area_sold_price_median_3m", 1),
        df.index,
    )
    total_ownership_cost = _feature_series(df, "listing_price") + (
        df.get("monthly_fee", 0) * 12 * 5
    )
    df["cost_benefit_ratio"] = safe_divide(
        df.get("living_area", 1) * df.get("energy_efficiency_est", 5),
        total_ownership_cost,
        df.index,
    )
    trend_1m = safe_divide(
        df.get("area_sold_price_median_1m"), df.get("area_sold_price_median_3m", 1), df.index
    )
    trend_3m = safe_divide(
        df.get("area_sold_price_median_3m"), df.get("area_sold_price_median_6m", 1), df.index
    )
    df["temporal_price_trend"] = (trend_1m + trend_3m) / 2
    base_price_per_sqm = df.get("price_per_sqm", 0)
    efficiency_factor = df.get("energy_efficiency_est", 5) / 10
    quality_factor = df.get("construction_quality_score", 5) / 10
    df["efficiency_premium"] = base_price_per_sqm * efficiency_factor * quality_factor
    df["demand_supply_ratio"] = safe_divide(
        df.get("area_sales_volume_3m", 0), df.get("area_inventory", 50), df.index
    )
    df = _create_luxury_tier_features(df)

    return df


def _create_luxury_tier_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create inference-safe high-end proxy features from prior comp signals."""
    market_ppsqm = _feature_series(df, "market_ppsqm_index")

    df["h3_market_ppsqm_ratio"] = safe_divide(
        _feature_series(df, "micro_area_ppsqm_median"),
        market_ppsqm,
        df.index,
    ).replace([np.inf, -np.inf], np.nan)
    df["same_size_market_ppsqm_ratio"] = safe_divide(
        _feature_series(df, "same_size_ppsqm_median"),
        market_ppsqm,
        df.index,
    ).replace([np.inf, -np.inf], np.nan)
    df["neighbor_market_ppsqm_ratio"] = safe_divide(
        _feature_series(df, "h3_neighbor_ppsqm"),
        market_ppsqm,
        df.index,
    ).replace([np.inf, -np.inf], np.nan)

    area = _feature_series(df, "area")
    central = area.astype("string").str.lower().isin(CENTRAL_LUXURY_AREAS)

    living_area = pd.to_numeric(_feature_series(df, "living_area"), errors="coerce")
    size_component = ((living_area - 70.0) / 70.0).clip(lower=0.0, upper=1.0).fillna(0.0)
    micro_component = _ratio_component(df["h3_market_ppsqm_ratio"], low=0.90, high=1.35)
    same_size_component = _ratio_component(
        df["same_size_market_ppsqm_ratio"],
        low=0.90,
        high=1.35,
    )
    neighbor_component = _ratio_component(
        df["neighbor_market_ppsqm_ratio"],
        low=0.90,
        high=1.35,
    )

    luxury_score = (
        micro_component * 0.42
        + same_size_component * 0.22
        + neighbor_component * 0.14
        + central.astype(float) * 0.12
        + size_component * 0.10
    )
    df["micro_luxury_score"] = luxury_score.clip(0.0, 1.0).fillna(0.0)
    df["luxury_location_flag"] = (df["micro_luxury_score"] >= 0.65).astype(float)
    df["luxury_location_tier"] = pd.cut(
        df["micro_luxury_score"],
        bins=[-0.01, 0.25, 0.50, 0.75, 1.01],
        labels=["standard", "strong", "premium", "luxury"],
    ).astype("object")

    return df


def _ratio_component(values: pd.Series, *, low: float, high: float) -> pd.Series:
    ratio = pd.to_numeric(values, errors="coerce")
    return ((ratio - low) / (high - low)).clip(lower=0.0, upper=1.0).fillna(0.0)


def _feature_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(np.nan, index=df.index)
    return _first_column(df[column])


def _first_column(selected: pd.Series | pd.DataFrame) -> pd.Series:
    """``df[column]`` is a DataFrame when the frame has duplicate column names."""
    return selected.iloc[:, 0] if isinstance(selected, pd.DataFrame) else selected
