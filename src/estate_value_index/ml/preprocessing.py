"""Preprocessing helpers for Booli listing regression."""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from estate_value_index.ingestion.booli.normalization import extract_area_token

from .constants import MIN_VALID_PRICE
from .features import CATEGORICAL_FEATURE_NAMES, NUMERIC_FEATURE_NAMES

_SWEDISH_CHAR_MAP = {"ö": "o", "ä": "a", "å": "a", "Ö": "o", "Ä": "a", "Å": "a"}


def transliterate_swedish(text: object) -> str | None:
    """Convert Swedish characters to ASCII equivalents and clean for LightGBM compatibility.

    Returns None for missing values to preserve NA semantics in tests/pipelines.
    """
    if pd.isna(text):
        return None

    text = str(text).lower()
    for swedish_char, ascii_char in _SWEDISH_CHAR_MAP.items():
        text = text.replace(swedish_char, ascii_char)

    text = re.sub(r"[^a-zA-Z0-9_]", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_")


def extract_area_name(area_string: object) -> str | None:
    """Extract the ASCII area key from a Booli ``Type · Area · Municipality`` string.

    Tokenisation delegates to :func:`extract_area_token` (the single shared
    implementation between ingestion and ML); this layer transliterates the
    extracted token to the slug the model expects. Returns None for missing
    inputs to preserve NA semantics used by tests.
    """
    if pd.isna(area_string):
        return None

    token = extract_area_token(area_string)
    if not token:
        return None
    return transliterate_swedish(token)


def normalize_area_for_model(area: object, *, empty_for_unknown: bool = False) -> str:
    """Return the area key used in training and inference (ASCII slug, Booli-safe).

    Handles Booli-style ``Lägenhet · Södermalm · Stockholm`` via ``extract_area_name``.

    Args:
        area: Raw area string (any Booli-shaped or pre-cleaned value).
        empty_for_unknown: When True, map missing/unknown areas to ``""`` instead
            of ``"unknown"`` — useful for keys that need to be join-safe (e.g. the
            geocode join in feature materialization, where ``"unknown"`` would
            produce a sentinel match).
    """
    extracted = extract_area_name(area)
    if extracted is None or extracted == "":
        return "" if empty_for_unknown else "unknown"
    return extracted


def preprocess_area_field(frame: pd.DataFrame) -> pd.DataFrame:
    """Preprocess the area field to extract area names."""
    if "area" in frame.columns:
        frame = frame.copy()
        frame["area"] = frame["area"].apply(extract_area_name)
    return frame


@dataclass(frozen=True)
class FeatureSpec:
    numeric: list[str]
    categorical: list[str]
    target: str


def filter_valid_listings(
    frame: pd.DataFrame,
    *,
    min_price: int = MIN_VALID_PRICE,
    drop_na_features: bool = False,
    require_listing_price: bool = True,
) -> pd.DataFrame:
    """Drop listings that cannot be used for supervised learning."""

    required_columns = {"sold_price"}
    if require_listing_price:
        required_columns.add("listing_price")
    missing = required_columns.difference(frame.columns)
    if missing:
        raise KeyError(f"Missing required columns: {sorted(missing)}")

    filtered = frame.copy()
    if "listing_price" not in filtered.columns:
        filtered["listing_price"] = pd.NA

    # Preprocess area field to extract area names
    filtered = preprocess_area_field(filtered)

    mask = filtered["sold_price"].notna() & (filtered["sold_price"] >= min_price)
    if require_listing_price:
        mask &= filtered["listing_price"].notna() & (filtered["listing_price"] >= min_price)

    filtered = filtered.loc[mask]

    if drop_na_features:
        feature_columns = set(NUMERIC_FEATURE_NAMES + CATEGORICAL_FEATURE_NAMES)
        existing_features = feature_columns.intersection(filtered.columns)
        filtered = filtered.dropna(subset=list(existing_features))

    return filtered.reset_index(drop=True)


def prepare_features(
    frame: pd.DataFrame,
    *,
    feature_spec: FeatureSpec | None = None,
    target: str = "sold_price",
) -> tuple[pd.DataFrame, pd.Series, FeatureSpec]:
    """Split the dataset into features and target along with the feature spec."""

    if feature_spec is None:
        feature_spec = FeatureSpec(
            numeric=[col for col in NUMERIC_FEATURE_NAMES if col in frame.columns],
            categorical=[col for col in CATEGORICAL_FEATURE_NAMES if col in frame.columns],
            target=target,
        )

    missing_features = [
        col for col in feature_spec.numeric + feature_spec.categorical if col not in frame.columns
    ]
    if missing_features:
        raise KeyError(f"Missing expected feature columns: {missing_features}")
    if target not in frame.columns:
        raise KeyError(f"Missing target column '{target}'")

    X = frame[feature_spec.numeric + feature_spec.categorical].copy()
    y = frame[target].copy()

    return X, y, feature_spec


def drop_outliers_quantile(
    frame: pd.DataFrame,
    *,
    columns: list[str] | None = None,
    lower: float = 0.01,
    upper: float = 0.99,
) -> pd.DataFrame:
    """Drop rows where any selected numeric column lies outside [p01, p99]."""

    if not 0.0 <= lower < upper <= 1.0:
        raise ValueError("Quantile bounds must satisfy 0.0 <= lower < upper <= 1.0")

    if columns is None:
        candidate_cols = [c for c in NUMERIC_FEATURE_NAMES if c in frame.columns]
        if "sold_price" in frame.columns:
            candidate_cols.append("sold_price")
        columns = candidate_cols

    if not columns:
        return frame.reset_index(drop=True)

    work = frame.copy()
    bounds: dict[str, tuple[float, float]] = {}

    for col in columns:
        if col not in work.columns:
            continue
        work[col] = pd.to_numeric(work[col], errors="coerce")
        series = work[col].dropna()
        if series.empty:
            continue
        q_low = series.quantile(lower)
        q_high = series.quantile(upper)
        bounds[col] = (q_low, q_high)

    if not bounds:
        return frame.reset_index(drop=True)

    mask = pd.Series(True, index=work.index)
    for col, (lo, hi) in bounds.items():
        col_series = work[col]
        within_range = col_series.ge(lo) & col_series.le(hi)
        mask &= within_range | col_series.isna()

    return frame.loc[mask].reset_index(drop=True)
