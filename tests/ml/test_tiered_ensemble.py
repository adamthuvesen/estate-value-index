from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from estate_value_index.ml.tiered_ensemble import (
    apply_expert_blend,
    apply_gated_expert_blend,
    prediction_tier_labels,
    select_best_expert_weights,
    select_gated_expert_weights,
)


def test_prediction_tier_labels_uses_predicted_price_only() -> None:
    labels = prediction_tier_labels(
        np.array([4_000_000.0, 7_000_000.0, 11_000_000.0, np.nan]),
        low_max=5_000_000.0,
        high_min=10_000_000.0,
    )

    assert labels.tolist() == ["low", "mid", "high", "mid"]


def test_select_best_expert_weights_picks_lowest_mae_convex_blend() -> None:
    predictions = pd.DataFrame(
        {
            "global": [100.0, 200.0, 300.0],
            "low": [100.0, 210.0, 330.0],
            "mid": [90.0, 205.0, 310.0],
            "high": [50.0, 150.0, 300.0],
        }
    )

    result = select_best_expert_weights(
        np.array([100.0, 200.0, 300.0]),
        predictions,
        weight_step=0.5,
    )

    assert result["weights"] == {"global": 1.0, "low": 0.0, "mid": 0.0, "high": 0.0}
    assert result["oof_mae"] == 0.0


def test_apply_gated_expert_blend_uses_segment_weights() -> None:
    predictions = pd.DataFrame(
        {
            "global": [100.0, 200.0, 300.0],
            "low": [90.0, 180.0, 270.0],
            "mid": [110.0, 210.0, 310.0],
            "high": [130.0, 230.0, 330.0],
        }
    )

    blended = apply_gated_expert_blend(
        predictions,
        np.array(["low", "mid", "high"]),
        {
            "low": {"global": 0.0, "low": 1.0, "mid": 0.0, "high": 0.0},
            "mid": {"global": 0.0, "low": 0.0, "mid": 1.0, "high": 0.0},
            "high": {"global": 0.0, "low": 0.0, "mid": 0.0, "high": 1.0},
        },
        fallback_weights={"global": 1.0, "low": 0.0, "mid": 0.0, "high": 0.0},
    )

    assert blended.tolist() == [90.0, 210.0, 330.0]


def test_select_gated_expert_weights_can_use_different_experts_by_gate() -> None:
    predictions = pd.DataFrame(
        {
            "global": [100.0, 100.0, 200.0, 200.0, 300.0, 300.0],
            "low": [95.0, 105.0, 220.0, 220.0, 330.0, 330.0],
            "mid": [130.0, 130.0, 195.0, 205.0, 340.0, 340.0],
            "high": [140.0, 140.0, 240.0, 240.0, 295.0, 305.0],
        }
    )

    result = select_gated_expert_weights(
        np.array([95.0, 105.0, 195.0, 205.0, 295.0, 305.0]),
        predictions,
        np.array(["low", "low", "mid", "mid", "high", "high"]),
        fallback_weights={"global": 1.0, "low": 0.0, "mid": 0.0, "high": 0.0},
        weight_step=1.0,
        min_segment_rows=2,
    )

    assert result["weights_by_gate"]["low"] == {
        "global": 0.0,
        "low": 1.0,
        "mid": 0.0,
        "high": 0.0,
    }
    assert result["weights_by_gate"]["mid"] == {
        "global": 0.0,
        "low": 0.0,
        "mid": 1.0,
        "high": 0.0,
    }
    assert result["weights_by_gate"]["high"] == {
        "global": 0.0,
        "low": 0.0,
        "mid": 0.0,
        "high": 1.0,
    }
    assert result["oof_mae"] == 0.0


def test_apply_expert_blend_rejects_non_convex_weights() -> None:
    with pytest.raises(ValueError, match="sum to 1"):
        apply_expert_blend(
            pd.DataFrame({"global": [1.0], "low": [1.0]}),
            {"global": 0.4, "low": 0.4},
        )
