"""Preprocessing helpers for Booli listing regression."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from estate_value_index.areas import extract_area_name

from .constants import MIN_VALID_PRICE
from .features import CATEGORICAL_FEATURE_NAMES, NUMERIC_FEATURE_NAMES


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
        bounds[col] = (float(q_low), float(q_high))

    if not bounds:
        return frame.reset_index(drop=True)

    mask = pd.Series(True, index=work.index)
    for col, (lo, hi) in bounds.items():
        col_series = work[col]
        within_range = col_series.ge(lo) & col_series.le(hi)
        mask &= within_range | col_series.isna()

    return frame.loc[mask].reset_index(drop=True)
