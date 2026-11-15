"""``evi backfill``: fetch Booli listings by sold-date window, then optionally process and load."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from estate_value_index.exceptions import EstateValueIndexError
from estate_value_index.ingestion.ingest import DEFAULT_CONFIG_FILE, ingest_listings

if TYPE_CHECKING:
    from argparse import Namespace

DEFAULT_OUTPUT_ROOT = Path("data/raw/booli")
DEFAULT_START_DATE = date(2025, 12, 22)


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
    parser.add_argument("--max-window-retries", type=int, default=2)
    parser.add_argument("--min-validation-rate", type=float, default=0.5)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--process",
        action="store_true",
        help="Merge the fetched rows into the production listings file (clean areas, impute).",
    )
    parser.add_argument(
        "--load",
        action="store_true",
        help="Process, then write BigQuery, geocode new addresses, sync back, and back up to GCS.",
    )
    parser.add_argument(
        "--approved",
        action="store_true",
        help="Allow the BigQuery and GCS writes that --load makes.",
    )
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
        summary = ingest_listings(
            base_config_file=args.base_config,
            output_dir=output_dir,
            start_date=start_date,
            end_date=end_date,
            window_days=args.window_days,
            max_pages=args.max_pages,
            dry_run=args.dry_run,
            max_window_retries=args.max_window_retries,
            min_validation_rate=args.min_validation_rate,
            process=args.process,
            load=args.load,
            approved=args.approved,
        )
    except (EstateValueIndexError, RuntimeError, OSError, ValueError) as exc:
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
