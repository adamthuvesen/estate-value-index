"""Test that ``parse_search_results`` does not re-issue requests for already-seen listings."""

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

    def set_value(self, key: str, value):
        self.values[key] = value

    def get_value(self, key: str, default=None):
        return self.values.get(key, default)


def _make_spider():
    spider = BooliSpider(max_pages=1)
    spider.crawler = SimpleNamespace(stats=_FakeStats())
    return spider


def _search_response(spider) -> HtmlResponse:
    body = b"""
    <html><body>
      <li class="search-page__module-container">
        <article>
          <a href="/annons/1234567">Listing one</a>
        </article>
      </li>
      <li class="search-page__module-container">
        <article>
          <a href="/annons/7654321">Listing two</a>
        </article>
      </li>
    </body></html>
    """
    request = Request(url="https://booli.se/sok/till-salu?page=1", meta={"page": 1})
    return HtmlResponse(
        url=request.url,
        request=request,
        body=body,
        encoding="utf-8",
    )


def test_second_call_yields_no_listing_requests_and_increments_dedup_stat():
    spider = _make_spider()
    response = _search_response(spider)

    first_yields = list(spider.parse_search_results(response))
    listing_requests_first = [
        r for r in first_yields if isinstance(r, Request) and "/annons/" in r.url
    ]
    assert len(listing_requests_first) == 2
    initial_dedup = spider.crawler.stats.get_value("booli/dedup_skipped", 0)

    # Reset pages_processed so pagination logic still emits the next-page request.
    spider.pages_processed = 0
    second_yields = list(spider.parse_search_results(response))
    listing_requests_second = [
        r for r in second_yields if isinstance(r, Request) and "/annons/" in r.url
    ]
    assert listing_requests_second == []

    final_dedup = spider.crawler.stats.get_value("booli/dedup_skipped", 0)
    assert final_dedup - initial_dedup == 2
