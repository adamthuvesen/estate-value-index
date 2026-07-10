from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from estate_value_index.ml.market_normalized_target import (
    blend_market_predictions,
    denormalize_market_predictions,
    market_index_reference,
    normalize_prices_to_market_index,
    select_best_market_blend_weight,
)


def test_normalize_prices_to_market_index_uses_reference_level() -> None:
    normalized = normalize_prices_to_market_index(
        pd.Series([5_000_000.0, 6_600_000.0]),
        pd.Series([100_000.0, 110_000.0]),
        reference_index=100_000.0,
    )

    assert normalized.tolist() == [5_000_000.0, 6_000_000.0]


def test_denormalize_market_predictions_uses_fallback_for_missing_index() -> None:
    prices = denormalize_market_predictions(
        np.array([5_000_000.0, 6_000_000.0, 7_000_000.0]),
        pd.Series([100_000.0, np.nan, 0.0]),
        reference_index=100_000.0,
        fallback_predictions=np.array([4_900_000.0, 5_500_000.0, 6_000_000.0]),
    )

    assert prices.tolist() == [5_000_000.0, 5_500_000.0, 6_000_000.0]


def test_market_index_reference_uses_median_valid_value() -> None:
    reference = market_index_reference(pd.Series([np.nan, -1.0, 100_000.0, 120_000.0, 140_000.0]))

    assert reference == 120_000.0


def test_market_index_reference_rejects_empty_valid_values() -> None:
    with pytest.raises(ValueError, match="positive market index"):
        market_index_reference(pd.Series([np.nan, 0.0, -1.0]))


def test_select_best_market_blend_weight_uses_lowest_mae() -> None:
    y_true = np.array([100.0, 200.0, 300.0])
    base = np.array([80.0, 180.0, 280.0])
    normalized = np.array([100.0, 200.0, 300.0])

    result = select_best_market_blend_weight(
        y_true,
        base,
        normalized,
        weights=(0.0, 0.5, 1.0),
    )

    assert result["normalized_weight"] == 1.0
    assert result["oof_mae"] == 0.0


def test_blend_market_predictions_rejects_bad_weight() -> None:
    with pytest.raises(ValueError, match="normalized_weight"):
        blend_market_predictions(np.array([1.0]), np.array([2.0]), normalized_weight=1.5)
