#!/usr/bin/env python3
"""CLI for migrating processed JSONL listings to BigQuery.

Usage:
    uv run python -m estate_value_index.cli migrate --data-file data/raw/booli/booli_listings_prod.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import Namespace

from estate_value_index.ingestion.bigquery_upload import upload_to_bigquery


def main(argv: list[str] | None = None, *, args: Namespace | None = None) -> int:
    """Migrate JSONL to BigQuery. ``args`` takes precedence over ``argv``."""
    if args is None:
        parser = argparse.ArgumentParser(description="Migrate JSONL data to BigQuery")
        parser.add_argument(
            "--data-file",
            type=Path,
            default=Path("data/raw/booli/booli_listings_prod.json"),
            help="Path to JSONL data file (default: data/raw/booli/booli_listings_prod.json)",
        )
        parser.add_argument(
            "--project-id",
            default=None,
            help="GCP project ID (default: from environment config)",
        )
        parser.add_argument(
            "--dataset-id",
            default=None,
            help="BigQuery dataset ID (default: from environment config)",
        )
        parser.add_argument(
            "--table-id",
            default=None,
            help="BigQuery table ID (default: from environment config)",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=None,
            help="Batch size for inserts (default: from config)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Dry run mode - don't actually write to BigQuery",
        )
        args = parser.parse_args(argv)

    if not args.data_file.exists():
        print(f"Data file not found: {args.data_file}")
        return 1

    success = upload_to_bigquery(
        data_file=args.data_file,
        project_id=args.project_id,
        dataset_id=args.dataset_id,
        table_id=args.table_id,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
