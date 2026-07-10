#!/usr/bin/env python3
"""CLI for monitoring GCP costs.

Usage:
    uv run python -m estate_value_index.cli costs [--project-id PROJECT] [--bucket BUCKET] [--days 7]
"""

from __future__ import annotations

import argparse
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import Namespace

from estate_value_index.monitoring.cost_monitoring import (
    monitor_bigquery_costs,
    monitor_gcs_costs,
    monitor_vertex_ai_costs,
)


def main(argv: list[str] | None = None, *, args: Namespace | None = None) -> int:
    """Monitor GCP costs. ``args`` takes precedence over ``argv`` when given."""
    if args is None:
        parser = argparse.ArgumentParser(description="Monitor GCP costs for the project")
        parser.add_argument(
            "--project-id",
            default=os.getenv("GCP_PROJECT_ID"),
            help="GCP project ID (default: from GCP_PROJECT_ID env var)",
        )
        parser.add_argument(
            "--bucket",
            default=os.getenv("GCS_BUCKET"),
            help="GCS bucket name (default: from GCS_BUCKET env var)",
        )
        parser.add_argument("--region", default=os.getenv("GCP_REGION", "europe-north1"))
        parser.add_argument("--days", type=int, default=7)
        parser.add_argument("--bigquery-only", action="store_true")
        parser.add_argument("--gcs-only", action="store_true")
        parser.add_argument("--vertex-only", action="store_true")
        args = parser.parse_args(argv)

    if not args.project_id:
        print("Error: --project-id is required (or set GCP_PROJECT_ID env var)")
        return 1
    if args.gcs_only and not args.bucket:
        print("Error: --bucket is required when --gcs-only is set")
        return 1

    if not args.gcs_only and not args.vertex_only:
        monitor_bigquery_costs(args.project_id, args.days)
    if not args.bigquery_only and not args.vertex_only and args.bucket:
        monitor_gcs_costs(args.bucket)
    if not args.bigquery_only and not args.gcs_only:
        monitor_vertex_ai_costs(args.project_id, args.region, args.days)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
