from __future__ import annotations

import numpy as np
import pandas as pd

from estate_value_index.ml.premium_specialist import (
    comp_anchor_ppsqm,
    premium_over_comp_target,
    premium_predictions_to_price,
)


def test_comp_anchor_ppsqm_uses_first_positive_anchor() -> None:
    frame = pd.DataFrame(
        {
            "same_size_ppsqm_p90": [120_000.0, np.nan, -1.0],
            "micro_area_ppsqm_p90": [110_000.0, 100_000.0, 95_000.0],
            "same_size_ppsqm_median": [90_000.0, 90_000.0, 90_000.0],
        }
    )

    anchor = comp_anchor_ppsqm(
        frame,
        ("same_size_ppsqm_p90", "micro_area_ppsqm_p90", "same_size_ppsqm_median"),
    )

    assert anchor.tolist() == [120_000.0, 100_000.0, 95_000.0]


def test_premium_over_comp_target_uses_sold_price_over_anchor_value() -> None:
    frame = pd.DataFrame(
        {
            "sold_price": [12_000_000.0, 9_000_000.0],
            "living_area": [80.0, 50.0],
        }
    )
    anchor = pd.Series([120_000.0, 100_000.0])

    target = premium_over_comp_target(frame, anchor)

    assert target.tolist() == [1.25, 1.8]


def test_premium_predictions_to_price_falls_back_without_valid_anchor() -> None:
    frame = pd.DataFrame(
        {
            "same_size_ppsqm_p90": [120_000.0, np.nan],
            "living_area": [80.0, 50.0],
        }
    )

    predictions = premium_predictions_to_price(
        np.array([1.25, 1.50]),
        frame,
        np.array([8_000_000.0, 7_000_000.0]),
        anchor_columns=("same_size_ppsqm_p90",),
    )

    assert predictions.tolist() == [12_000_000.0, 7_000_000.0]
