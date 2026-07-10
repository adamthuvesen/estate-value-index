from __future__ import annotations

import argparse
from pathlib import Path

from estate_value_index.experiments.model_suite import (
    DEFAULT_DATA_FILE,
    DEFAULT_LISTING_FEATURE_SET,
    DEFAULT_NO_LIST_FEATURE_SET,
    DEFAULT_OUTPUT_DIR,
    run_model_suite_experiment,
)


def main(argv: list[str] | None = None, *, args=None) -> int:
    if args is None:
        parser = argparse.ArgumentParser(description="Run the four-variant model suite experiment")
        parser.add_argument("--data-file", type=Path, default=DEFAULT_DATA_FILE)
        parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
        parser.add_argument("--splits", type=int, default=4)
        parser.add_argument("--no-list-feature-set", default=DEFAULT_NO_LIST_FEATURE_SET)
        parser.add_argument("--listing-feature-set", default=DEFAULT_LISTING_FEATURE_SET)
        args = parser.parse_args(argv)

    result = run_model_suite_experiment(
        data_file=args.data_file,
        output_dir=args.output_dir,
        no_list_feature_set=args.no_list_feature_set,
        listing_feature_set=args.listing_feature_set,
        n_splits=args.splits,
    )
    print("Model suite experiment complete")
    for name, variant in result["variants"].items():
        metrics = variant["metrics"]
        print(
            f"{name}: MAE {metrics['mae']:,.0f} SEK; "
            f"bias {metrics['mean_bias']:,.0f} SEK; "
            f"within 10% {metrics['within_10_pct']:.2f}%"
        )
    print(f"Output directory: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
