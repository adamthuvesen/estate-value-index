from __future__ import annotations

from pathlib import Path

import pytest

from estate_value_index.ingestion.booli.spiders.booli import BooliSpider


def test_explicit_missing_config_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Booli config file not found"):
        BooliSpider(max_pages=1, config_file=str(tmp_path / "missing.json"))


def test_explicit_invalid_config_raises(tmp_path: Path) -> None:
    config = tmp_path / "invalid.json"
    config.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid JSON in Booli config file"):
        BooliSpider(max_pages=1, config_file=str(config))
