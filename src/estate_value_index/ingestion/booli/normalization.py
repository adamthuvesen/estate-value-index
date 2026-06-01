"""Normalization helpers for Booli ingestion modules."""

from __future__ import annotations

import re

_TRUTHY = {"true", "t", "yes", "y", "1", "ja"}
_FALSY = {"false", "f", "no", "n", "0", "nej"}

_NBSP_VARIANTS = tuple(chr(c) for c in (0xA0, 0x202F, 0x2009, 0xFEFF))
_ESCAPED_NBSP_VARIANTS = ("\\xa0", "\\u202f", "\\u00a0", "&nbsp;")

_GENERIC_TOKENS = frozenset(
    {
        "stockholm",
        "stockholms län",
        "stockholms kommun",
        "stockholms stad",
        "län",
        "kommun",
        "stad",
        "lägenhet",
        "villa",
        "radhus",
        "bostadsrätt",
    }
)


def normalize_text(value: object) -> str:
    """Collapse whitespace, NBSP variants, and HTML entities to a single space."""

    if not value:
        return ""
    text = str(value)
    for literal in _ESCAPED_NBSP_VARIANTS:
        text = text.replace(literal, " ")
    for char in _NBSP_VARIANTS:
        text = text.replace(char, " ")
    return re.sub(r"\s+", " ", text).strip()


def is_generic_token(token: object) -> bool:
    """Return True for tokens that are property types or broad regions, not areas."""

    if not token:
        return True
    return str(token).strip().lower() in _GENERIC_TOKENS


def extract_area_token(area_field: object) -> str:
    """Extract the area name from a Booli ``Type · Area · Municipality`` string.

    Single source of truth for tokenisation: shared by ingestion-time cleaning
    (which keeps the Swedish-cased token) and ML-time normalisation (which
    transliterates to an ASCII slug).
    """

    if not area_field:
        return ""

    text = normalize_text(area_field)
    parts = re.split(r"\s*·\s*", text)

    if len(parts) >= 2:
        tokens = [t for t in parts if t]
        filtered = [t for t in tokens if not is_generic_token(t)]
        if filtered:
            return filtered[-1]
        if len(tokens) >= 3 and tokens[-1].lower() == "stockholm":
            return tokens[-2]
        return tokens[0]

    return text


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


def ensure_list(value: object) -> list:
    """Return a list, defaulting to ``[]`` when the value is falsy."""

    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


__all__ = [
    "clean_text",
    "to_int",
    "to_float",
    "to_bool",
    "ensure_list",
    "normalize_text",
    "is_generic_token",
    "extract_area_token",
]
