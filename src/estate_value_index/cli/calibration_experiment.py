from __future__ import annotations

import argparse
from pathlib import Path

from estate_value_index.analytics.residual_calibration import (
    DEFAULT_DATA_FILE,
    DEFAULT_OUTPUT_DIR,
    run_residual_calibration_experiment,
)


def main(argv: list[str] | None = None, *, args=None) -> int:
    if args is None:
        parser = argparse.ArgumentParser(description="Run residual calibration experiments")
        parser.add_argument("--data-file", type=Path, default=DEFAULT_DATA_FILE)
        parser.add_argument("--feature-set", default="no_list_price_h3_market")
        parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
        parser.add_argument("--splits", type=int, default=4)
        args = parser.parse_args(argv)

    result = run_residual_calibration_experiment(
        data_file=args.data_file,
        feature_set=args.feature_set,
        output_dir=args.output_dir,
        n_splits=args.splits,
    )
    base = result["base"]
    calibrated = result["calibrated"]
    delta = result["delta"]
    print(f"Residual calibration experiment complete: {args.feature_set}")
    print(f"Base MAE: {base['mae']:,.0f} SEK; bias: {base['mean_bias']:,.0f} SEK")
    print(
        "Calibrated MAE: "
        f"{calibrated['mae']:,.0f} SEK; bias: {calibrated['mean_bias']:,.0f} SEK"
    )
    print(
        "Delta: "
        f"MAE {delta['mae']:,.0f} SEK, "
        f"bias {delta['mean_bias']:,.0f} SEK, "
        f"within10 {delta['within_10_pct']:.2f} pp"
    )
    print(f"Output directory: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
