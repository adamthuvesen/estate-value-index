"""Tests for 429 + retry middleware behaviour.

The 429 path must re-issue a fresh Request (so the rate-limit page never
reaches the parser) and raise ``IgnoreRequest`` once ``RETRY_TIMES`` is
exhausted. The smart-retry path must raise ``IgnoreRequest`` when
``_retry`` cannot produce another attempt (rather than masquerading the
error response as success).
"""

from __future__ import annotations

import asyncio

import pytest

scrapy = pytest.importorskip("scrapy")

from scrapy.exceptions import IgnoreRequest
from scrapy.http import HtmlResponse, Request
from scrapy.utils.test import get_crawler

from estate_value_index.ingestion.core import middlewares as mw_module
from estate_value_index.ingestion.core.middlewares import (
    BooliDownloaderMiddleware,
    BooliSpiderMiddleware,
    SmartRetryMiddleware,
)


def _make_spider(retry_times: int = 3):
    crawler = get_crawler(settings_dict={"RETRY_TIMES": retry_times})
    spider = scrapy.Spider(name="test")
    spider.crawler = crawler
    return spider


def _response(status: int, url: str = "https://booli.se/x", request: Request | None = None):
    request = request or Request(url=url)
    return HtmlResponse(url=url, status=status, request=request, body=b"<html></html>")


@pytest.fixture
def capture_deferlater(monkeypatch):
    """Replace deferLater with a stub that records the scheduled callable.

    Returns a list onto which each (delay, callable) tuple is appended.
    """
    captured: list[tuple[float, callable]] = []

    def fake_defer_later(reactor, delay, fn, *args, **kwargs):
        captured.append((delay, lambda: fn(*args, **kwargs)))
        return f"<deferred delay={delay}>"

    monkeypatch.setattr(mw_module, "deferLater", fake_defer_later)
    return captured


def test_429_returns_request_not_response(capture_deferlater):
    """The 429 page must never be returned to the parser; a fresh Request is scheduled."""
    middleware = BooliDownloaderMiddleware(get_crawler().settings)
    spider = _make_spider()
    request = Request(url="https://booli.se/x")

    middleware.process_response(request, _response(429, request=request), spider)

    assert len(capture_deferlater) == 1
    delay, scheduled = capture_deferlater[0]
    assert 30 <= delay <= 60
    produced = scheduled()
    assert isinstance(produced, Request)
    assert produced.meta.get("booli_429_retries") == 1
    assert produced.dont_filter is True


def test_429_after_retry_times_raises_ignore_request():
    middleware = BooliDownloaderMiddleware(get_crawler().settings)
    spider = _make_spider(retry_times=2)
    request = Request(url="https://booli.se/x", meta={"booli_429_retries": 2})

    with pytest.raises(IgnoreRequest):
        middleware.process_response(request, _response(429, request=request), spider)


def test_smart_retry_exhausted_raises_ignore_request(capture_deferlater):
    """When `_retry` returns None (cap hit), we must raise rather than return the error response."""
    crawler = get_crawler(settings_dict={"RETRY_TIMES": 1})
    middleware = SmartRetryMiddleware(crawler.settings)
    spider = _make_spider(retry_times=1)
    # Scrapy's RetryMiddleware._retry needs middleware.crawler.spider; wire it up.
    crawler.spider = spider
    middleware.crawler = crawler
    # meta.retry_times already past the cap so _retry returns None
    request = Request(url="https://booli.se/x", meta={"retry_times": 5})

    middleware.process_response(request, _response(503, request=request), spider)

    assert len(capture_deferlater) == 1
    _, scheduled = capture_deferlater[0]
    with pytest.raises(IgnoreRequest):
        scheduled()


def test_booli_spider_middleware_supports_async_output():
    middleware = BooliSpiderMiddleware()

    async def source():
        yield "first"
        yield "second"

    async def collect():
        return [item async for item in middleware.process_spider_output_async(None, source(), None)]

    assert asyncio.run(collect()) == ["first", "second"]
