from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

from estate_value_index.ml.production_models import _oof_final_blend
from estate_value_index.ml.production_residual_calibration import _gate_summary
from estate_value_index.ml.residual_calibration import apply_calibration_correction
from estate_value_index.ml.tiered_ensemble import (
    DEFAULT_TRAIN_TIER_HIGH_MIN_PRICE,
    DEFAULT_TRAIN_TIER_LOW_MAX_PRICE,
    DEFAULT_TRAIN_TIER_MID_MAX_PRICE,
    DEFAULT_TRAIN_TIER_MID_MIN_PRICE,
    _tier_specs,
)


def test_apply_calibration_correction_clips_to_tighter_of_abs_and_fraction() -> None:
    calibrated = apply_calibration_correction(
        np.array([1_000_000.0, 10_000_000.0, 500_000.0]),
        np.array([2_000_000.0, 50_000.0, -900_000.0]),
        max_abs=1_000_000.0,
        max_frac=0.12,
    )

    # row0: 12% of 1M = 120k caps the +2M correction
    # row1: 1M abs cap is tighter than 12% of 10M, but +50k is under both
    # row2: 12% of 500k = 60k caps the -900k correction
    assert calibrated.tolist() == [1_120_000.0, 10_050_000.0, 440_000.0]


def test_apply_calibration_correction_floors_at_zero() -> None:
    calibrated = apply_calibration_correction(
        np.array([100_000.0]),
        np.array([-500_000.0]),
        max_abs=1_000_000.0,
        max_frac=10.0,
    )

    assert calibrated.tolist() == [0.0]


def test_apply_calibration_correction_skips_low_predictions() -> None:
    # Selective: only predictions >= min_base_prediction get corrected.
    calibrated = apply_calibration_correction(
        np.array([5_000_000.0, 9_000_000.0]),
        np.array([300_000.0, 300_000.0]),
        max_abs=1_000_000.0,
        max_frac=0.12,
        min_base_prediction=8_000_000.0,
    )

    # 5M is below the threshold -> unchanged; 9M gets the correction.
    assert calibrated.tolist() == [5_000_000.0, 9_300_000.0]


def test_oof_final_blend_routes_rows_through_their_gate_weights() -> None:
    tier_specs = _tier_specs(
        low_max_price=DEFAULT_TRAIN_TIER_LOW_MAX_PRICE,
        mid_min_price=DEFAULT_TRAIN_TIER_MID_MIN_PRICE,
        mid_max_price=DEFAULT_TRAIN_TIER_MID_MAX_PRICE,
        high_min_price=DEFAULT_TRAIN_TIER_HIGH_MIN_PRICE,
    )
    oof = pd.DataFrame(
        {
            "base_prediction": [4_000_000.0, 12_000_000.0],
            "normalized_prediction": [4_000_000.0, 12_000_000.0],
            "low_prediction": [1_000_000.0, 1_000_000.0],
            "mid_prediction": [2_000_000.0, 2_000_000.0],
            "high_prediction": [9_000_000.0, 9_000_000.0],
        }
    )
    model = SimpleNamespace(
        market_blend_weight=0.0,  # global blend collapses to the base prediction
        gate_low_max=5_000_000.0,
        gate_high_min=10_000_000.0,
        gated_weights_by_gate={
            "low": {"high": 1.0},
            "high": {"low": 1.0},
        },
        fallback_weights={"global": 1.0},
    )

    final = _oof_final_blend(model, oof, tier_specs)

    # 4M is gated "low" -> takes the high expert (9M); 12M is gated "high" -> takes the low expert (1M)
    assert final.tolist() == [9_000_000.0, 1_000_000.0]


def _gate_result(
    *,
    base_bias: float,
    cal_bias: float,
    mae_delta: float,
    base_under: float,
    cal_under: float,
    high_end: dict[str, float] | None = None,
) -> dict[str, object]:
    band = []
    if high_end is not None:
        band = [{"segment": "12M+", **high_end}]
    return {
        "base": {"mean_bias": base_bias, "underprediction_rate": base_under},
        "calibrated": {"mean_bias": cal_bias, "underprediction_rate": cal_under},
        "delta": {"mae": mae_delta},
        "by_price_band": band,
    }


def test_gate_summary_passes_when_all_signals_improve() -> None:
    gate = _gate_summary(
        _gate_result(
            base_bias=-131_000.0,
            cal_bias=-112_000.0,
            mae_delta=-3_200.0,
            base_under=53.0,
            cal_under=52.4,
            high_end={
                "base_mae": 1_741_000.0,
                "calibrated_mae": 1_701_000.0,
                "base_bias": -960_000.0,
                "calibrated_bias": -833_000.0,
            },
        )
    )

    assert gate["passed"] is True
    assert all(gate["checks"].values())


def test_gate_summary_fails_when_mean_bias_worsens() -> None:
    gate = _gate_summary(
        _gate_result(
            base_bias=-131_000.0,
            cal_bias=-154_000.0,  # worse
            mae_delta=-7_000.0,
            base_under=53.0,
            cal_under=58.0,  # away from 50
        )
    )

    assert gate["passed"] is False
    assert gate["checks"]["mean_bias_improves"] is False
    assert gate["checks"]["underprediction_toward_50"] is False


def test_gate_summary_fails_when_mae_worsens_beyond_threshold() -> None:
    gate = _gate_summary(
        _gate_result(
            base_bias=-131_000.0,
            cal_bias=-100_000.0,
            mae_delta=20_000.0,  # worse than 10k
            base_under=53.0,
            cal_under=51.0,
        )
    )

    assert gate["passed"] is False
    assert gate["checks"]["overall_mae"] is False
