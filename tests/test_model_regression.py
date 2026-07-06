"""Model regression smoke tests against a naive baseline."""

import json
import os
from pathlib import Path

import pytest

from estate_value_index.model_artifacts import (
    LISTING_MODEL_ID,
    NO_LIST_MODEL_ID,
    production_artifact_names,
)

MODEL_REGRESSION_ENV = "RUN_MODEL_REGRESSION"


def _model_dir() -> Path:
    return Path(__file__).parent.parent / "web" / "models"


def _require_model_regression_artifacts() -> Path:
    if os.getenv(MODEL_REGRESSION_ENV) != "1":
        pytest.skip(f"Set {MODEL_REGRESSION_ENV}=1 to validate external model artifacts")
    return _model_dir()


@pytest.mark.integration
def test_model_performance_regression():
    """Fail if current MdAPE is >10% worse than the naive baseline."""
    # Naive baseline (average price/m² × size) expressed as MdAPE, the
    # AVM-standard headline metric. A trained model should sit well under this.
    BASELINE_MEDIAN_APE = 0.15
    REGRESSION_THRESHOLD = 0.10

    model_dir = _require_model_regression_artifacts()
    metrics_file = model_dir / production_artifact_names(NO_LIST_MODEL_ID).metrics

    if not metrics_file.exists():
        pytest.skip(f"Model metrics file not found: {metrics_file}")

    with open(metrics_file) as f:
        current_metrics = json.load(f)

    current_median_ape = current_metrics.get("median_ape")
    if current_median_ape is None:
        pytest.fail("median_ape not found in model metrics file")

    regression_pct = ((current_median_ape - BASELINE_MEDIAN_APE) / BASELINE_MEDIAN_APE) * 100
    max_allowed_median_ape = BASELINE_MEDIAN_APE * (1 + REGRESSION_THRESHOLD)

    assert current_median_ape <= max_allowed_median_ape, (
        f"Model performance regression detected!\n"
        f"  Current MdAPE: {current_median_ape:.2%}\n"
        f"  Baseline MdAPE: {BASELINE_MEDIAN_APE:.2%}\n"
        f"  Regression: {regression_pct:+.1f}% (threshold: {REGRESSION_THRESHOLD * 100:.0f}%)\n"
        f"  Max allowed MdAPE: {max_allowed_median_ape:.2%}\n"
    )


@pytest.mark.integration
def test_model_metrics_exist():
    model_dir = _require_model_regression_artifacts()
    metrics_file = model_dir / production_artifact_names(NO_LIST_MODEL_ID).metrics

    assert metrics_file.exists(), f"Model metrics file not found: {metrics_file}"

    with open(metrics_file) as f:
        metrics = json.load(f)

    for field in ["median_ape", "within_10_pct", "within_20_pct", "mae", "rmse"]:
        assert field in metrics, f"Required field '{field}' missing from metrics"
        assert isinstance(metrics[field], (int, float)), f"Field '{field}' must be numeric"

    assert 0 <= metrics["median_ape"] <= 1  # fraction
    assert 0 <= metrics["within_10_pct"] <= 100
    assert 0 <= metrics["within_20_pct"] <= 100


@pytest.mark.integration
def test_model_artifacts_exist():
    model_dir = _require_model_regression_artifacts()

    required_files = [
        filename
        for model_id in (NO_LIST_MODEL_ID, LISTING_MODEL_ID)
        for filename in production_artifact_names(model_id).files
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

    assert "median_ape" in baseline, "baseline_metrics.json must contain 'median_ape' field"
    assert isinstance(baseline["median_ape"], (int, float)), "median_ape must be numeric"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
