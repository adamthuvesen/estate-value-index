from __future__ import annotations

import argparse
from pathlib import Path

from estate_value_index.ml.market_normalized_target import (
    DEFAULT_DATA_FILE,
    DEFAULT_OUTPUT_DIR,
    run_market_normalized_experiment,
)


def main(argv: list[str] | None = None, *, args=None) -> int:
    if args is None:
        parser = argparse.ArgumentParser(description="Run market-normalized target experiments")
        parser.add_argument("--data-file", type=Path, default=DEFAULT_DATA_FILE)
        parser.add_argument("--feature-set", default="no_list_price_h3_market")
        parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
        parser.add_argument("--splits", type=int, default=4)
        args = parser.parse_args(argv)

    result = run_market_normalized_experiment(
        data_file=args.data_file,
        feature_set=args.feature_set,
        output_dir=args.output_dir,
        n_splits=args.splits,
    )
    base = result["base"]
    normalized = result["normalized"]
    blend = result["blend"]
    selection = result["blend_selection"]
    print(f"Market-normalized target experiment complete: {args.feature_set}")
    print(f"Base MAE: {base['mae']:,.0f} SEK; bias: {base['mean_bias']:,.0f} SEK")
    print(f"Normalized MAE: {normalized['mae']:,.0f} SEK; bias: {normalized['mean_bias']:,.0f} SEK")
    print(
        "Blend MAE: "
        f"{blend['mae']:,.0f} SEK; bias: {blend['mean_bias']:,.0f} SEK; "
        f"normalized weight: {selection['normalized_weight']:.2f}"
    )
    print(f"Output directory: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
