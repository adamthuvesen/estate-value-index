from __future__ import annotations

import numpy as np
import pandas as pd

from estate_value_index.analytics.value_analysis import (
    calculate_value_metrics,
    generate_summary_statistics,
    prepare_output_records,
)


def _base_frame(n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    df = pd.DataFrame(
        {
            "area": ["central"] * n,
            "sold_price": rng.uniform(4_000_000, 8_000_000, n),
            "living_area": rng.uniform(40, 120, n),
        }
    )
    df["price_per_sqm"] = df["sold_price"] / df["living_area"]
    df["predicted_price"] = df["sold_price"] * rng.uniform(0.9, 1.1, n)
    return df


def test_missing_living_area_is_not_ranked():
    df = _base_frame()
    # Fake upside: five rows lose their size and get a wildly inflated prediction,
    # exactly the shape that used to top Value Finder.
    fake = df.index[:5]
    df.loc[fake, ["living_area", "price_per_sqm"]] = np.nan
    df.loc[fake, "predicted_price"] = df.loc[fake, "sold_price"] * 1.8

    out = calculate_value_metrics(df)

    suppressed = out.loc[fake]
    assert not suppressed["is_rankable"].any()
    assert suppressed["value_score"].isna().all()
    assert suppressed["value_tier"].isna().all()
    assert not suppressed["is_undervalued"].any()
    assert suppressed["rank_suppressed_reason"].eq("missing_living_area").all()
    assert suppressed["missing_core_fields"].iloc[0] == ["living_area", "price_per_sqm"]

    # The inflated rows must not out-score real ones — they carry no score at all.
    assert out.loc[out["is_rankable"], "value_score"].notna().all()


def test_rankable_rows_keep_full_score_spread():
    out = calculate_value_metrics(_base_frame())

    assert out["is_rankable"].all()
    assert out["rank_suppressed_reason"].isna().all()
    assert out["value_score"].between(1, 100).all()
    # The percentile mapping should still span most of the 1-100 range.
    assert out["value_score"].max() - out["value_score"].min() > 40


def test_summary_and_output_exclude_suppressed_rows():
    df = _base_frame()
    fake = df.index[:5]
    df.loc[fake, ["living_area", "price_per_sqm"]] = np.nan
    df.loc[fake, "predicted_price"] = df.loc[fake, "sold_price"] * 1.8
    out = calculate_value_metrics(df)

    stats = generate_summary_statistics(out, metrics={})
    assert stats["rankable_count"] == 195
    assert stats["unrankable_count"] == 5
    # Score stats cover ranked rows only — no NaN leaks into the aggregates.
    assert stats["value_score"]["max"] <= 100

    records = prepare_output_records(out)
    suppressed = [r for r in records if not r["is_rankable"]]
    assert len(suppressed) == 5
    assert all(r["value_score"] is None for r in suppressed)
    assert all(r["missing_core_fields"] == ["living_area", "price_per_sqm"] for r in suppressed)
