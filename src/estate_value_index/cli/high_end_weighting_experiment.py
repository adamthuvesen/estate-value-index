from __future__ import annotations

import argparse
from pathlib import Path

from estate_value_index.analytics.high_end_weighting import (
    DEFAULT_CURVE_POWER,
    DEFAULT_DATA_FILE,
    DEFAULT_MAX_WEIGHT,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_START_QUANTILE,
    run_high_end_weighting_experiment,
)


def main(argv: list[str] | None = None, *, args=None) -> int:
    if args is None:
        parser = argparse.ArgumentParser(description="Run high-end sample weighting experiments")
        parser.add_argument("--data-file", type=Path, default=DEFAULT_DATA_FILE)
        parser.add_argument("--feature-set", default="no_list_price_h3_market")
        parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
        parser.add_argument("--splits", type=int, default=4)
        parser.add_argument("--start-quantile", type=float, default=DEFAULT_START_QUANTILE)
        parser.add_argument("--max-weight", type=float, default=DEFAULT_MAX_WEIGHT)
        parser.add_argument("--curve-power", type=float, default=DEFAULT_CURVE_POWER)
        args = parser.parse_args(argv)

    result = run_high_end_weighting_experiment(
        data_file=args.data_file,
        feature_set=args.feature_set,
        output_dir=args.output_dir,
        n_splits=args.splits,
        start_quantile=args.start_quantile,
        max_weight=args.max_weight,
        curve_power=args.curve_power,
    )
    unweighted = result["unweighted_blend"]
    weighted = result["weighted_blend"]
    hybrid = result["hybrid_blend"]
    best_name = result["best_weighted_model"]
    best = result[best_name]
    weighted_selection = result["blend_selection"]["weighted"]
    print(f"High-end weighting experiment complete: {args.feature_set}")
    print(
        f"Unweighted blend MAE: {unweighted['mae']:,.0f} SEK; "
        f"bias: {unweighted['mean_bias']:,.0f} SEK"
    )
    print(
        f"Weighted blend MAE: {weighted['mae']:,.0f} SEK; "
        f"bias: {weighted['mean_bias']:,.0f} SEK; "
        f"normalized weight: {weighted_selection['normalized_weight']:.2f}"
    )
    print(f"Hybrid blend MAE: {hybrid['mae']:,.0f} SEK; bias: {hybrid['mean_bias']:,.0f} SEK")
    print(f"Best weighted challenger: {best_name}; MAE: {best['mae']:,.0f} SEK")
    print(f"Output directory: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
