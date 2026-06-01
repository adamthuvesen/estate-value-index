#!/usr/bin/env python3
"""CLI for materializing engineered features to BigQuery.

Usage:
    uv run python -m estate_value_index.cli features --truncate
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import Namespace

from estate_value_index.ml.feature_materialization import materialize_features


def main(argv: list[str] | None = None, *, args: Namespace | None = None) -> int:
    """Materialize engineered features. ``args`` takes precedence over ``argv``."""
    if args is None:
        parser = argparse.ArgumentParser(description="Materialize engineered features to BigQuery")
        parser.add_argument(
            "--project-id",
            type=str,
            default=None,
            help="GCP project ID (default: from environment config)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Compute features but don't upload to BigQuery",
        )
        parser.add_argument(
            "--truncate",
            action="store_true",
            help="Clear existing features before uploading",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=None,
            help="Number of rows to insert per batch (default: from config)",
        )
        args = parser.parse_args(argv)

    try:
        materialize_features(
            project_id=args.project_id,
            dry_run=args.dry_run,
            truncate=args.truncate,
            batch_size=args.batch_size,
        )
        return 0
    except Exception as e:
        print(f"Feature materialization failed: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
