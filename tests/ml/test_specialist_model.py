from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from estate_value_index.ml.specialist_model import (
    apply_gated_specialist_predictions,
    build_specialist_gate,
    select_best_specialist_weight,
)


def test_build_specialist_gate_uses_prediction_comp_value_or_luxury_score() -> None:
    frame = pd.DataFrame(
        {
            "living_area": [40.0, 100.0, 70.0, 40.0],
            "same_size_ppsqm_median": [100_000.0, 95_000.0, 70_000.0, 70_000.0],
            "micro_area_ppsqm_median": [90_000.0, 90_000.0, 90_000.0, 90_000.0],
            "micro_luxury_score": [0.2, 0.4, 0.8, 0.8],
        }
    )

    gate = build_specialist_gate(
        frame,
        np.array([8_500_000.0, 6_000_000.0, 6_000_000.0, 6_000_000.0]),
        prediction_min=8_000_000.0,
        comp_value_min=9_000_000.0,
        luxury_score_min=0.6,
        min_living_area=55.0,
    )

    assert gate.tolist() == [True, True, True, False]


def test_apply_gated_specialist_predictions_only_changes_gated_rows() -> None:
    predictions = apply_gated_specialist_predictions(
        np.array([100.0, 200.0, 300.0]),
        np.array([120.0, 260.0, 500.0]),
        np.array([True, False, True]),
        specialist_weight=0.5,
    )

    assert predictions.tolist() == [110.0, 200.0, 400.0]


def test_apply_gated_specialist_predictions_rejects_bad_weight() -> None:
    with pytest.raises(ValueError, match="specialist_weight"):
        apply_gated_specialist_predictions(
            np.array([100.0]),
            np.array([120.0]),
            np.array([True]),
            specialist_weight=1.5,
        )


def test_select_best_specialist_weight_uses_gated_mae() -> None:
    result = select_best_specialist_weight(
        np.array([100.0, 200.0, 300.0]),
        np.array([80.0, 200.0, 280.0]),
        np.array([100.0, 250.0, 300.0]),
        np.array([True, False, True]),
        weights=(0.0, 0.5, 1.0),
    )

    assert result["specialist_weight"] == 1.0
    assert result["oof_mae"] == 0.0
