from __future__ import annotations

import re
from typing import Any

import pandas as pd

"""Classification helpers for engineered features."""


def _classify_architectural_era(construction_year: Any) -> str:
    """Classify properties by Swedish architectural eras with market characteristics."""
    if pd.isna(construction_year):
        return "unknown"

    year = int(construction_year)

    if year <= 1929:
        return "pre_war"  # Historic, often renovated, unique character
    elif year <= 1945:
        return "functionalism"  # Swedish functionalist architecture
    elif year <= 1965:
        return "post_war_boom"  # Post-war construction boom
    elif year <= 1975:
        return "million_programme"  # Million Programme era, mixed reputation
    elif year <= 1990:
        return "late_modern"  # Late modern, energy crisis improvements
    elif year <= 2005:
        return "contemporary"  # Contemporary construction
    elif year <= 2015:
        return "energy_efficient"  # Energy-efficient era
    else:
        return "newest"  # Latest construction, highest standards


def _get_construction_quality_score(era: str) -> int:
    """Assign construction quality scores based on architectural era."""
    quality_map = {
        "pre_war": 7,  # High character, often well-maintained
        "functionalism": 8,  # Classic Swedish design, well-built
        "post_war_boom": 6,  # Decent but rushed construction
        "million_programme": 4,  # Lower prestige, but improving
        "late_modern": 7,  # Better materials and methods
        "contemporary": 8,  # Good modern standards
        "energy_efficient": 9,  # High energy standards
        "newest": 10,  # Latest technology and standards
        "unknown": 5,
    }
    return quality_map.get(era, 5)


def _classify_renovation_likelihood(age: Any) -> str:
    """Classify renovation likelihood based on property age."""
    if pd.isna(age):
        return "low"
    if 30 <= age <= 50:
        return "high"
    elif 15 <= age <= 70:
        return "medium"
    else:
        return "low"


def _extract_postal_code(address: Any) -> str | None:
    """Extract Swedish postal codes (5 digits) from address string."""
    if pd.isna(address) or not isinstance(address, str):
        return None
    # Swedish postal codes are 5 digits (e.g., "11122", "101 23")
    match = re.search(r"\b(\d{3}\s?\d{2}|\d{5})\b", address)
    return match.group(1).replace(" ", "") if match else None


def _classify_stockholm_district(postal_code: Any) -> str:
    """Classify Stockholm districts based on postal code ranges."""
    if not postal_code or len(postal_code) != 5:
        return "unknown"
    try:
        code = int(postal_code)
        if 10000 <= code <= 11499:
            return "central_stockholm"  # Norrmalm, Gamla Stan, Södermalm, Östermalm
        elif 11500 <= code <= 11799:
            return "inner_south"  # Södermalm extended
        elif 11800 <= code <= 12599:
            return "kungsholmen_vasastan"  # Kungsholmen, Vasastan
        elif 12600 <= code <= 12799:
            return "inner_north"  # Östermalm extended
        elif 13000 <= code <= 16999:
            return "outer_stockholm"  # Suburbs and outer areas
        else:
            return "other_sweden"
    except (ValueError, TypeError):
        return "unknown"


def _classify_market_cycle(date_series: pd.Series) -> pd.Series:
    """Determine market cycle phase based on Swedish housing market patterns."""
    # Swedish housing market shows strong seasonality and multi-year cycles
    years = date_series.dt.year

    # Multi-year cycle (simplified 4-year cycle based on economic patterns)
    cycle_year = years % 4
    market_cycle = pd.Series("stable", index=date_series.index)
    market_cycle.loc[cycle_year == 0] = "downturn"  # Economic uncertainty years
    market_cycle.loc[cycle_year == 1] = "recovery"  # Recovery phase
    market_cycle.loc[cycle_year == 2] = "expansion"  # Growth phase
    market_cycle.loc[cycle_year == 3] = "peak"  # Peak phase

    return market_cycle


def _classify_swedish_season(month: int) -> str:
    """Get Swedish housing market seasons."""
    if month in [12, 1, 2]:
        return "winter_slow"  # Very slow market
    elif month in [3, 4]:
        return "spring_awakening"  # Market starts moving
    elif month in [5, 6, 7, 8]:
        return "summer_peak"  # Peak activity
    elif month in [9, 10]:
        return "autumn_rush"  # Second peak before winter
    else:  # November
        return "pre_winter"  # Market cooling


def _classify_school_period(month: int) -> str:
    """Classify months by Swedish school calendar impact."""
    if month in [6, 7]:
        return "summer_vacation"  # School holidays, family moving season
    elif month in [8, 9]:
        return "school_start"  # New school year, high activity
    elif month in [12, 1]:
        return "winter_break"  # Holiday period, low activity
    elif month in [3, 4]:
        return "spring_semester"  # Spring activity
    else:
        return "regular_period"


def _classify_dom_momentum(days_on_market: Any) -> str:
    """Classify days on market momentum."""
    if pd.isna(days_on_market):
        return "normal"
    if days_on_market <= 7:
        return "hot_market"
    elif days_on_market <= 21:
        return "normal"
    elif days_on_market <= 60:
        return "slow"
    else:
        return "stagnant"


def _classify_area_price_momentum(area_price_change_mean: Any) -> str:
    """Classify area price momentum based on typical price changes."""
    if pd.isna(area_price_change_mean):
        return "normal"

    if area_price_change_mean < 0:
        return "below_asking"
    elif area_price_change_mean < 250000:
        return "normal"
    elif area_price_change_mean < 500000:
        return "hot"
    elif area_price_change_mean < 750000:
        return "very_hot"
    elif area_price_change_mean < 1000000:
        return "extreme"
    else:
        return "bidding_war"
