from __future__ import annotations

import json

from estate_value_index.ingestion.booli.extractors import next_fetch
from estate_value_index.ingestion.booli.extractors.next_fetch import (
    BooliNextFetchMixin,
    _property_next_data_url,
    _property_path_from_listing_url,
)


class _Fetcher(BooliNextFetchMixin):
    def __init__(self):
        self.invalidations = 0
        self.refreshes = 0

    def _ensure_build_id(self, force_refresh=False):
        if force_refresh:
            self.refreshes += 1
            return "new-build"
        return "old-build"

    def _invalidate_build_id_cache(self):
        self.invalidations += 1

    def _default_http_headers(self):
        return {"User-Agent": "test-agent"}


def test_property_next_data_url_helpers():
    assert _property_path_from_listing_url("https://www.booli.se/annons/123/") == "/annons/123"
    assert _property_path_from_listing_url("https://www.booli.se") is None
    assert (
        _property_next_data_url("build-1", "/annons/123")
        == "https://www.booli.se/_next/data/build-1/annons/123.json"
    )


def test_fetch_property_data_refreshes_build_id_after_non_json(monkeypatch):
    fetcher = _Fetcher()
    urls: list[str] = []
    payloads = iter(
        [
            "not json",
            json.dumps(
                {
                    "pageProps": {
                        "__APOLLO_STATE__": {
                            "SoldProperty:123": {"booliId": 123, "address": "A Street 1"}
                        }
                    }
                }
            ),
        ]
    )

    def fake_request_next_payload(url, headers):
        urls.append(url)
        assert headers["Accept"] == "application/json"
        return next(payloads)

    monkeypatch.setattr(next_fetch, "_request_next_payload", fake_request_next_payload)
    monkeypatch.setattr(next_fetch.time, "sleep", lambda seconds: None)

    result = fetcher._fetch_property_data_from_next("https://www.booli.se/annons/123", "123")

    assert result == {"booliId": 123, "address": "A Street 1"}
    assert fetcher.invalidations == 1
    assert fetcher.refreshes == 1
    assert "old-build" in urls[0]
    assert "new-build" in urls[1]
