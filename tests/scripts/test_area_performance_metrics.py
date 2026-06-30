"""Tests for the area-performance metrics inverse-log guard."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

# Load the script as a module without importing the project's `scripts/` dir
# (which is not a package and would shadow other scripts at import time).
_SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "estate_value_index"
    / "cli"
    / "area_performance_metrics.py"
)


@pytest.fixture(scope="module")
def area_metrics_module():
    spec = importlib.util.spec_from_file_location(
        "area_performance_metrics_under_test", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_log_space_predictions_get_expm1(area_metrics_module):
    # Median ~ 15 → in log space → expm1 should be applied.
    y_log = np.array([14.5, 15.0, 15.5])
    out = area_metrics_module._maybe_inverse_log(y_log)
    np.testing.assert_allclose(out, np.expm1(y_log))


def test_linear_space_predictions_pass_through(area_metrics_module, capsys):
    # Median ~ 5,000,000 → already in SEK → pass through unchanged.
    y_linear = np.array([4_000_000.0, 5_000_000.0, 6_000_000.0])
    out = area_metrics_module._maybe_inverse_log(y_linear)
    np.testing.assert_array_equal(out, y_linear)

    captured = capsys.readouterr()
    assert "predictions already in linear space" in captured.err


def _pipeline(predictions: np.ndarray):
    model = SimpleNamespace(predict=lambda X: predictions)
    context = SimpleNamespace(
        numeric_fill_values={"living_area": 55.0},
        categorical_fill_values={"area": "unknown_area"},
    )
    return SimpleNamespace(
        model=model,
        numeric_features=["living_area"],
        categorical_features=["area"],
        context=context,
    )


def test_prepare_feature_matrix_fills_model_context_values(area_metrics_module):
    df = pd.DataFrame(
        {
            "living_area": [None, 70.0],
            "area": [None, "vasastan"],
            "sold_price": [4_000_000, 5_000_000],
        }
    )

    feature_matrix = area_metrics_module._prepare_feature_matrix(
        df,
        _pipeline(np.array([15.0, 15.2])),
    )

    assert feature_matrix["living_area"].tolist() == [55.0, 70.0]
    assert feature_matrix["area"].astype(str).tolist() == ["unknown_area", "vasastan"]
    assert str(feature_matrix["area"].dtype) == "category"


def test_add_prediction_columns_adds_errors_and_metrics(area_metrics_module):
    df = pd.DataFrame(
        {
            "living_area": [55.0, 70.0],
            "area": ["vasastan", "vasastan"],
            "sold_price": [4_000_000.0, 5_000_000.0],
        }
    )
    predictions = np.array([4_100_000.0, 4_800_000.0])

    scored, metrics = area_metrics_module._add_prediction_columns(df, _pipeline(predictions))

    np.testing.assert_array_equal(scored["prediction"].to_numpy(), predictions)
    np.testing.assert_array_equal(scored["error"].to_numpy(), np.array([100_000.0, -200_000.0]))
    assert scored["abs_error"].tolist() == [100_000.0, 200_000.0]
    assert metrics["mae"] == pytest.approx(150_000.0)
    assert metrics["mape"] == pytest.approx(3.25)
    assert "r2" in metrics


def test_area_tier_and_bias_metrics(area_metrics_module):
    rows = []
    for _ in range(10):
        rows.append(
            {
                "area": "premium_area",
                "area_price_tier": "premium",
                "sold_price": 5_000_000.0,
                "prediction": 5_200_000.0,
                "error": 200_000.0,
                "abs_error": 200_000.0,
                "pct_error": 4.0,
            }
        )
        rows.append(
            {
                "area": "value_area",
                "area_price_tier": "affordable",
                "sold_price": 3_000_000.0,
                "prediction": 2_850_000.0,
                "error": -150_000.0,
                "abs_error": 150_000.0,
                "pct_error": -5.0,
            }
        )
    df = pd.DataFrame(rows)

    area_metrics = area_metrics_module._area_metrics(df)
    tier_metrics = area_metrics_module._tier_metrics(df)
    bias_metrics, over_predicted, under_predicted = area_metrics_module._bias_metrics(df)

    assert area_metrics.loc["premium_area", "count"] == 10
    assert tier_metrics.loc["premium", "mae"] == 200_000
    assert bias_metrics.loc["value_area", "mean_error"] == -150_000
    assert over_predicted.index.tolist() == ["premium_area"]
    assert under_predicted.index.tolist() == ["value_area"]
