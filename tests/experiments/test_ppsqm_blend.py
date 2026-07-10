from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from estate_value_index.experiments.ppsqm_blend import (
    blend_predictions,
    ppsqm_predictions_to_price,
    select_best_blend_weight,
)


def test_ppsqm_predictions_to_price_uses_fallback_for_missing_area() -> None:
    prices = ppsqm_predictions_to_price(
        np.array([100_000, 120_000, 130_000]),
        pd.Series([50.0, np.nan, 0.0]),
        np.array([4_900_000, 5_500_000, 6_000_000]),
    )

    assert prices.tolist() == [5_000_000, 5_500_000, 6_000_000]


def test_select_best_blend_weight_uses_lowest_mae() -> None:
    y_true = np.array([100.0, 200.0, 300.0])
    base = np.array([80.0, 180.0, 280.0])
    ppsqm = np.array([100.0, 200.0, 300.0])

    result = select_best_blend_weight(
        y_true,
        base,
        ppsqm,
        weights=(0.0, 0.5, 1.0),
    )

    assert result["ppsqm_weight"] == 1.0
    assert result["oof_mae"] == 0.0


def test_blend_predictions_rejects_bad_weight() -> None:
    with pytest.raises(ValueError, match="ppsqm_weight"):
        blend_predictions(np.array([1.0]), np.array([2.0]), ppsqm_weight=1.5)
