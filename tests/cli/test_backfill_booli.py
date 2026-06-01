from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from estate_value_index.cli.backfill_booli import (
    DateWindow,
    date_windows,
    merge_deduped_jsonl,
    run_backfill,
    write_window_config,
)


def test_date_windows_cover_range_inclusive() -> None:
    assert list(date_windows(date(2026, 1, 1), date(2026, 1, 10), 4)) == [
        DateWindow(date(2026, 1, 1), date(2026, 1, 4)),
        DateWindow(date(2026, 1, 5), date(2026, 1, 8)),
        DateWindow(date(2026, 1, 9), date(2026, 1, 10)),
    ]


def test_date_windows_reject_invalid_ranges() -> None:
    with pytest.raises(ValueError, match="window_days"):
        list(date_windows(date(2026, 1, 1), date(2026, 1, 2), 0))

    with pytest.raises(ValueError, match="start date"):
        list(date_windows(date(2026, 1, 2), date(2026, 1, 1), 1))


def test_write_window_config_updates_sold_date_parameters(tmp_path: Path) -> None:
    base_config = tmp_path / "base.json"
    output_config = tmp_path / "config_2026-01-01.json"
    base_config.write_text(json.dumps({"search_parameters": {"rooms": "2"}}), encoding="utf-8")

    write_window_config(
        base_config,
        output_config,
        DateWindow(date(2026, 1, 1), date(2026, 1, 7)),
    )

    written = json.loads(output_config.read_text(encoding="utf-8"))
    assert written["search_parameters"] == {
        "rooms": "2",
        "minSoldDate": "2026-01-01",
        "maxSoldDate": "2026-01-07",
    }


def test_merge_deduped_jsonl_keeps_first_listing_id(tmp_path: Path) -> None:
    first = tmp_path / "listings_2026-01-01.jsonl"
    second = tmp_path / "listings_2026-01-08.jsonl"
    first.write_text(
        '{"listing_id": "1", "sold_date": "2026-01-02"}\n'
        '{"listing_id": "2", "sold_date": "2026-02-03"}\n',
        encoding="utf-8",
    )
    second.write_text(
        '{"listing_id": "1", "sold_date": "2026-01-09"}\n'
        '{"listing_id": "3", "sold_date": "2026-01-10"}\n',
        encoding="utf-8",
    )

    output = tmp_path / "all_dedup.jsonl"
    summary = merge_deduped_jsonl([second, first], output)

    assert summary["total_unique"] == 3
    assert summary["source_counts"] == {
        "listings_2026-01-01.jsonl": 2,
        "listings_2026-01-08.jsonl": 1,
    }
    assert summary["month_counts"] == {"2026-01": 2, "2026-02": 1}
    assert [json.loads(line)["listing_id"] for line in output.read_text().splitlines()] == [
        "1",
        "2",
        "3",
    ]


def test_run_backfill_dry_run_does_not_read_config(tmp_path: Path) -> None:
    summary = run_backfill(
        base_config_file=tmp_path / "missing.json",
        output_dir=tmp_path / "backfill",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        window_days=2,
        max_pages=20,
        concurrent_requests=2,
        delay=0.5,
        dry_run=True,
    )

    assert summary["dry_run"] is True
    assert summary["windows"] == [
        {"start": "2026-01-01", "end": "2026-01-02"},
        {"start": "2026-01-03", "end": "2026-01-03"},
    ]
