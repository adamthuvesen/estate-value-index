from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

"""Shared utilities for feature engineering."""

_COERCE_TRUTHY = {"true", "t", "yes", "y", "1", "ja"}
_COERCE_FALSY = {"false", "f", "no", "n", "0", "nej"}


def _coerce_nullable_bool(series: pd.Series) -> pd.Series:
    """Normalize heterogeneous truthy/falsy values to pandas nullable Boolean.

    Truth table matches `estate_value_index.ingestion.booli.normalization.to_bool`
    so the ingestion layer and the feature layer cannot disagree about whether
    `'no'` means False (it does) or `'unknown'` is a valid bool (it isn't).
    """

    def _convert(value):
        if pd.isna(value):
            return pd.NA
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            token = value.strip().lower()
            if token in _COERCE_TRUTHY:
                return True
            if token in _COERCE_FALSY:
                return False
            return pd.NA
        if isinstance(value, (int, np.integer)):
            return True if value == 1 else (False if value == 0 else pd.NA)
        return pd.NA

    converted = series.map(_convert)
    return converted.astype("boolean")


def _safe_divide(numerator: Any, denominator: Any, index: Any) -> pd.Series:
    """Safely divide two values, handling None and zero denominators."""
    if index is None:
        if hasattr(numerator, "index"):
            index = numerator.index
        elif hasattr(denominator, "index"):
            index = denominator.index
        else:
            index = (
                pd.RangeIndex(len(numerator)) if hasattr(numerator, "__len__") else pd.RangeIndex(1)
            )

    if numerator is None or denominator is None:
        return pd.Series(np.nan, index=index, dtype=float)

    if isinstance(numerator, pd.Series):
        numerator_series = pd.to_numeric(numerator, errors="coerce")
    else:
        numerator_series = pd.Series(numerator, index=index, dtype=float)

    if isinstance(denominator, pd.Series):
        denominator_series = pd.to_numeric(denominator, errors="coerce")
    else:
        denominator_series = pd.Series(denominator, index=index, dtype=float)

    denominator_series = denominator_series.replace(0, np.nan)
    result = numerator_series / denominator_series
    result[~np.isfinite(result)] = np.nan
    return result
