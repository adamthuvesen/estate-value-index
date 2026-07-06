"""Model regression smoke tests against a naive baseline."""

import json
import os
from pathlib import Path

import pytest

MODEL_REGRESSION_ENV = "RUN_MODEL_REGRESSION"


def _model_dir() -> Path:
    return Path(__file__).parent.parent / "web" / "models"


def _require_model_regression_artifacts() -> Path:
    if os.getenv(MODEL_REGRESSION_ENV) != "1":
        pytest.skip(f"Set {MODEL_REGRESSION_ENV}=1 to validate external model artifacts")
    return _model_dir()


@pytest.mark.integration
def test_model_performance_regression():
    """Fail if current MAE is >10% worse than the naive baseline."""
    BASELINE_MAE = 725000  # Naive baseline (average price/m² × size)
    REGRESSION_THRESHOLD = 0.10

    model_dir = _require_model_regression_artifacts()
    metrics_file = model_dir / "price_prediction_model_no_list_metrics.json"

    if not metrics_file.exists():
        pytest.skip(f"Model metrics file not found: {metrics_file}")

    with open(metrics_file) as f:
        current_metrics = json.load(f)

    current_mae = current_metrics.get("mae")
    if current_mae is None:
        pytest.fail("MAE not found in model metrics file")

    regression_pct = ((current_mae - BASELINE_MAE) / BASELINE_MAE) * 100
    max_allowed_mae = BASELINE_MAE * (1 + REGRESSION_THRESHOLD)

    assert current_mae <= max_allowed_mae, (
        f"Model performance regression detected!\n"
        f"  Current MAE: {current_mae:,.0f} SEK\n"
        f"  Baseline MAE: {BASELINE_MAE:,.0f} SEK\n"
        f"  Regression: {regression_pct:+.1f}% (threshold: {REGRESSION_THRESHOLD * 100:.0f}%)\n"
        f"  Max allowed MAE: {max_allowed_mae:,.0f} SEK\n"
    )


@pytest.mark.integration
def test_model_metrics_exist():
    model_dir = _require_model_regression_artifacts()
    metrics_file = model_dir / "price_prediction_model_no_list_metrics.json"

    assert metrics_file.exists(), f"Model metrics file not found: {metrics_file}"

    with open(metrics_file) as f:
        metrics = json.load(f)

    for field in ["mae", "rmse", "mape"]:
        assert field in metrics, f"Required field '{field}' missing from metrics"
        assert isinstance(metrics[field], (int, float)), f"Field '{field}' must be numeric"

    assert metrics["mae"] > 0
    assert metrics["rmse"] > 0
    assert 0 <= metrics["mape"] <= 100


@pytest.mark.integration
def test_model_artifacts_exist():
    model_dir = _require_model_regression_artifacts()

    required_files = [
        "price_prediction_model_no_list.joblib",
        "price_prediction_model_no_list_metrics.json",
        "price_prediction_model_no_list_feature_context.json",
        "price_prediction_model_listing.joblib",
        "price_prediction_model_listing_metrics.json",
        "price_prediction_model_listing_feature_context.json",
    ]

    missing_files = [f for f in required_files if not (model_dir / f).exists()]

    assert not missing_files, (
        "Missing required model artifacts:\n  "
        + "\n  ".join(missing_files)
        + "\n\nRun training to generate artifacts: uv run python -m estate_value_index.cli train-production-models --data-source bigquery"
    )


@pytest.mark.integration
def test_baseline_metrics_file():
    """Validate optional baseline_metrics.json when external model artifacts are present."""
    model_dir = _require_model_regression_artifacts()
    baseline_file = model_dir / "baseline_metrics.json"

    if not baseline_file.exists():
        pytest.skip(f"Baseline metrics file not found: {baseline_file}")

    with open(baseline_file) as f:
        baseline = json.load(f)

    assert "mae" in baseline, "baseline_metrics.json must contain 'mae' field"
    assert isinstance(baseline["mae"], (int, float)), "MAE must be numeric"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
