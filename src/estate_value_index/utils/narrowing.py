"""Narrow loosely typed JSON values to the type the caller needs."""

from collections.abc import Mapping
from typing import Any

import pandas as pd


def number(record: Mapping[str, Any], key: str) -> float | None:
    """Return ``record[key]`` when it is an int or float, otherwise None."""
    value = record.get(key)
    return value if isinstance(value, int | float) else None


def is_missing(value: object) -> bool:
    """True for None, NaN, NaT, and pd.NA. pandas accepts any scalar; its stubs say less."""
    scalar: Any = value
    return bool(pd.isna(scalar))
