from __future__ import annotations

import argparse
from pathlib import Path

from estate_value_index.ml.premium_specialist import (
    DEFAULT_ANCHOR_COLUMNS,
    DEFAULT_DATA_FILE,
    DEFAULT_GATE_COMP_VALUE_MIN,
    DEFAULT_GATE_LUXURY_SCORE_MIN,
    DEFAULT_GATE_MIN_LIVING_AREA,
    DEFAULT_GATE_PREDICTION_MIN,
    DEFAULT_MAX_PREMIUM_RATIO,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SPECIALIST_MIN_PRICE,
    run_premium_specialist_experiment,
)


def main(argv: list[str] | None = None, *, args=None) -> int:
    if args is None:
        parser = argparse.ArgumentParser(description="Run premium-over-comp specialist experiments")
        parser.add_argument("--data-file", type=Path, default=DEFAULT_DATA_FILE)
        parser.add_argument("--feature-set", default="no_list_price_h3_market_tail")
        parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
        parser.add_argument("--splits", type=int, default=4)
        parser.add_argument(
            "--specialist-min-price", type=float, default=DEFAULT_SPECIALIST_MIN_PRICE
        )
        parser.add_argument(
            "--gate-prediction-min", type=float, default=DEFAULT_GATE_PREDICTION_MIN
        )
        parser.add_argument(
            "--gate-comp-value-min", type=float, default=DEFAULT_GATE_COMP_VALUE_MIN
        )
        parser.add_argument(
            "--gate-luxury-score-min", type=float, default=DEFAULT_GATE_LUXURY_SCORE_MIN
        )
        parser.add_argument(
            "--gate-min-living-area", type=float, default=DEFAULT_GATE_MIN_LIVING_AREA
        )
        parser.add_argument("--max-premium-ratio", type=float, default=DEFAULT_MAX_PREMIUM_RATIO)
        parser.add_argument(
            "--anchor-column",
            action="append",
            dest="anchor_columns",
            help="Comp PPSQM anchor column, in fallback order. May be repeated.",
        )
        args = parser.parse_args(argv)

    anchor_columns = tuple(args.anchor_columns or DEFAULT_ANCHOR_COLUMNS)
    result = run_premium_specialist_experiment(
        data_file=args.data_file,
        feature_set=args.feature_set,
        output_dir=args.output_dir,
        n_splits=args.splits,
        specialist_min_price=args.specialist_min_price,
        gate_prediction_min=args.gate_prediction_min,
        gate_comp_value_min=args.gate_comp_value_min,
        gate_luxury_score_min=args.gate_luxury_score_min,
        gate_min_living_area=args.gate_min_living_area,
        anchor_columns=anchor_columns,
        max_premium_ratio=args.max_premium_ratio,
    )
    global_metrics = result["global"]
    specialist_metrics = result["premium_specialist_gated"]
    gate = result["gate"]
    selection = result["blend_selection"]["specialist"]
    print(f"Premium specialist experiment complete: {args.feature_set}")
    print(
        f"Global MAE: {global_metrics['mae']:,.0f} SEK; "
        f"bias: {global_metrics['mean_bias']:,.0f} SEK"
    )
    print(
        f"Premium gated MAE: {specialist_metrics['mae']:,.0f} SEK; "
        f"bias: {specialist_metrics['mean_bias']:,.0f} SEK; "
        f"specialist weight: {selection['specialist_weight']:.2f}"
    )
    print(
        f"Gate rows: {gate['test_gate_rows']:,} "
        f"({gate['test_gate_rate']:.2f}%); 12M+ capture: {gate['test_12m_plus_capture_rate']:.2f}%"
    )
    print(f"Output directory: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
