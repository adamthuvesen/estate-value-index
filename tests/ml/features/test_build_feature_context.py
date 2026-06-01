"""Tests for build_feature_context reference-date anchoring."""

from __future__ import annotations

import pandas as pd

from estate_value_index.ml.features import build_feature_context


def _minimal_frame(extra: dict[str, list]) -> pd.DataFrame:
    """Return a frame with the columns build_feature_context needs to succeed."""
    n = max(len(v) for v in extra.values()) if extra else 2
    base = {
        "area": ["Vasastan"] * n,
        "listing_price": [5_000_000.0] * n,
        "sold_price": [5_100_000.0] * n,
    }
    base.update(extra)
    return pd.DataFrame(base)


def test_reference_date_uses_sold_date_max():
    df = _minimal_frame(
        {
            "sold_date": pd.to_datetime(["2024-01-15", "2024-06-01"]),
            "scraped_at": pd.to_datetime(["2024-11-01", "2024-12-01"]),
        }
    )
    ctx = build_feature_context(df)
    assert ctx.reference_date == pd.Timestamp("2024-06-01")


def test_reference_date_falls_back_to_scraped_at_when_sold_all_nat():
    df = _minimal_frame(
        {
            "sold_date": pd.to_datetime([None, None]),
            "scraped_at": pd.to_datetime(["2024-11-01", "2024-12-01"]),
        }
    )
    ctx = build_feature_context(df)
    assert ctx.reference_date == pd.Timestamp("2024-12-01")


def test_reference_date_falls_back_to_now_when_both_columns_missing():
    df = _minimal_frame({"foo": [1, 2]})
    ctx = build_feature_context(df)
    assert isinstance(ctx.reference_date, pd.Timestamp)
    assert pd.notna(ctx.reference_date)
