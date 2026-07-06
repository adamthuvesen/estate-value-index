from __future__ import annotations

import argparse
from pathlib import Path

from estate_value_index.analytics.specialist_model import (
    DEFAULT_DATA_FILE,
    DEFAULT_GATE_COMP_VALUE_MIN,
    DEFAULT_GATE_LUXURY_SCORE_MIN,
    DEFAULT_GATE_MIN_LIVING_AREA,
    DEFAULT_GATE_PREDICTION_MIN,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SPECIALIST_MIN_PRICE,
    run_specialist_experiment,
)


def main(argv: list[str] | None = None, *, args=None) -> int:
    if args is None:
        parser = argparse.ArgumentParser(description="Run gated high-end specialist experiments")
        parser.add_argument("--data-file", type=Path, default=DEFAULT_DATA_FILE)
        parser.add_argument("--feature-set", default="no_list_price_h3_market_luxury")
        parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
        parser.add_argument("--splits", type=int, default=4)
        parser.add_argument("--specialist-min-price", type=float, default=DEFAULT_SPECIALIST_MIN_PRICE)
        parser.add_argument("--gate-prediction-min", type=float, default=DEFAULT_GATE_PREDICTION_MIN)
        parser.add_argument("--gate-comp-value-min", type=float, default=DEFAULT_GATE_COMP_VALUE_MIN)
        parser.add_argument("--gate-luxury-score-min", type=float, default=DEFAULT_GATE_LUXURY_SCORE_MIN)
        parser.add_argument("--gate-min-living-area", type=float, default=DEFAULT_GATE_MIN_LIVING_AREA)
        args = parser.parse_args(argv)

    result = run_specialist_experiment(
        data_file=args.data_file,
        feature_set=args.feature_set,
        output_dir=args.output_dir,
        n_splits=args.splits,
        specialist_min_price=args.specialist_min_price,
        gate_prediction_min=args.gate_prediction_min,
        gate_comp_value_min=args.gate_comp_value_min,
        gate_luxury_score_min=args.gate_luxury_score_min,
        gate_min_living_area=args.gate_min_living_area,
    )
    global_metrics = result["global"]
    specialist_metrics = result["specialist_gated"]
    gate = result["gate"]
    selection = result["blend_selection"]["specialist"]
    print(f"Specialist experiment complete: {args.feature_set}")
    print(
        f"Global MAE: {global_metrics['mae']:,.0f} SEK; "
        f"bias: {global_metrics['mean_bias']:,.0f} SEK"
    )
    print(
        f"Specialist gated MAE: {specialist_metrics['mae']:,.0f} SEK; "
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
