#!/usr/bin/env python3
"""CLI to process scraped Booli listings (merge + clean + impute).

Usage:
    uv run python -m estate_value_index.cli process --input data/raw/booli/booli_listings_*.json
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import Namespace

from estate_value_index.ingestion.processing import process_pipeline


def main(argv: list[str] | None = None, *, args: Namespace | None = None) -> int:
    """Process scraped Booli listings. ``args`` takes precedence over ``argv``."""
    if args is None:
        parser = argparse.ArgumentParser(
            description="Process scraped Booli listings: merge, clean areas, and impute missing values",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Process new scrape and update production data
  uv run python -m estate_value_index.cli process --input data/raw/booli/booli_listings_20251002.json

  # Dry run to preview changes
  uv run python -m estate_value_index.cli process --input new_scrape.json --dry-run

  # Custom parameters
  uv run python -m estate_value_index.cli process --input new_scrape.json --min-area-count 3 --days-threshold 500
            """,
        )

        parser.add_argument(
            "--input",
            type=Path,
            required=True,
            help="Path to new scraped listings file (JSON or JSONL)",
        )
        parser.add_argument(
            "--production",
            type=Path,
            default=Path("data/raw/booli/booli_listings_prod.json"),
            help="Path to existing production data file (default: data/raw/booli/booli_listings_prod.json)",
        )
        parser.add_argument(
            "--output",
            type=Path,
            default=None,
            help="Path to output file (default: same as --production, overwrites it)",
        )
        parser.add_argument(
            "--min-area-count",
            type=int,
            default=5,
            help="Minimum listings per area before consolidation (default: 5)",
        )
        parser.add_argument(
            "--days-threshold",
            type=int,
            default=1000,
            help="Threshold for days_on_market imputation (default: 1000)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without writing output file",
        )
        args = parser.parse_args(argv)

    output_file = args.output if args.output else args.production

    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}")
        return 1

    if not args.production.exists():
        print(f"Warning: Production file not found: {args.production}")
        print("   Will create new production file from input data only")

    try:
        return process_pipeline(
            input_file=args.input,
            production_file=args.production,
            output_file=output_file,
            min_area_count=args.min_area_count,
            days_threshold=args.days_threshold,
            dry_run=args.dry_run,
        )
    except Exception as e:
        print(f"\nError: Pipeline failed: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
