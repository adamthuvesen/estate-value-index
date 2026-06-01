#!/usr/bin/env python3
"""CLI entrypoint for generating value analysis data.

Computation lives in `estate_value_index.analytics.value_analysis`; this module
is a thin argparse shell that drives those helpers with verbose progress output.

Usage:
    uv run python -m estate_value_index.cli value-analysis
    uv run python -m estate_value_index.cli value-analysis --data-file data/raw/booli/custom.json
    uv run python -m estate_value_index.cli value-analysis --model-type lgbm
    uv run python -m estate_value_index.cli value-analysis --output data/custom_analysis.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error

from estate_value_index.analytics.value_analysis import (
    calculate_value_metrics,
    generate_summary_statistics,
    load_model,
    load_production_data,
    prepare_output_records,
)


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
            default="lgbm",
            choices=["lgbm", "xgb", "linear", "baseline"],
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
            default=Path("data/enrichment/value_analysis.json"),
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

    # Load data with optional training filters
    apply_filters = not args.no_training_filters
    df = load_production_data(args.data_file, apply_training_filters=apply_filters)

    # Load model
    model, metrics = load_model(args.models_dir, args.model_type, args.model_prefix)

    # Generate predictions
    print("\nGenerating predictions...")
    try:
        predictions = model.predict(df)
        df["predicted_price"] = predictions
        print(f"   Generated {len(predictions):,} predictions")

        # Calculate overall prediction quality
        mae = mean_absolute_error(df["sold_price"], predictions)
        rmse = np.sqrt(mean_squared_error(df["sold_price"], predictions))
        print(f"   Prediction MAE: {mae:,.0f} SEK")
        print(f"   Prediction RMSE: {rmse:,.0f} SEK")

    except Exception as e:
        print(f"Prediction failed: {e}")
        raise

    # Calculate value metrics
    print("\nCalculating value metrics...")
    print(
        f"   Undervalue threshold: {args.undervalue_threshold_pct}% OR {args.undervalue_threshold_abs:,.0f} SEK"
    )
    df = calculate_value_metrics(
        df,
        undervalue_threshold_pct=args.undervalue_threshold_pct,
        undervalue_threshold_abs=args.undervalue_threshold_abs,
    )

    # Apply filters if specified
    if args.only_undervalued:
        df = df[df["is_undervalued"]].copy()
        print(f"   Filtered to {len(df):,} undervalued properties (exceeding threshold)")

    if args.min_value_score:
        df = df[df["value_score"] >= args.min_value_score].copy()
        print(f"   Filtered to {len(df):,} properties with score >= {args.min_value_score}")

    # Generate summary statistics
    print("\nGenerating summary statistics...")
    stats = generate_summary_statistics(df, metrics)

    # Prepare output
    properties = prepare_output_records(df)

    # Sort by value_score descending (best deals first)
    properties_sorted = sorted(properties, key=lambda x: x["value_score"], reverse=True)

    # Create output structure
    output = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "model_type": args.model_type,
            "model_path": str(args.models_dir / f"{args.model_prefix}_{args.model_type}.joblib"),
            "data_source": str(args.data_file),
            "filters": {
                "only_undervalued": args.only_undervalued,
                "min_value_score": args.min_value_score,
                "training_filters_applied": not args.no_training_filters,
            },
            "thresholds": {
                "undervalue_threshold_pct": args.undervalue_threshold_pct,
                "undervalue_threshold_abs": args.undervalue_threshold_abs,
            },
        },
        "statistics": stats,
        "properties": properties_sorted,
    }

    # Save output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nValue analysis saved to: {args.output}")
    print(f"   Total properties: {len(properties_sorted):,}")
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
