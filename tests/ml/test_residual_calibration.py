from __future__ import annotations

import numpy as np
import pandas as pd

from estate_value_index.ml.residual_calibration import (
    apply_residual_calibration,
    build_calibration_features,
)


def test_build_calibration_features_marks_central_area_and_ppsqm() -> None:
    frame = pd.DataFrame(
        {
            "area": ["ostermalm", "rasunda"],
            "h3_res9": ["891", "892"],
            "micro_area_resolution_used": ["h3_res10", "area"],
            "living_area": [50.0, 100.0],
            "rooms": [2.0, 4.0],
            "floor": [3.0, 1.0],
            "market_ppsqm_index_change_3m": [0.04, -0.01],
        }
    )

    features = build_calibration_features(frame, np.array([5_000_000, 7_500_000]))

    assert features.loc[0, "base_prediction"] == 5_000_000
    assert features.loc[0, "base_prediction_ppsqm"] == 100_000
    assert features.loc[1, "base_prediction_ppsqm"] == 75_000
    assert features.loc[0, "is_central_area"] == 1.0
    assert features.loc[1, "is_central_area"] == 0.0
    assert features.loc[0, "market_ppsqm_index_change_3m"] == 0.04
    assert features.loc[1, "area"] == "rasunda"


def test_apply_residual_calibration_clips_negative_predictions() -> None:
    calibrated = apply_residual_calibration(
        np.array([1_000_000, 500_000]),
        np.array([250_000, -900_000]),
    )

    assert calibrated.tolist() == [1_250_000, 0]
