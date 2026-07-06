from __future__ import annotations

import argparse
from pathlib import Path

from estate_value_index.analytics.tiered_ensemble import (
    DEFAULT_DATA_FILE,
    DEFAULT_GATE_HIGH_MIN,
    DEFAULT_GATE_LOW_MAX,
    DEFAULT_HIGH_MIN_PRICE,
    DEFAULT_LOW_MAX_PRICE,
    DEFAULT_MID_MAX_PRICE,
    DEFAULT_MID_MIN_PRICE,
    DEFAULT_MIN_SEGMENT_ROWS,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_WEIGHT_STEP,
    run_tiered_ensemble_experiment,
)


def main(argv: list[str] | None = None, *, args=None) -> int:
    if args is None:
        parser = argparse.ArgumentParser(description="Run tiered low/mid/high ensemble experiments")
        parser.add_argument("--data-file", type=Path, default=DEFAULT_DATA_FILE)
        parser.add_argument("--feature-set", default="no_list_price_h3_market_street")
        parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
        parser.add_argument("--splits", type=int, default=4)
        parser.add_argument("--low-max-price", type=float, default=DEFAULT_LOW_MAX_PRICE)
        parser.add_argument("--mid-min-price", type=float, default=DEFAULT_MID_MIN_PRICE)
        parser.add_argument("--mid-max-price", type=float, default=DEFAULT_MID_MAX_PRICE)
        parser.add_argument("--high-min-price", type=float, default=DEFAULT_HIGH_MIN_PRICE)
        parser.add_argument("--gate-low-max", type=float, default=DEFAULT_GATE_LOW_MAX)
        parser.add_argument("--gate-high-min", type=float, default=DEFAULT_GATE_HIGH_MIN)
        parser.add_argument("--weight-step", type=float, default=DEFAULT_WEIGHT_STEP)
        parser.add_argument("--min-segment-rows", type=int, default=DEFAULT_MIN_SEGMENT_ROWS)
        args = parser.parse_args(argv)

    result = run_tiered_ensemble_experiment(
        data_file=args.data_file,
        feature_set=args.feature_set,
        output_dir=args.output_dir,
        n_splits=args.splits,
        low_max_price=args.low_max_price,
        mid_min_price=args.mid_min_price,
        mid_max_price=args.mid_max_price,
        high_min_price=args.high_min_price,
        gate_low_max=args.gate_low_max,
        gate_high_min=args.gate_high_min,
        weight_step=args.weight_step,
        min_segment_rows=args.min_segment_rows,
    )
    global_metrics = result["global"]
    overall_metrics = result["overall_ensemble"]
    gated_metrics = result["gated_ensemble"]
    gated_selection = result["blend_selection"]["gated_ensemble"]
    gate = result["gate"]
    print(f"Tiered ensemble experiment complete: {args.feature_set}")
    print(
        f"Global MAE: {global_metrics['mae']:,.0f} SEK; "
        f"bias: {global_metrics['mean_bias']:,.0f} SEK"
    )
    print(
        f"Overall ensemble MAE: {overall_metrics['mae']:,.0f} SEK; "
        f"bias: {overall_metrics['mean_bias']:,.0f} SEK"
    )
    print(
        f"Gated ensemble MAE: {gated_metrics['mae']:,.0f} SEK; "
        f"bias: {gated_metrics['mean_bias']:,.0f} SEK; "
        f"OOF MAE: {gated_selection['oof_mae']:,.0f} SEK"
    )
    print(
        f"Predicted high rows: {gate['test_rows_by_gate']['high']:,}; "
        f"12M+ high-gate capture: {gate['test_12m_plus_capture_rate']:.2f}%"
    )
    print(f"Output directory: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
