from __future__ import annotations

import json

import pytest

from estate_value_index.ingestion.booli.api import (
    BooliApiCredentials,
    booli_api_record_to_listing,
    scrape_booli_api_window,
    signed_api_params,
)


def test_signed_api_params_match_booli_sha1_contract() -> None:
    credentials = BooliApiCredentials(caller_id="caller", private_key="private")

    signed = signed_api_params(
        credentials,
        {"q": "stockholm"},
        timestamp=1234567890,
        unique="abcdefghijklmnop",
    )

    assert signed == {
        "q": "stockholm",
        "callerId": "caller",
        "time": "1234567890",
        "unique": "abcdefghijklmnop",
        "hash": "b256426a895a63d565582f6675064b803beb4ddf",
    }


def test_booli_api_record_to_listing_maps_core_fields() -> None:
    record = {
        "booliId": 123,
        "url": "/bostad/lagenhet/stockholm/testgatan+1/123",
        "listPrice": {"raw": 4_000_000},
        "soldPrice": {"raw": 4_250_000},
        "soldSqmPrice": {"raw": 85_000},
        "livingArea": {"raw": 50},
        "rooms": {"raw": 2},
        "soldDate": {"raw": "2026-04-30"},
        "daysActive": {"raw": 12},
        "objectType": "Lägenhet",
        "constructionYear": {"raw": 1930},
        "rent": {"raw": 3200},
        "location": {
            "streetAddress": "Testgatan 1",
            "namedAreas": [{"name": "Södermalm"}],
            "region": {"municipalityName": "Stockholm"},
        },
    }

    listing = booli_api_record_to_listing(record, source="api.booli.se/sold")

    assert listing["listing_id"] == "123"
    assert listing["url"] == "https://www.booli.se/bostad/lagenhet/stockholm/testgatan+1/123"
    assert listing["listing_price"] == 4_000_000
    assert listing["sold_price"] == 4_250_000
    assert listing["price_change"] == 250_000
    assert listing["living_area"] == 50.0
    assert listing["area"] == "Södermalm"
    assert listing["municipality"] == "Stockholm"
    assert listing["sold_date"] == "2026-04-30"
    assert listing["days_on_market"] == 12


def test_scrape_booli_api_window_writes_jsonl(tmp_path) -> None:
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps({"search_parameters": {"q": "stockholm", "minSoldDate": "2026-04-27"}}),
        encoding="utf-8",
    )
    output = tmp_path / "listings.jsonl"

    class FakeClient:
        def iter_sold(self, params, *, max_pages):
            assert params["q"] == "stockholm"
            assert params["minSoldDate"] == "2026-04-27"
            assert max_pages == 3
            yield {
                "booliId": 456,
                "soldPrice": 3_000_000,
                "livingArea": 42,
                "location": {"streetAddress": "Testvägen 2", "areaName": "Vasastan"},
            }

    scrape_booli_api_window(
        config_file=config,
        output_file=output,
        max_pages=3,
        client=FakeClient(),
        credentials=BooliApiCredentials("caller", "private"),
    )

    lines = output.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    listing = json.loads(lines[0])
    assert listing["listing_id"] == "456"
    assert listing["sold_price"] == 3_000_000
    assert listing["living_area"] == 42.0
    assert listing["area"] == "Vasastan"


def test_booli_api_credentials_fail_fast_without_env(monkeypatch) -> None:
    monkeypatch.delenv("BOOLI_API_CALLER_ID", raising=False)
    monkeypatch.delenv("BOOLI_API_PRIVATE_KEY", raising=False)

    with pytest.raises(RuntimeError, match="BOOLI_API_CALLER_ID"):
        BooliApiCredentials.from_env()
