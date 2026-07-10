from __future__ import annotations

import argparse
from pathlib import Path

from estate_value_index.ml.production_models import DEFAULT_NO_LIST_FEATURE_SET
from estate_value_index.ml.production_residual_calibration import (
    run_production_residual_calibration_experiment,
)
from estate_value_index.ml.residual_calibration import (
    DEFAULT_DATA_FILE,
    DEFAULT_OUTPUT_DIR,
    run_residual_calibration_experiment,
)


def main(argv: list[str] | None = None, *, args=None) -> int:
    if args is None:
        parser = argparse.ArgumentParser(description="Run residual calibration experiments")
        parser.add_argument("--data-file", type=Path, default=DEFAULT_DATA_FILE)
        parser.add_argument(
            "--feature-set",
            default=None,
            help=(
                "Feature set to calibrate. Its meaning depends on --production: "
                "without --production this selects a single LGBM's feature set "
                "(default 'no_list_price_h3_market'); with --production it "
                f"selects the tiered no_list production model's feature set "
                f"(default '{DEFAULT_NO_LIST_FEATURE_SET}') — the same flag "
                "resolves against a different model depending on --production."
            ),
        )
        parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
        parser.add_argument("--splits", type=int, default=4)
        parser.add_argument(
            "--production",
            action="store_true",
            help=(
                "Calibrate the production tiered no_list model instead of a "
                "single LGBM. Also changes what --feature-set resolves against."
            ),
        )
        args = parser.parse_args(argv)

    if getattr(args, "production", False):
        return _run_production(args)

    feature_set = args.feature_set or "no_list_price_h3_market"
    result = run_residual_calibration_experiment(
        data_file=args.data_file,
        feature_set=feature_set,
        output_dir=args.output_dir,
        n_splits=args.splits,
    )
    base = result["base"]
    calibrated = result["calibrated"]
    delta = result["delta"]
    print(f"Residual calibration experiment complete: {feature_set}")
    print(f"Base MAE: {base['mae']:,.0f} SEK; bias: {base['mean_bias']:,.0f} SEK")
    print(f"Calibrated MAE: {calibrated['mae']:,.0f} SEK; bias: {calibrated['mean_bias']:,.0f} SEK")
    print(
        "Delta: "
        f"MAE {delta['mae']:,.0f} SEK, "
        f"bias {delta['mean_bias']:,.0f} SEK, "
        f"within10 {delta['within_10_pct']:.2f} pp"
    )
    print(f"Output directory: {args.output_dir}")
    return 0


def _run_production(args) -> int:
    # The single-model default feature set is meaningless for the production model;
    # fall back to the real no_list production feature set unless the user overrode it.
    feature_set = args.feature_set or DEFAULT_NO_LIST_FEATURE_SET
    result = run_production_residual_calibration_experiment(
        data_file=args.data_file,
        feature_set=feature_set,
        output_dir=args.output_dir,
        n_splits=args.splits,
    )
    base = result["base"]
    calibrated = result["calibrated"]
    delta = result["delta"]
    gate = result["gate"]
    print(f"Production residual calibration complete: {feature_set}")
    print(f"Base MAE: {base['mae']:,.0f} SEK; bias: {base['mean_bias']:,.0f} SEK")
    print(f"Calibrated MAE: {calibrated['mae']:,.0f} SEK; bias: {calibrated['mean_bias']:,.0f} SEK")
    print(
        "Delta: "
        f"MAE {delta['mae']:,.0f} SEK, "
        f"bias {delta['mean_bias']:,.0f} SEK, "
        f"within10 {delta['within_10_pct']:.2f} pp"
    )
    failed = [name for name, ok in gate["checks"].items() if not ok]
    verdict = "PASS" if gate["passed"] else f"FAIL ({', '.join(failed)})"
    print(
        f"Gate: MAE delta {gate['mae_delta']:,.0f} SEK "
        f"(need <= {gate['max_mae_worsening']:,.0f}); "
        f"checks {sum(gate['checks'].values())}/{len(gate['checks'])} -> {verdict}"
    )
    print(f"Output directory: {args.output_dir}")
    return 0 if gate["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
