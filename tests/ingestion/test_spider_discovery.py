"""Regression tests for fix-scrapy-spider-module-paths (C4).

Confirms that every Scrapy module path written by repo code is fully
qualified under `estate_value_index.*`, so spider/pipeline discovery
works in any deployment topology — not just the dev shell where the
editable install accidentally puts `src/estate_value_index/` on
``sys.path``.
"""

from __future__ import annotations

import pytest

scrapy = pytest.importorskip("scrapy")

from scrapy.spiderloader import SpiderLoader
from scrapy.utils.misc import load_object

from estate_value_index.ingestion.booli.runner import (
    BooliCrawlerOptions,
    BooliCrawlerRunner,
)


def test_settings_use_qualified_spider_modules():
    settings = BooliCrawlerRunner._prepare_settings(BooliCrawlerOptions(stats_only=False))
    spider_modules = settings.getlist("SPIDER_MODULES")
    assert "estate_value_index.ingestion.booli.spiders" in spider_modules
    assert "ingestion.booli.spiders" not in spider_modules
    for path in spider_modules:
        assert path.startswith("estate_value_index."), path


def test_spider_loader_resolves_booli_spider():
    settings = BooliCrawlerRunner._prepare_settings(BooliCrawlerOptions(stats_only=False))
    loader = SpiderLoader.from_settings(settings)
    spider_cls = loader.load("booli")
    assert spider_cls.name == "booli"


def test_default_item_pipelines_are_qualified():
    settings = BooliCrawlerRunner._prepare_settings(BooliCrawlerOptions(stats_only=False))
    pipelines = settings.getdict("ITEM_PIPELINES")
    assert pipelines, "Default ITEM_PIPELINES is empty"
    for path in pipelines:
        assert path.startswith("estate_value_index."), path
        # Must actually resolve to a class
        load_object(path)


def test_stats_only_pipelines_are_qualified():
    settings = BooliCrawlerRunner._prepare_settings(BooliCrawlerOptions(stats_only=True))
    pipelines = settings.getdict("ITEM_PIPELINES")
    assert pipelines, "stats_only ITEM_PIPELINES is empty"
    for path in pipelines:
        assert path.startswith("estate_value_index."), path
        load_object(path)
