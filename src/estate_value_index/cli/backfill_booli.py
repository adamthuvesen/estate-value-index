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

from estate_value_index.ingestion.booli.api import scrape_booli_api_window
from estate_value_index.pipelines.core.data_pipeline import run_scrapy_spider

if TYPE_CHECKING:
    from argparse import Namespace

DEFAULT_CONFIG_FILE = Path("src/estate_value_index/ingestion/config/booli_all_locations.json")
DEFAULT_OUTPUT_ROOT = Path("data/raw/booli")
DEFAULT_START_DATE = date(2025, 12, 22)
REQUIRED_LISTING_FIELDS = ("listing_id", "sold_price", "living_area", "area")


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
    if not base_config_file.exists():
        raise FileNotFoundError(f"Booli base config not found: {base_config_file}")
    try:
        config = json.loads(base_config_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid Booli base config JSON: {base_config_file}") from exc
    if not isinstance(config, dict):
        raise ValueError(f"Booli base config must be a JSON object: {base_config_file}")

    search_parameters = config.setdefault("search_parameters", {})
    if not isinstance(search_parameters, dict):
        raise ValueError(f"Booli base config search_parameters must be an object: {base_config_file}")
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


def validate_jsonl_file(path: Path) -> dict[str, Any]:
    total = 0
    valid = 0
    missing_fields: set[str] = set()
    invalid_json = 0

    with path.open(encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            total += 1
            try:
                listing = json.loads(line)
            except json.JSONDecodeError:
                invalid_json += 1
                continue

            missing = [
                field
                for field in REQUIRED_LISTING_FIELDS
                if field not in listing
                or listing[field] is None
                or (isinstance(listing[field], str) and not listing[field].strip())
            ]
            if missing:
                missing_fields.update(missing)
                continue
            valid += 1

    return {
        "total_listings": total,
        "valid_listings": valid,
        "invalid_listings": total - valid,
        "validation_rate": valid / total if total else 0.0,
        "missing_fields": sorted(missing_fields),
        "invalid_json": invalid_json,
    }


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
    source: str = "spider",
    max_window_retries: int = 2,
    min_validation_rate: float = 0.5,
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
            "source": source,
            "max_window_retries": max_window_retries,
            "min_validation_rate": min_validation_rate,
        }

    if source == "spider":
        scrape_fn = scrape or getattr(run_scrapy_spider, "fn", run_scrapy_spider)
    elif source == "api":
        scrape_fn = scrape or scrape_booli_api_window
    else:
        raise ValueError(f"unsupported backfill source: {source}")

    listing_files: list[Path] = []
    window_counts: dict[str, int] = {}
    window_validation: dict[str, dict[str, Any]] = {}

    for window in windows:
        config_file = output_dir / f"config_{window.label}.json"
        output_file = output_dir / f"listings_{window.label}.jsonl"
        write_window_config(base_config_file, config_file, window)

        last_error: Exception | None = None
        scraped_file: Path | None = None
        for attempt in range(max_window_retries + 1):
            output_file.unlink(missing_ok=True)
            try:
                scraped_file = Path(
                    scrape_fn(
                        max_pages=max_pages,
                        concurrent_requests=concurrent_requests,
                        delay=delay,
                        config_file=str(config_file),
                        output_file=output_file,
                    )
                )
                validation = validate_jsonl_file(scraped_file)
                window_validation[window.label] = validation
                if validation["total_listings"] == 0:
                    raise RuntimeError(f"zero scraped rows for window {window.label}")
                if validation["validation_rate"] < min_validation_rate:
                    raise RuntimeError(
                        "validation rate "
                        f"{validation['validation_rate']:.1%} below "
                        f"{min_validation_rate:.1%} for window {window.label}"
                    )
                break
            except Exception as exc:
                last_error = exc
                if attempt >= max_window_retries:
                    raise

        if scraped_file is None:
            raise RuntimeError(f"Backfill window {window.label} failed") from last_error

        listing_files.append(scraped_file)
        window_counts[window.label] = count_jsonl_records(scraped_file)

    merged_file = output_dir / "all_dedup.jsonl"
    merge_summary = merge_deduped_jsonl(listing_files, merged_file)
    merged_validation = validate_jsonl_file(merged_file)
    if merged_validation["total_listings"] == 0:
        raise RuntimeError("zero merged rows after backfill")

    return {
        "dry_run": False,
        "source": source,
        "output_dir": str(output_dir),
        "window_counts": window_counts,
        "window_validation": window_validation,
        "merge": merge_summary,
        "validation": merged_validation,
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
    parser.add_argument("--source", choices=("spider", "api"), default="spider")
    parser.add_argument("--max-window-retries", type=int, default=2)
    parser.add_argument("--min-validation-rate", type=float, default=0.5)
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
    if args.max_window_retries < 0:
        parser.error("--max-window-retries must be >= 0")
    if not 0 <= args.min_validation_rate <= 1:
        parser.error("--min-validation-rate must be between 0 and 1")

    try:
        start_date = _parse_date(args.start_date, DEFAULT_START_DATE)
        end_date = _parse_date(args.end_date, date.today())
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))

    output_dir = args.output_dir or _default_output_dir()

    try:
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
            source=args.source,
            max_window_retries=args.max_window_retries,
            min_validation_rate=args.min_validation_rate,
        )
    except (RuntimeError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

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
