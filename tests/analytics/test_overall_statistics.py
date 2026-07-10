from __future__ import annotations

import json

from estate_value_index.analytics.overall_statistics import (
    _amenity_effect,
    _bidding_rows,
    build_by_floor,
    build_histogram,
    build_records,
    build_top_streets,
    generate_overall_statistics,
)


def test_build_histogram_clips_to_percentile_window_but_percentiles_are_unclipped():
    # 0..100 plus two extreme outliers. p1..p99 come from the full set; the
    # outliers are trimmed before binning so they don't stretch the axis.
    values = list(range(0, 101)) + [10_000, -10_000]

    hist = build_histogram(values, bins=10, clip_lo_pct=1, clip_hi_pct=99, as_int=True)

    assert hist["sample_size"] == 103  # pre-clip count
    # Edges track the p1/p99 window, not the -10000/10000 outliers.
    assert hist["min"] == hist["p1"]
    assert hist["max"] == hist["p99"]
    assert -1 <= hist["min"] <= 5
    assert 95 <= hist["max"] <= 101
    assert len(hist["counts"]) == 10
    # Every retained value lands in exactly one bin; the two outliers are gone.
    assert sum(hist["counts"]) <= 101


def test_build_histogram_bin_math_is_uniform():
    values = [float(x) for x in range(0, 100)]  # 0..99
    hist = build_histogram(values, bins=10, clip_lo_pct=0, clip_hi_pct=100, as_int=False)

    assert hist["min"] == 0.0
    assert hist["max"] == 99.0
    assert hist["bin_width"] == 9.9
    assert len(hist["counts"]) == 10
    assert sum(hist["counts"]) == 100


def test_bidding_excludes_rows_without_listing_price():
    rows = [
        {"listing_price": 5_000_000, "sold_price": 5_500_000},
        {"listing_price": None, "sold_price": 5_000_000},  # no ask -> excluded
        {"listing_price": 0, "sold_price": 4_000_000},  # zero ask -> excluded
        {"listing_price": 4_000_000, "sold_price": None},  # no sale -> excluded
        {"listing_price": 6_000_000, "sold_price": 6_600_000},
    ]

    bidding = _bidding_rows(rows)

    assert len(bidding) == 2
    assert all(r["listing_price"] and r["sold_price"] for r in bidding)


def test_amenity_effect_treats_null_as_unknown_not_false():
    # 2 with (true), 2 without (false), 2 unknown (null). Only known rows count.
    rows = [
        {"balcony": True, "sold_price": 6_000_000, "living_area": 50},  # 120k/m²
        {"balcony": True, "sold_price": 6_600_000, "living_area": 60},  # 110k/m²
        {"balcony": False, "sold_price": 5_000_000, "living_area": 50},  # 100k/m²
        {"balcony": False, "sold_price": 5_400_000, "living_area": 60},  # 90k/m²
        {"balcony": None, "sold_price": 9_000_000, "living_area": 30},  # unknown
        {"balcony": None, "sold_price": 3_000_000, "living_area": 100},  # unknown
    ]

    effect = _amenity_effect(rows, "balcony")

    assert effect["known_count"] == 4  # nulls excluded
    assert effect["share_with"] == 0.5
    assert effect["median_ppsqm_with"] == 115_000
    assert effect["median_ppsqm_without"] == 95_000
    # (115000 - 95000) / 95000 * 100
    assert round(effect["naive_diff_pct"], 2) == 21.05


def test_amenity_effect_handles_empty_without_arm():
    rows = [
        {"balcony": True, "sold_price": 6_000_000, "living_area": 50},
        {"balcony": None, "sold_price": 5_000_000, "living_area": 50},
    ]

    effect = _amenity_effect(rows, "balcony")

    assert effect["known_count"] == 1
    assert effect["share_with"] == 1.0
    assert effect["median_ppsqm_without"] is None
    assert effect["naive_diff_pct"] is None
    assert effect["within_area_diff_pct"] is None
    assert effect["within_area_sample_areas"] == 0


def test_by_floor_drops_buckets_below_min_n_and_keeps_floor_zero():
    rows = []
    # Floor 0: 30 rows (meets min-n), floor 1: 5 rows (dropped), null: ignored.
    for _ in range(30):
        rows.append({"floor": 0, "sold_price": 5_000_000, "living_area": 50})
    for _ in range(5):
        rows.append({"floor": 1, "sold_price": 6_000_000, "living_area": 50})
    rows.append({"floor": None, "sold_price": 9_000_000, "living_area": 50})

    result = build_by_floor(rows)

    buckets = {r["floor_bucket"]: r for r in result}
    assert "0" in buckets  # floor 0 is real
    assert buckets["0"]["sample_size"] == 30
    assert "1" not in buckets  # below min-n


def test_records_fastest_sale_requires_days_on_market_at_least_one():
    rows = [
        {
            "address": "A 1",
            "area": "sodermalm",
            "sold_price": 5_000_000,
            "living_area": 50,
            "sold_date": "2026-01-01",
            "days_on_market": 0,  # not a real sale duration -> excluded
            "listing_price": 4_800_000,
        },
        {
            "address": "B 2",
            "area": "sodermalm",
            "sold_price": 6_000_000,
            "living_area": 60,
            "sold_date": "2026-02-01",
            "days_on_market": 3,
            "listing_price": 5_500_000,
        },
    ]

    records = build_records(rows, value_properties=[])

    assert records["fastest_sale"]["days_on_market"] == 3
    assert records["fastest_sale"]["address"] == "B 2"


def test_records_biggest_bid_up_skips_implausible_premiums():
    def row(address: str, listing: int, sold: int) -> dict:
        return {
            "address": address,
            "area": "sodermalm",
            "sold_price": sold,
            "living_area": 50,
            "sold_date": "2026-01-01",
            "days_on_market": 5,
            "listing_price": listing,
        }

    rows = [
        row("Typo 1", 1_300_000, 13_000_000),  # +900% -> 10x listing-price typo
        row("Real 2", 4_000_000, 6_000_000),  # +50% -> plausible record
        row("Calm 3", 5_000_000, 5_100_000),  # +2%
    ]

    records = build_records(rows, value_properties=[])

    assert records["biggest_bid_up"]["address"] == "Real 2"
    assert records["biggest_bid_up"]["premium_pct"] == 50.0


def test_top_streets_strips_trailing_house_numbers():
    rows = [
        {"address": "Vasagatan 12B", "sold_price": 5_000_000},
        {"address": "Vasagatan 5", "sold_price": 5_400_000},
        {"address": "Vasagatan 8 A", "sold_price": 6_000_000},
        {"address": "Storgatan 3", "sold_price": 7_000_000},
    ]

    streets = build_top_streets(rows)

    top = streets[0]
    assert top["street"] == "Vasagatan"
    assert top["sales_count"] == 3
    assert top["median_sold_price"] == 5_400_000


def test_generate_overall_statistics_end_to_end(tmp_path):
    value_analysis_path = tmp_path / "value_analysis.json"
    raw_listings_path = tmp_path / "raw_listings.json"
    output_path = tmp_path / "overall_statistics.json"

    listings = []
    # Two published areas with >= 2 listings each.
    for i in range(4):
        listings.append(
            {
                "listing_id": str(i),
                "area": "sodermalm",
                "address": f"Testgatan {i + 1}",
                "url": f"https://example.test/{i}",
                "listing_price": 4_800_000 + i * 100_000,
                "sold_price": 5_000_000 + i * 100_000,
                "living_area": 50 + i,
                "rooms": 2,
                "floor": i,
                "balcony": True,
                "elevator": True,
                "monthly_fee": 2_500,
                "construction_year": 1930 + i,
                "sold_date": f"2026-0{(i % 6) + 1}-15",
                "days_on_market": i + 1,
                "price_change": 200_000,
            }
        )
    for i in range(3):
        listings.append(
            {
                "listing_id": f"v{i}",
                "area": "vasastan",
                "address": f"Odengatan {i + 1}",
                "url": f"https://example.test/v{i}",
                "listing_price": 6_000_000,
                "sold_price": 6_500_000 + i * 100_000,
                "living_area": 70 + i,
                "rooms": 3,
                "floor": 2,
                "balcony": None,
                "elevator": True,
                "monthly_fee": 3_500,
                "construction_year": 1990,
                "sold_date": f"2025-1{i}-10",
                "days_on_market": 5,
                "price_change": 500_000,
            }
        )

    raw_listings_path.write_text(json.dumps(listings), encoding="utf-8")
    value_analysis_path.write_text(
        json.dumps(
            {
                "metadata": {"generated_at": "2026-06-02T00:00:00Z"},
                "properties": [
                    {
                        "area": "sodermalm",
                        "address": "Testgatan 1",
                        "url": "https://example.test/0",
                        "living_area": 50,
                        "rooms": 2,
                        "sold_price": 5_000_000,
                        "sold_date": "2026-01-15",
                        "is_rankable": True,
                        "is_undervalued": True,
                        "value_score": 90.0,
                        "prediction_delta_percentage": 12.5,
                    },
                    {
                        "area": "sodermalm",
                        "is_rankable": True,
                        "is_undervalued": False,
                        "value_score": 40.0,
                        "prediction_delta_percentage": -3.0,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    result = generate_overall_statistics(
        data_source="json",
        value_analysis_path=value_analysis_path,
        raw_listings_path=raw_listings_path,
        output_path=output_path,
    )

    assert json.loads(output_path.read_text(encoding="utf-8")) == result

    assert set(result) == {
        "metadata",
        "hero",
        "prices",
        "over_time",
        "bidding",
        "geography",
        "size_rooms",
        "building",
        "records",
    }

    meta = result["metadata"]
    assert meta["total_properties"] == 7
    assert meta["total_areas"] == 2
    assert meta["generated_at"] == "2026-04-15"  # latest sold_date in data
    assert meta["date_range"] == {"start": "2025-10-10", "end": "2026-04-15"}
    assert meta["data_sources"] == {
        "raw_listings": "raw_listings.json",
        "value_analysis": "value_analysis.json",
    }

    assert result["hero"]["total_sales"] == 7
    assert result["hero"]["total_areas"] == 2
    assert len(result["hero"]["price_per_sqm_strip"]["counts"]) == 200

    # Geography sorted by median kr-m² desc; undervalued_share joined for sodermalm.
    areas = result["geography"]["areas"]
    assert [a["area_name"] for a in areas] == sorted(
        [a["area_name"] for a in areas],
        key=lambda k: next(x["median_price_per_sqm"] for x in areas if x["area_name"] == k),
        reverse=True,
    )
    sodermalm = next(a for a in areas if a["area_name"] == "sodermalm")
    assert sodermalm["undervalued_share"] == 0.5
    vasastan = next(a for a in areas if a["area_name"] == "vasastan")
    assert vasastan["undervalued_share"] is None  # not in value_analysis

    # best_value comes from the rankable value-analysis row with the top score.
    best = result["records"]["best_value"]
    assert best is not None
    assert best["value_score"] == 90.0
    assert best["area_name"] == "sodermalm"
