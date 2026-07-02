from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from estate_value_index.cli.backfill_booli import (
    DateWindow,
    date_windows,
    main,
    merge_deduped_jsonl,
    run_backfill,
    validate_jsonl_file,
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


def test_validate_jsonl_file_reports_valid_rate(tmp_path: Path) -> None:
    listings = tmp_path / "listings.jsonl"
    listings.write_text(
        '{"listing_id": "1", "sold_price": 1000000, "living_area": 55, "area": "Solna"}\n'
        '{"listing_id": "2", "sold_price": null, "living_area": 42, "area": "Solna"}\n'
        "not-json\n",
        encoding="utf-8",
    )

    summary = validate_jsonl_file(listings)

    assert summary["total_listings"] == 3
    assert summary["valid_listings"] == 1
    assert summary["invalid_listings"] == 2
    assert summary["validation_rate"] == pytest.approx(1 / 3)
    assert summary["missing_fields"] == ["sold_price"]
    assert summary["invalid_json"] == 1


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


def test_run_backfill_retries_window_scrape_failure(tmp_path: Path) -> None:
    base_config = tmp_path / "base.json"
    base_config.write_text(json.dumps({"search_parameters": {}}), encoding="utf-8")
    calls = 0

    def scrape(**kwargs) -> Path:
        nonlocal calls
        calls += 1
        output_file = Path(kwargs["output_file"])
        if calls == 1:
            raise RuntimeError("blocked")
        output_file.write_text(
            '{"listing_id": "1", "sold_price": 1000000, "living_area": 55, "area": "Solna"}\n',
            encoding="utf-8",
        )
        return output_file

    summary = run_backfill(
        base_config_file=base_config,
        output_dir=tmp_path / "backfill",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
        window_days=1,
        max_pages=20,
        concurrent_requests=1,
        delay=1.0,
        dry_run=False,
        max_window_retries=1,
        scrape=scrape,
    )

    assert calls == 2
    assert summary["validation"]["validation_rate"] == 1.0


def test_run_backfill_uses_api_source(tmp_path: Path) -> None:
    base_config = tmp_path / "base.json"
    base_config.write_text(json.dumps({"search_parameters": {}}), encoding="utf-8")
    seen_kwargs: dict[str, object] = {}

    def scrape(**kwargs) -> Path:
        seen_kwargs.update(kwargs)
        output_file = Path(kwargs["output_file"])
        output_file.write_text(
            '{"listing_id": "api-1", "sold_price": 1000000, "living_area": 55, "area": "Solna"}\n',
            encoding="utf-8",
        )
        return output_file

    summary = run_backfill(
        base_config_file=base_config,
        output_dir=tmp_path / "backfill",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
        window_days=1,
        max_pages=3,
        concurrent_requests=1,
        delay=1.0,
        dry_run=False,
        source="api",
        scrape=scrape,
    )

    assert seen_kwargs["max_pages"] == 3
    assert summary["source"] == "api"
    assert summary["merge"]["total_unique"] == 1


def test_run_backfill_fails_after_low_validation_retry(tmp_path: Path) -> None:
    base_config = tmp_path / "base.json"
    base_config.write_text(json.dumps({"search_parameters": {}}), encoding="utf-8")

    def scrape(**kwargs) -> Path:
        output_file = Path(kwargs["output_file"])
        output_file.write_text('{"listing_id": "1"}\n', encoding="utf-8")
        return output_file

    with pytest.raises(RuntimeError, match="validation rate"):
        run_backfill(
            base_config_file=base_config,
            output_dir=tmp_path / "backfill",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 1),
            window_days=1,
            max_pages=20,
            concurrent_requests=1,
            delay=1.0,
            dry_run=False,
            max_window_retries=1,
            min_validation_rate=0.5,
            scrape=scrape,
        )


def test_api_source_missing_credentials_returns_clean_error(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.delenv("BOOLI_API_CALLER_ID", raising=False)
    monkeypatch.delenv("BOOLI_API_PRIVATE_KEY", raising=False)

    code = main(
        [
            "--source",
            "api",
            "--start-date",
            "2026-04-27",
            "--end-date",
            "2026-04-27",
            "--output-dir",
            str(tmp_path / "out"),
            "--max-pages",
            "1",
            "--max-window-retries",
            "0",
        ]
    )

    captured = capsys.readouterr()
    assert code == 1
    assert "BOOLI_API_CALLER_ID" in captured.err
    assert "Traceback" not in captured.err
