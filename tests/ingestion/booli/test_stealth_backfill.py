"""Tests for the stealth (Cloudflare-bypassing) backfill mapper.

LOCAL BRANCH ONLY — mirrors stealth_backfill.py, which is not committed.
"""

from __future__ import annotations

import pytest

from estate_value_index.ingestion.booli.stealth_backfill import (
    _parse_data_points,
    sold_record_to_item,
)


def _sold(data_points, **overrides):
    base = {
        "__typename": "SoldProperty",
        "booliId": "999",
        "id": "999",
        "streetAddress": "Testgatan 1",
        "descriptiveAreaName": "Vasastan",
        "objectType": "Lägenhet",
        "soldDate": "2026-05-30",
        "daysActive": 20,
        "soldPrice": {"raw": 6000000},
        "location": {"region": {"municipalityName": "Stockholm"}},
        "amenities": [{"__ref": 'Amenity:{"key":"elevator"}'}],
        'displayAttributes({"queryContext":"SERP_LIST_LISTING"})': {"dataPoints": data_points},
        "url": "/bostad/999",
    }
    base.update(overrides)
    return base


def _dp(text):
    return {"value": {"plainText": text}}


@pytest.mark.unit
def test_data_points_parse_half_rooms_and_fields():
    dp = _parse_data_points(
        _sold([_dp("56 m²"), _dp("2,5 rum"), _dp("vån 4"), _dp("6 464 kr/mån")])
    )
    assert dp["living_area"] == 56.0
    assert dp["rooms"] == 2  # half-room floored, never read as 5
    assert dp["floor"] == 4
    assert dp["monthly_fee"] == 6464


@pytest.mark.unit
def test_price_per_sqm_data_point_not_confused_with_area():
    dp = _parse_data_points(_sold([_dp("73 m²"), _dp("3 rum"), _dp("95 000 kr/m²")]))
    assert dp["living_area"] == 73.0
    assert dp["price_per_sqm"] == 95000


@pytest.mark.unit
def test_item_recovers_bad_living_area_from_price_per_sqm():
    # Card mis-shows "12 m²" but price_per_sqm implies ~73 m² for a 8.25M sale.
    item = sold_record_to_item(
        _sold(
            [_dp("12 m²"), _dp("3 rum"), _dp("113 000 kr/m²")],
            soldPrice={"raw": 8250000},
        ),
        {},
    )
    assert item["living_area"] == 73  # repaired via sold_price / price_per_sqm
    assert item["price_per_sqm"] == 113000


@pytest.mark.unit
def test_item_core_fields_and_amenities():
    item = sold_record_to_item(_sold([_dp("50 m²"), _dp("2 rum"), _dp("95 000 kr/m²")]), {})
    assert item["listing_id"] == "999"
    assert item["sold_price"] == 6000000
    assert item["sold_date"] == "2026-05-30"
    assert item["address"] == "Testgatan 1"
    assert item["municipality"] == "Stockholm"
    assert item["elevator"] is True
    assert item["balcony"] is None
    assert item["url"] == "https://www.booli.se/bostad/999"


@pytest.mark.unit
def test_listing_price_falls_back_to_paired_listing():
    listing_by_id = {"999": {"listPrice": {"raw": 5500000}}}
    item = sold_record_to_item(
        _sold([_dp("50 m²"), _dp("2 rum"), _dp("120 000 kr/m²")]), listing_by_id
    )
    assert item["listing_price"] == 5500000
    assert item["price_change"] == 6000000 - 5500000
