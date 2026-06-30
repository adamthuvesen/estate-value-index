"""Tests for BooliSpider detail-page parsing."""

from __future__ import annotations

from collections import defaultdict
from types import SimpleNamespace

import pytest

scrapy = pytest.importorskip("scrapy")

from scrapy.http import HtmlResponse, Request

from estate_value_index.ingestion.booli.spiders.booli import BooliSpider


class _FakeStats:
    def __init__(self):
        self.values: dict[str, int] = defaultdict(int)

    def inc_value(self, key: str, count: int = 1):
        self.values[key] += count

    def get_value(self, key: str, default=None):
        return self.values.get(key, default)


def _spider() -> BooliSpider:
    spider = BooliSpider(max_pages=1, progress_interval=100)
    spider.crawler = SimpleNamespace(stats=_FakeStats())

    spider.extract_listing_price = lambda response: 4_000_000
    spider.extract_sold_price = lambda response: 4_500_000
    spider.extract_address = lambda response: "Testgatan 1"
    spider.extract_area = lambda response: "Vasastan"
    spider.extract_municipality = lambda response: "Stockholm"
    spider.extract_living_area = lambda response: 55.0
    spider.extract_rooms = lambda response: 2
    spider.extract_property_type = lambda response: "Lägenhet"
    spider.extract_construction_year = lambda response: 1930
    spider.extract_monthly_fee = lambda response: 3200
    spider.extract_price_per_sqm = lambda response: 81_818
    spider.extract_floor = lambda response: 3
    spider.extract_elevator = lambda response: True
    spider.extract_balcony = lambda response: False
    spider.extract_sold_date = lambda response: "2024-01-15"
    spider.extract_days_on_market = lambda response: 12
    spider.extract_price_change = lambda response: 123
    spider.extract_description = lambda response: "Nice"
    spider.extract_images = lambda response: ["https://example.test/img.jpg"]
    return spider


def _listing_response() -> HtmlResponse:
    request = Request(
        "https://www.booli.se/annons/123",
        meta={"listing_id": "123", "source_page": 2},
    )
    return HtmlResponse(
        url=request.url,
        request=request,
        body=b"<html><body>listing</body></html>",
        encoding="utf-8",
    )


@pytest.mark.unit
def test_parse_listing_builds_item_and_records_stats() -> None:
    spider = _spider()

    items = list(spider.parse_listing(_listing_response()))

    assert len(items) == 1
    item = items[0]
    assert item["listing_id"] == "123"
    assert item["source_page"] == 2
    assert item["address"] == "Testgatan 1"
    assert item["price_change"] == 500_000
    assert spider.total_listings_processed == 1
    assert spider.crawler.stats.get_value("booli/listings_yielded") == 1
    assert spider.crawler.stats.get_value("booli/missing/listing_price", 0) == 0
