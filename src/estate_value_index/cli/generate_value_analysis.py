#!/usr/bin/env python3
"""CLI entrypoint for generating value analysis data.

Computation lives in `estate_value_index.analytics.value_analysis`; this module
is a thin argparse shell that drives those helpers with verbose progress output.

Usage:
    uv run python -m estate_value_index.cli value-analysis
    uv run python -m estate_value_index.cli value-analysis --data-file data/raw/booli/custom.json
    uv run python -m estate_value_index.cli value-analysis --model-type no_list
    uv run python -m estate_value_index.cli value-analysis --output data/custom_analysis.json
"""

from __future__ import annotations

import argparse
from pathlib import Path

from estate_value_index.analytics.value_analysis import run_analysis


def main(argv: list[str] | None = None, *, args=None) -> int:
    if args is None:
        parser = argparse.ArgumentParser(
            description="Generate value analysis by running predictions on production data"
        )
        parser.add_argument(
            "--data-file",
            type=Path,
            default=Path("data/raw/booli/booli_listings_prod.json"),
            help="Path to production data JSON file",
        )
        parser.add_argument(
            "--model-type",
            type=str,
            default="no_list",
            choices=["no_list", "listing", "baseline"],
            help="Model type to use for predictions",
        )
        parser.add_argument(
            "--model-prefix", type=str, default="price_prediction_model", help="Model file prefix"
        )
        parser.add_argument(
            "--models-dir",
            type=Path,
            default=Path("web/models"),
            help="Directory containing trained models",
        )
        parser.add_argument(
            "--output",
            type=Path,
            default=Path("data/derived/value_analysis.json"),
            help="Output path for value analysis JSON",
        )
        parser.add_argument(
            "--min-value-score",
            type=float,
            help="Only include properties with value_score >= this threshold",
        )
        parser.add_argument(
            "--only-undervalued",
            action="store_true",
            help="Only include undervalued properties (exceeding threshold)",
        )
        parser.add_argument(
            "--undervalue-threshold-pct",
            type=float,
            default=5.0,
            help="Percentage threshold for undervalued (default: 5%%)",
        )
        parser.add_argument(
            "--undervalue-threshold-abs",
            type=float,
            default=200000,
            help="Absolute SEK threshold for undervalued (default: 200,000 SEK)",
        )
        parser.add_argument(
            "--no-training-filters",
            action="store_true",
            help="Skip applying training filters (min_price, outlier removal). By default, applies same filters as training.",
        )
        args = parser.parse_args(argv)

    print("=" * 70)
    print("VALUE ANALYSIS GENERATOR")
    print("=" * 70)
    print(f"\nModel: {args.model_type} ({args.model_prefix})")
    print(f"Data file: {args.data_file}")
    print(
        f"Undervalue threshold: {args.undervalue_threshold_pct}% OR "
        f"{args.undervalue_threshold_abs:,.0f} SEK"
    )

    output = run_analysis(
        data_file=args.data_file,
        model_type=args.model_type,
        output_file=args.output,
        models_dir=args.models_dir,
        model_prefix=args.model_prefix,
        apply_training_filters=not args.no_training_filters,
        undervalue_threshold_pct=args.undervalue_threshold_pct,
        undervalue_threshold_abs=args.undervalue_threshold_abs,
        only_undervalued=args.only_undervalued,
        min_value_score=args.min_value_score,
    )
    stats = output["statistics"]
    properties = output["properties"]

    print(f"\nValue analysis saved to: {args.output}")
    print(f"   Total properties: {len(properties):,}")
    print(
        f"   Undervalued: {stats['undervalued_count']:,} ({stats['undervalued_percentage']:.1f}%)"
    )
    print(f"   Overvalued: {stats['overvalued_count']:,}")
    print(f"   Average value score: {stats['value_score']['mean']:.1f}")
    print(f"   Top value score: {stats['value_score']['max']:.1f}")

    print("\nTop 5 areas with undervalued properties:")
    for area, count in list(stats["area_statistics"]["top_undervalued_areas"].items())[:5]:
        print(f"   {area}: {count} properties")

    print("\nValue tier distribution:")
    for tier, count in sorted(
        stats["value_tier_distribution"].items(), key=lambda x: x[1], reverse=True
    ):
        print(f"   {tier}: {count} properties")

    print("\n" + "=" * 70)
    print("Analysis complete!")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    main()
