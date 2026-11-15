from __future__ import annotations

import numpy as np
import pandas as pd

from estate_value_index.analytics.value_analysis import (
    calculate_value_metrics,
    generate_summary_statistics,
    prepare_output_records,
)
from estate_value_index.analytics.web_json import ValueAnalysisData


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


def test_output_matches_the_web_json_contract():
    df = _base_frame(50)
    df.loc[df.index[:3], ["living_area", "price_per_sqm"]] = np.nan
    df["listing_id"] = [str(i) for i in range(len(df))]
    df["url"] = None
    df["address"] = "Street 1"
    df["municipality"] = "Stockholm"
    df["rooms"] = 2.0
    df["property_type"] = "Lägenhet"
    df["construction_year"] = 1930
    df["monthly_fee"] = 3000.0
    df["floor"] = 2.0
    df["elevator"] = True
    df["balcony"] = None
    df["sold_date"] = "2026-01-02"
    df["days_on_market"] = 10
    df["listing_price"] = df["sold_price"]
    # Sold listings may lack rooms and a monthly fee; the export must keep them.
    df.loc[df.index[3:5], ["rooms", "monthly_fee"]] = np.nan
    df[["address", "municipality", "property_type"]] = df[
        ["address", "municipality", "property_type"]
    ].astype(object)
    df.loc[df.index[5:7], ["address", "municipality", "property_type"]] = None
    # A sold price with no recorded sale date is a valid ingested listing too.
    df["sold_date"] = df["sold_date"].astype(object)
    df.loc[df.index[7], "sold_date"] = None
    out = calculate_value_metrics(df)

    ValueAnalysisData.model_validate(
        {
            "metadata": {
                "generated_at": "2026-01-03T00:00:00",
                "model_type": "no_list_price",
                "model_path": "web/models/m.joblib",
                "data_source": "listings.json",
                "filters": {
                    "only_undervalued": False,
                    "min_value_score": None,
                    "training_filters_applied": True,
                },
                "thresholds": {"undervalue_threshold_pct": 5.0, "undervalue_threshold_abs": 2e5},
            },
            "statistics": generate_summary_statistics(out, metrics={}),
            "properties": prepare_output_records(out),
        }
    )
