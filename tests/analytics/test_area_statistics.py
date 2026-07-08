from __future__ import annotations

import json

from estate_value_index.analytics.area_statistics import (
    calculate_price_by_size,
    generate_area_statistics,
)


def test_calculate_price_by_size_buckets_by_living_area():
    properties = [
        {"living_area": 45, "sold_price": 4_000_000},
        {"living_area": 48, "sold_price": 4_400_000},  # same 40-50 bucket
        {"living_area": 55, "sold_price": 5_800_000},
        {"living_area": 130, "sold_price": 12_000_000},
        {"living_area": 60, "sold_price": None},  # dropped: no price
        {"living_area": None, "sold_price": 5_000_000},  # dropped: no area
    ]

    result = calculate_price_by_size(properties)

    # Ordered small -> large, empty buckets omitted.
    assert [row["bucket"] for row in result] == ["40–50", "50–60", "120+"]
    first = result[0]
    assert first["count"] == 2
    assert first["median_price"] == 4_200_000  # median of 4.0M and 4.4M


def test_generate_area_statistics_builds_and_writes_area_payload(tmp_path):
    feature_context_path = tmp_path / "feature_context.json"
    value_analysis_path = tmp_path / "value_analysis.json"
    raw_listings_path = tmp_path / "raw_listings.json"
    output_path = tmp_path / "area_statistics.json"

    feature_context_path.write_text(
        json.dumps(
            {
                "reference_date": "2026-06-01",
                "area_avg_price": {"sodermalm": 5_000_000, "ignored": 1},
                "area_target_mean": {"sodermalm": 5_100_000},
                "area_price_tier": {"sodermalm": "premium"},
                "area_median_price_3m": {"sodermalm": 5_050_000},
                "area_median_price_6m": {"sodermalm": 5_000_000},
                "area_median_price_12m": {"sodermalm": 4_950_000},
                "area_sales_volume_3m": {"sodermalm": 4},
                "area_sales_volume_6m": {"sodermalm": 7},
                "area_sales_volume_12m": {"sodermalm": 11},
            }
        ),
        encoding="utf-8",
    )
    value_analysis_path.write_text(
        json.dumps(
            {
                "metadata": {"generated_at": "2026-06-02T00:00:00Z"},
                "properties": [
                    {
                        "area": "sodermalm",
                        "value_score": 80,
                        "prediction_delta_absolute": 100_000,
                        "is_undervalued": True,
                        "value_tier": "Good Value",
                        "is_rankable": True,
                    },
                    {
                        "area": "sodermalm",
                        "value_score": 60,
                        "prediction_delta_absolute": 50_000,
                        "is_undervalued": False,
                        "value_tier": "Fair Value",
                        "is_rankable": True,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    raw_listings_path.write_text(
        json.dumps(
            [
                {
                    "listing_id": "1",
                    "area": "sodermalm",
                    "address": "A Street 1",
                    "url": "https://example.test/1",
                    "listing_price": 4_900_000,
                    "sold_price": 5_100_000,
                    "living_area": 50,
                    "rooms": 2,
                    "sold_date": "2026-05-15",
                    "days_on_market": 10,
                    "price_change": 200_000,
                    "elevator": True,
                    "balcony": False,
                    "construction_year": 1930,
                },
                {
                    "listing_id": "2",
                    "area": "sodermalm",
                    "address": "B Street 2",
                    "url": "https://example.test/2",
                    "listing_price": 6_100_000,
                    "sold_price": 6_000_000,
                    "living_area": 60,
                    "rooms": 3,
                    "sold_date": "2026-04-20",
                    "days_on_market": 20,
                    "price_change": -100_000,
                    "elevator": False,
                    "balcony": True,
                    "construction_year": 1985,
                },
            ]
        ),
        encoding="utf-8",
    )

    result = generate_area_statistics(
        data_source="json",
        feature_context_path=feature_context_path,
        value_analysis_path=value_analysis_path,
        raw_listings_path=raw_listings_path,
        output_path=output_path,
    )

    assert json.loads(output_path.read_text(encoding="utf-8")) == result
    assert result["metadata"]["total_areas"] == 1
    assert result["metadata"]["total_properties"] == 2
    # "Updated" tracks the newest sold_date in the data (2026-05-15), not the
    # model's reference_date (2026-06-01) — the training cutoff lags the data.
    assert result["metadata"]["generated_at"] == "2026-05-15"

    area = result["areas"]["sodermalm"]
    assert area["overview"]["avg_listing_price"] == 5_000_000
    assert area["overview"]["avg_sold_price"] == 5_100_000
    assert area["market_dynamics"]["days_on_market_median"] == 15
    assert area["market_dynamics"]["price_change_mean"] == 50_000
    assert area["market_dynamics"]["sales_volume_12m"] == 11
    assert area["value_insights"]["undervalued_count"] == 1
    assert area["value_insights"]["avg_value_score"] == 70.0
    assert set(area["by_room_count"]) == {"all", "2", "3"}


def test_generate_area_statistics_falls_back_when_area_avg_price_is_empty(tmp_path):
    feature_context_path = tmp_path / "feature_context.json"
    value_analysis_path = tmp_path / "value_analysis.json"
    raw_listings_path = tmp_path / "raw_listings.json"
    output_path = tmp_path / "area_statistics.json"

    feature_context_path.write_text(
        json.dumps(
            {
                "reference_date": "2026-06-01",
                "area_avg_price": {},
                "area_target_mean": {"sodermalm": 5_500_000},
                "area_sales_volume_3m": {"sodermalm": 2},
            }
        ),
        encoding="utf-8",
    )
    value_analysis_path.write_text(
        json.dumps({"metadata": {}, "properties": [{"area": "sodermalm", "is_rankable": True}]}),
        encoding="utf-8",
    )
    raw_listings_path.write_text(
        json.dumps(
            [
                {
                    "listing_id": "1",
                    "area": "sodermalm",
                    "listing_price": 4_900_000,
                    "sold_price": 5_100_000,
                    "living_area": 50,
                    "rooms": 2,
                    "sold_date": "2026-05-15",
                },
                {
                    "listing_id": "2",
                    "area": "sodermalm",
                    "listing_price": 5_300_000,
                    "sold_price": 5_900_000,
                    "living_area": 60,
                    "rooms": 3,
                    "sold_date": "2026-05-16",
                },
            ]
        ),
        encoding="utf-8",
    )

    result = generate_area_statistics(
        data_source="json",
        feature_context_path=feature_context_path,
        value_analysis_path=value_analysis_path,
        raw_listings_path=raw_listings_path,
        output_path=output_path,
    )

    assert result["metadata"]["total_areas"] == 1
    area = result["areas"]["sodermalm"]
    assert area["overview"]["avg_listing_price"] == 5_100_000
    assert area["overview"]["avg_sold_price"] == 5_500_000
