from __future__ import annotations

import argparse
from pathlib import Path

from estate_value_index.experiments.feature_count import (
    DEFAULT_DATA_FILE,
    DEFAULT_FEATURE_COUNTS,
    DEFAULT_OUTPUT_DIR,
    run_feature_count_experiment,
    run_recursive_feature_count_experiment,
)


def main(argv: list[str] | None = None, *, args=None) -> int:
    if args is None:
        parser = argparse.ArgumentParser(description="Run top-k feature count experiments")
        parser.add_argument("--data-file", type=Path, default=DEFAULT_DATA_FILE)
        parser.add_argument("--feature-set", default="no_list_price_h3_market_street")
        parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
        parser.add_argument("--counts", type=int, nargs="+", default=list(DEFAULT_FEATURE_COUNTS))
        parser.add_argument(
            "--method",
            choices=["one-shot", "rfe"],
            default="one-shot",
            help="Feature selection method: full-model one-shot ranking or recursive elimination.",
        )
        parser.add_argument(
            "--normalized-weight",
            type=float,
            required=True,
            help="Fixed market-normalized blend weight from the full OOF experiment.",
        )
        args = parser.parse_args(argv)

    runner = (
        run_recursive_feature_count_experiment
        if args.method == "rfe"
        else run_feature_count_experiment
    )
    result = runner(
        data_file=args.data_file,
        feature_set=args.feature_set,
        output_dir=args.output_dir,
        feature_counts=tuple(args.counts),
        normalized_weight=args.normalized_weight,
    )
    baseline = result["baseline_full"]["blend"]
    best = min(result["evaluations"], key=lambda evaluation: evaluation["blend"]["mae"])
    print(f"Feature count experiment complete: {args.feature_set}")
    print(f"Full feature MAE: {baseline['mae']:,.0f} SEK; bias: {baseline['mean_bias']:,.0f} SEK")
    print(
        f"Best top-k: {best['feature_count']} features; "
        f"MAE: {best['blend']['mae']:,.0f} SEK; "
        f"delta: {best['delta_vs_full']['mae']:,.0f} SEK"
    )
    print(f"Output directory: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
