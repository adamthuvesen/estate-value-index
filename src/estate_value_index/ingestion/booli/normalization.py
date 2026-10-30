"""Normalization helpers for Booli ingestion modules."""

from __future__ import annotations

from typing import Any

_TRUTHY = {"true", "t", "yes", "y", "1", "ja"}
_FALSY = {"false", "f", "no", "n", "0", "nej"}


def clean_text(value: object) -> str | None:
    """Trim whitespace from text fields, returning None for empty values."""

    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value).strip() or None


def to_int(value: object) -> int | None:
    """Convert common numeric inputs to ``int``; return ``None`` on failure."""

    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        token = value.strip().replace(" ", "")
        if not token:
            return None
        try:
            return int(token)
        except ValueError:
            try:
                return int(float(token))
            except ValueError:
                return None
    return None


def to_float(value: object) -> float | None:
    """Convert common numeric inputs to ``float``; return ``None`` on failure."""

    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        token = value.strip().replace(" ", "").replace(",", ".")
        if not token:
            return None
        try:
            return float(token)
        except ValueError:
            return None
    return None


def to_bool(value: object) -> bool | None:
    """Normalise textual / numeric booleans to ``True``/``False``."""

    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
        return None
    if isinstance(value, str):
        token = value.strip().lower()
        if token in _TRUTHY:
            return True
        if token in _FALSY:
            return False
    return None


def ensure_list(value: object) -> list[Any]:
    """Return a list, defaulting to ``[]`` when the value is falsy."""

    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


__all__ = [
    "clean_text",
    "ensure_list",
    "to_bool",
    "to_float",
    "to_int",
]
