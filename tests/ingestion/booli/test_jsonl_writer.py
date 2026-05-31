"""Tests for the Booli JSONL writer's per-record flush."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

from estate_value_index.ingestion.booli.items import BooliListingItem
from estate_value_index.ingestion.booli.pipelines import JsonWriterPipeline


def test_process_item_flushes_immediately(tmp_path: Path):
    pipeline = JsonWriterPipeline(output_dir=str(tmp_path))
    spider = SimpleNamespace(logger=logging.getLogger("test-spider"))
    pipeline.open_spider(spider)

    item = BooliListingItem()
    item["listing_id"] = "abc-1"
    item["url"] = "https://example.com/listing/abc-1"

    pipeline.process_item(item, spider)

    # Read the JSONL from a separate handle WITHOUT calling close_spider —
    # this only succeeds if the writer flushed its buffer immediately.
    jsonl_files = list(tmp_path.glob("*.jsonl"))
    assert len(jsonl_files) == 1
    contents = jsonl_files[0].read_text(encoding="utf-8")
    assert contents.strip(), "expected at least one record visible without close"
    assert '"abc-1"' in contents

    pipeline.close_spider(spider)
