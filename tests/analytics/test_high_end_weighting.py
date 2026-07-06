from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from estate_value_index.analytics.high_end_weighting import make_high_end_sample_weights


def test_make_high_end_sample_weights_ramps_above_start_quantile() -> None:
    weights = make_high_end_sample_weights(
        pd.Series([1_000_000, 2_000_000, 3_000_000, 4_000_000]),
        start_quantile=0.5,
        max_weight=2.0,
        curve_power=1.0,
    )

    assert weights.iloc[0] == 1.0
    assert weights.iloc[1] == 1.0
    assert weights.iloc[2] == 1.5
    assert weights.iloc[3] == 2.0


def test_make_high_end_sample_weights_preserves_missing_rows_at_weight_one() -> None:
    weights = make_high_end_sample_weights(
        pd.Series([1_000_000, np.nan, 3_000_000]),
        start_quantile=0.5,
        max_weight=2.0,
        curve_power=1.0,
    )

    assert weights.iloc[1] == 1.0
    assert weights.min() >= 1.0
    assert weights.max() <= 2.0


def test_make_high_end_sample_weights_rejects_bad_parameters() -> None:
    with pytest.raises(ValueError, match="start_quantile"):
        make_high_end_sample_weights(pd.Series([1.0]), start_quantile=1.0)
    with pytest.raises(ValueError, match="max_weight"):
        make_high_end_sample_weights(pd.Series([1.0]), max_weight=0.5)
    with pytest.raises(ValueError, match="curve_power"):
        make_high_end_sample_weights(pd.Series([1.0]), curve_power=0.0)
