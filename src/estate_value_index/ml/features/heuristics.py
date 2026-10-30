from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

"""Heuristic spatial and energy estimates."""


def _estimate_energy_efficiency_series(
    years: pd.Series | None, areas: pd.Series | None
) -> pd.Series:
    """Estimate energy efficiency (1-10) per row from construction year and area.

    Rows with a missing year or area get the default score of 5.0.
    """
    if years is None or areas is None:
        # No source columns: every row gets the default score.
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

    # Year-based base score by construction-year bin.
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

    # Size adjustment by area bin: smaller units heat more efficiently.
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

    # A missing year or area gets the default score.
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
