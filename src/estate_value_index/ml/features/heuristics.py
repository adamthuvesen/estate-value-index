from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

"""Heuristic spatial and energy estimates."""


def _estimate_energy_efficiency(year: Any, area: Any) -> float:
    """Estimate energy efficiency based on construction year and size."""
    if pd.isna(year) or pd.isna(area):
        return 5.0  # Default medium efficiency

    year = int(year)
    if year >= 2010:
        base_score = 9.0  # Very energy efficient
    elif year >= 2000:
        base_score = 7.5  # Good efficiency
    elif year >= 1990:
        base_score = 6.0  # Moderate efficiency
    elif year >= 1980:
        base_score = 5.0  # Lower efficiency
    elif year >= 1970:
        base_score = 4.0  # Poor efficiency (often renovated)
    else:
        base_score = 6.0  # Older buildings often renovated

    # Adjust for size (smaller units easier to heat efficiently)
    if area < 40:
        size_bonus = 1.0
    elif area < 60:
        size_bonus = 0.5
    elif area > 80:
        size_bonus = -0.5
    else:
        size_bonus = 0.0

    return min(10.0, max(1.0, base_score + size_bonus))


def _estimate_energy_efficiency_series(
    years: pd.Series | None, areas: pd.Series | None
) -> pd.Series:
    """Vectorised twin of :func:`_estimate_energy_efficiency`.

    Same bin boundaries and same default-on-NaN behaviour, but operates on
    whole columns at once so it doesn't pay Python-per-row overhead. The
    scalar function is kept so callers and tests outside the DataFrame path
    keep working.
    """
    if years is None or areas is None:
        # No source columns → match the scalar default for every row.
        index = (
            years.index
            if isinstance(years, pd.Series)
            else (areas.index if isinstance(areas, pd.Series) else pd.RangeIndex(0))
        )
        return pd.Series(5.0, index=index, dtype=float)

    # Coerce to plain numpy float arrays. BigQuery columns arrive as pandas
    # nullable Int64/Float64; comparisons on those return a nullable `boolean`
    # extension dtype, which numpy 2.x's np.select rejects.
    year_arr = pd.to_numeric(years, errors="coerce").to_numpy(dtype="float64", na_value=np.nan)
    area_arr = pd.to_numeric(areas, errors="coerce").to_numpy(dtype="float64", na_value=np.nan)

    # Year-based base score: bins mirror the scalar function's elif ladder.
    base = np.select(
        condlist=[
            year_arr >= 2010,
            year_arr >= 2000,
            year_arr >= 1990,
            year_arr >= 1980,
            year_arr >= 1970,
            ~np.isnan(year_arr),  # pre-1970, but year still known
        ],
        choicelist=[9.0, 7.5, 6.0, 5.0, 4.0, 6.0],
        default=np.nan,
    )

    # Size adjustment: bins mirror the scalar function's <40 / <60 / >80 branches.
    size_bonus = np.select(
        condlist=[
            area_arr < 40,
            area_arr < 60,
            area_arr > 80,
        ],
        choicelist=[1.0, 0.5, -0.5],
        default=0.0,
    )

    raw = base + size_bonus
    clipped = np.clip(raw, 1.0, 10.0)

    # If either input is NaN the scalar function returns 5.0; preserve that.
    missing = np.isnan(year_arr) | np.isnan(area_arr)
    result = np.where(missing, 5.0, clipped)
    return pd.Series(result, index=years.index, dtype=float)


def _calculate_distance_to_center(area_string: Any) -> float:
    """Calculate approximate distance score from Stockholm city center."""
    if pd.isna(area_string) or not isinstance(area_string, str):
        return 5.0  # Default medium distance

    area_lower = area_string.lower()
    # Central areas (very close to city center)
    if any(term in area_lower for term in ["gamla stan", "norrmalm", "city", "östermalm central"]):
        return 1.0
    # Inner areas (close to city center)
    elif any(term in area_lower for term in ["östermalm", "södermalm", "vasastan", "kungsholmen"]):
        return 2.0
    # Mid-distance areas
    elif any(
        term in area_lower for term in ["djurgården", "marieberg", "söder", "north stockholm"]
    ):
        return 3.0
    # Outer Stockholm areas
    elif any(
        term in area_lower for term in ["vällingby", "rinkeby", "tensta", "farsta", "skärholmen"]
    ):
        return 4.5
    # Suburban/outer areas
    elif any(term in area_lower for term in ["täby", "danderyd", "nacka", "huddinge", "solna"]):
        return 5.5
    else:
        return 5.0  # Default medium distance
