"""Backfill Booli listings over sold-date windows."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from estate_value_index.pipelines.core.data_pipeline import run_scrapy_spider

if TYPE_CHECKING:
    from argparse import Namespace

DEFAULT_CONFIG_FILE = Path("src/estate_value_index/ingestion/config/booli_all_locations.json")
DEFAULT_OUTPUT_ROOT = Path("data/raw/booli")
DEFAULT_START_DATE = date(2025, 12, 22)


@dataclass(frozen=True)
class DateWindow:
    start: date
    end: date

    @property
    def label(self) -> str:
        return self.start.isoformat()


def date_windows(start: date, end: date, window_days: int) -> Iterator[DateWindow]:
    if window_days < 1:
        raise ValueError("window_days must be >= 1")
    if start > end:
        raise ValueError("start date must be <= end date")

    current = start
    step = timedelta(days=window_days)
    while current <= end:
        window_end = min(current + step - timedelta(days=1), end)
        yield DateWindow(start=current, end=window_end)
        current = window_end + timedelta(days=1)


def write_window_config(base_config_file: Path, output_file: Path, window: DateWindow) -> None:
    config = json.loads(base_config_file.read_text(encoding="utf-8"))
    search_parameters = config.setdefault("search_parameters", {})
    search_parameters["minSoldDate"] = window.start.isoformat()
    search_parameters["maxSoldDate"] = window.end.isoformat()

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def count_jsonl_records(path: Path) -> int:
    with path.open(encoding="utf-8") as file:
        return sum(1 for line in file if line.strip())


def merge_deduped_jsonl(input_files: Iterable[Path], output_file: Path) -> dict[str, Any]:
    seen_listing_ids: set[str] = set()
    month_counts: Counter[str] = Counter()
    source_counts: dict[str, int] = {}

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as output:
        for input_file in sorted(input_files):
            new_records = 0
            with input_file.open(encoding="utf-8") as source:
                for line in source:
                    if not line.strip():
                        continue
                    listing = json.loads(line)
                    listing_id = listing.get("listing_id")
                    if not listing_id or listing_id in seen_listing_ids:
                        continue

                    seen_listing_ids.add(listing_id)
                    output.write(line)
                    new_records += 1

                    sold_date = listing.get("sold_date")
                    if sold_date:
                        month_counts[str(sold_date)[:7]] += 1
            source_counts[input_file.name] = new_records

    return {
        "output_file": str(output_file),
        "total_unique": len(seen_listing_ids),
        "source_counts": source_counts,
        "month_counts": dict(sorted(month_counts.items())),
    }


def run_backfill(
    *,
    base_config_file: Path,
    output_dir: Path,
    start_date: date,
    end_date: date,
    window_days: int,
    max_pages: int,
    concurrent_requests: int,
    delay: float,
    dry_run: bool,
    scrape: Callable[..., Path] | None = None,
) -> dict[str, Any]:
    windows = list(date_windows(start_date, end_date, window_days))
    output_dir.mkdir(parents=True, exist_ok=True)

    if dry_run:
        return {
            "dry_run": True,
            "output_dir": str(output_dir),
            "windows": [
                {"start": window.start.isoformat(), "end": window.end.isoformat()}
                for window in windows
            ],
        }

    scrape_fn = scrape or getattr(run_scrapy_spider, "fn", run_scrapy_spider)
    listing_files: list[Path] = []
    window_counts: dict[str, int] = {}

    for window in windows:
        config_file = output_dir / f"config_{window.label}.json"
        output_file = output_dir / f"listings_{window.label}.jsonl"
        write_window_config(base_config_file, config_file, window)

        scraped_file = Path(
            scrape_fn(
                max_pages=max_pages,
                concurrent_requests=concurrent_requests,
                delay=delay,
                config_file=str(config_file),
                output_file=output_file,
            )
        )
        listing_files.append(scraped_file)
        window_counts[window.label] = count_jsonl_records(scraped_file)

    merged_file = output_dir / "all_dedup.jsonl"
    merge_summary = merge_deduped_jsonl(listing_files, merged_file)

    return {
        "dry_run": False,
        "output_dir": str(output_dir),
        "window_counts": window_counts,
        "merge": merge_summary,
    }


def _parse_date(value: str | date | None, default: date) -> date:
    if value is None:
        return default
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid ISO date: {value}") from exc


def _default_output_dir() -> Path:
    return DEFAULT_OUTPUT_ROOT / f"backfill_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def add_arguments(parser: argparse.ArgumentParser, *, include_json: bool = True) -> None:
    parser.add_argument("--base-config", type=Path, default=DEFAULT_CONFIG_FILE)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--start-date", default=DEFAULT_START_DATE.isoformat())
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--concurrent", type=int, default=2)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--dry-run", action="store_true")
    if include_json:
        parser.add_argument("--json", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill Booli listings over sold-date windows")
    add_arguments(parser)
    return parser


def main(argv: list[str] | None = None, *, args: Namespace | None = None) -> int:
    parser = build_parser()
    if args is None:
        args = parser.parse_args(argv)

    if args.max_pages < 1:
        parser.error("--max-pages must be >= 1")
    if args.concurrent < 1:
        parser.error("--concurrent must be >= 1")
    if args.delay < 0:
        parser.error("--delay must be >= 0")

    try:
        start_date = _parse_date(args.start_date, DEFAULT_START_DATE)
        end_date = _parse_date(args.end_date, date.today())
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))

    output_dir = args.output_dir or _default_output_dir()

    summary = run_backfill(
        base_config_file=args.base_config,
        output_dir=output_dir,
        start_date=start_date,
        end_date=end_date,
        window_days=args.window_days,
        max_pages=args.max_pages,
        concurrent_requests=args.concurrent,
        delay=args.delay,
        dry_run=args.dry_run,
    )

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"Output: {summary['output_dir']}")
        if summary["dry_run"]:
            print(f"Windows: {len(summary['windows'])}")
        else:
            print(f"Merged: {summary['merge']['total_unique']} unique listings")
            print(f"File: {summary['merge']['output_file']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
