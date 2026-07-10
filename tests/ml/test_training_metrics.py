from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from estate_value_index.ml.training_workflow.metrics import regression_metrics


def test_regression_metrics_include_core_accuracy_metrics() -> None:
    y_true = pd.Series([1_000_000, 2_000_000, 3_000_000], dtype=float)
    y_pred = np.array([1_050_000, 1_700_000, 3_270_000], dtype=float)

    metrics = regression_metrics(y_true, y_pred)

    assert metrics["mae"] == pytest.approx(206_666.6667)
    assert metrics["mape"] == pytest.approx((0.05 + 0.15 + 0.09) / 3)
    # Median of abs % errors [0.05, 0.09, 0.15] — robust to the 0.15 tail.
    assert metrics["median_ape"] == pytest.approx(0.09)
    assert metrics["within_10_pct"] == pytest.approx(200 / 3)


def test_regression_metrics_ignores_zero_sold_price_rows() -> None:
    # Zero-price rows divide to inf; median_ape must skip them rather than
    # collapsing to inf and failing the acceptance gate outright.
    y_true = pd.Series([0.0, 0.0, 0.0, 1_000_000.0])
    y_pred = np.array([500_000.0, 0.0, 0.0, 1_100_000.0])

    metrics = regression_metrics(y_true, y_pred)

    assert metrics["median_ape"] == pytest.approx(0.1)
    assert np.isfinite(metrics["median_ape"])
