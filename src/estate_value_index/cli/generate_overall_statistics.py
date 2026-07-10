#!/usr/bin/env python3
"""CLI entrypoint for generating city-wide statistics for the web Stats page.

Computation lives in `estate_value_index.analytics.overall_statistics`; this
module is a thin argparse shell over `generate_overall_statistics`.
"""

import argparse
import os
from pathlib import Path

from estate_value_index.analytics.overall_statistics import generate_overall_statistics


def main(argv: list[str] | None = None, *, args=None) -> int:
    if args is None:
        parser = argparse.ArgumentParser(description="Generate city-wide statistics for the web UI")
        parser.add_argument(
            "--data-source",
            choices=["bigquery", "json"],
            default=os.getenv("DATA_SOURCE", "bigquery"),
            help=(
                "Primary data source for raw listings (default: bigquery; falls "
                "back to json when bigquery returns no rows or its client is "
                "unavailable — query/auth failures are surfaced, not hidden)"
            ),
        )
        parser.add_argument(
            "--value-analysis", type=str, default=None, help="Path to value_analysis.json"
        )
        parser.add_argument(
            "--raw-listings", type=str, default=None, help="Path to booli_listings_prod.json"
        )
        parser.add_argument(
            "--output", type=str, default=None, help="Output path for overall_statistics.json"
        )
        args = parser.parse_args(argv)

    generate_overall_statistics(
        data_source=args.data_source or os.getenv("DATA_SOURCE", "bigquery"),
        value_analysis_path=Path(args.value_analysis) if args.value_analysis else None,
        raw_listings_path=Path(args.raw_listings) if args.raw_listings else None,
        output_path=Path(args.output) if args.output else None,
    )
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
