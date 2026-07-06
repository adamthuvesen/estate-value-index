from __future__ import annotations

import argparse
from pathlib import Path

from estate_value_index.analytics.ppsqm_blend import (
    DEFAULT_DATA_FILE,
    DEFAULT_OUTPUT_DIR,
    run_ppsqm_blend_experiment,
)


def main(argv: list[str] | None = None, *, args=None) -> int:
    if args is None:
        parser = argparse.ArgumentParser(description="Run PPSQM target blend experiments")
        parser.add_argument("--data-file", type=Path, default=DEFAULT_DATA_FILE)
        parser.add_argument("--feature-set", default="no_list_price_h3_comps")
        parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
        parser.add_argument("--splits", type=int, default=4)
        args = parser.parse_args(argv)

    result = run_ppsqm_blend_experiment(
        data_file=args.data_file,
        feature_set=args.feature_set,
        output_dir=args.output_dir,
        n_splits=args.splits,
    )
    base = result["base"]
    ppsqm = result["ppsqm"]
    blend = result["blend"]
    selection = result["blend_selection"]
    print(f"PPSQM blend experiment complete: {args.feature_set}")
    print(f"Base MAE: {base['mae']:,.0f} SEK; bias: {base['mean_bias']:,.0f} SEK")
    print(f"PPSQM MAE: {ppsqm['mae']:,.0f} SEK; bias: {ppsqm['mean_bias']:,.0f} SEK")
    print(
        "Blend MAE: "
        f"{blend['mae']:,.0f} SEK; bias: {blend['mean_bias']:,.0f} SEK; "
        f"PPSQM weight: {selection['ppsqm_weight']:.2f}"
    )
    print(f"Output directory: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
