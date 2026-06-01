"""Shared fixtures for unit tests.

These fixtures provide isolated, deterministic test data without external dependencies.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

# --- DataFrame Fixtures for Validation Tests ---


@pytest.fixture
def sample_valid_df() -> pd.DataFrame:
    """DataFrame passing all validation checks."""
    return pd.DataFrame(
        {
            "listing_id": ["1", "2", "3", "4", "5"],
            "sold_price": [3_000_000, 4_000_000, 5_000_000, 3_500_000, 4_500_000],
            "living_area": [50, 75, 100, 60, 80],
            "rooms": [2, 3, 4, 2, 3],
            "area": ["Södermalm", "Östermalm", "Vasastan", "Kungsholmen", "Norrmalm"],
            "sold_date": [
                "2024-01-01",
                "2024-02-01",
                "2024-03-01",
                "2024-04-01",
                "2024-05-01",
            ],
        }
    )


@pytest.fixture
def sample_df_with_duplicates() -> pd.DataFrame:
    """DataFrame with duplicate listing_ids."""
    return pd.DataFrame(
        {
            "listing_id": ["1", "1", "2", "3", "3"],  # Duplicates: '1' and '3'
            "sold_price": [3_000_000, 3_500_000, 4_000_000, 5_000_000, 5_500_000],
            "living_area": [50, 55, 75, 100, 105],
            "rooms": [2, 2, 3, 4, 4],
            "area": ["Södermalm", "Södermalm", "Östermalm", "Vasastan", "Vasastan"],
            "sold_date": [
                "2024-01-01",
                "2024-01-02",
                "2024-02-01",
                "2024-03-01",
                "2024-03-02",
            ],
        }
    )


@pytest.fixture
def sample_df_with_outliers() -> pd.DataFrame:
    """DataFrame with price outliers outside 1M-10M range."""
    return pd.DataFrame(
        {
            "listing_id": ["1", "2", "3", "4", "5"],
            "sold_price": [
                500_000,  # Below min
                50_000_000,  # Above max
                3_000_000,  # Valid
                4_000_000,  # Valid
                5_000_000,  # Valid
            ],
            "living_area": [30, 200, 75, 80, 90],
            "rooms": [1, 6, 3, 3, 4],
            "area": ["Tensta", "Djursholm", "Södermalm", "Östermalm", "Vasastan"],
            "sold_date": [
                "2024-01-01",
                "2024-02-01",
                "2024-03-01",
                "2024-04-01",
                "2024-05-01",
            ],
        }
    )


@pytest.fixture
def sample_df_missing_fields() -> pd.DataFrame:
    """DataFrame missing required fields."""
    return pd.DataFrame(
        {
            "listing_id": ["1", "2", "3"],
            "sold_price": [3_000_000, 4_000_000, 5_000_000],
            # Missing: living_area, rooms, area, sold_date
        }
    )


@pytest.fixture
def sample_df_null_fields() -> pd.DataFrame:
    """DataFrame with entirely null required fields."""
    return pd.DataFrame(
        {
            "listing_id": ["1", "2", "3"],
            "sold_price": [3_000_000, 4_000_000, 5_000_000],
            "living_area": [50, 75, 100],
            "rooms": [None, None, None],  # Entirely null
            "area": ["Södermalm", "Östermalm", "Vasastan"],
            "sold_date": ["2024-01-01", "2024-02-01", "2024-03-01"],
        }
    )


@pytest.fixture
def sample_small_df() -> pd.DataFrame:
    """DataFrame with too few listings (< 100)."""
    return pd.DataFrame(
        {
            "listing_id": [str(i) for i in range(50)],
            "sold_price": [3_000_000 + i * 10_000 for i in range(50)],
            "living_area": [50 + i for i in range(50)],
            "rooms": [(i % 4) + 1 for i in range(50)],
            "area": ["Södermalm"] * 50,
            "sold_date": ["2024-01-01"] * 50,
        }
    )


# --- Training Fixtures ---


@pytest.fixture
def sample_training_features() -> pd.DataFrame:
    """Training features for LGBMTrainer tests."""
    np.random.seed(42)
    n_samples = 100
    return pd.DataFrame(
        {
            "living_area": np.random.uniform(30, 150, n_samples),
            "rooms": np.random.randint(1, 6, n_samples),
            "floor": np.random.randint(0, 10, n_samples),
            "monthly_fee": np.random.uniform(2000, 8000, n_samples),
            "construction_year": np.random.randint(1900, 2024, n_samples),
        }
    )


@pytest.fixture
def sample_training_target() -> np.ndarray:
    """Log-transformed target for training."""
    np.random.seed(42)
    prices = np.random.uniform(2_000_000, 8_000_000, 100)
    return np.log(prices)


@pytest.fixture
def sample_training_target_series(sample_training_target: np.ndarray) -> pd.Series:
    """Log-transformed target as pandas Series."""
    return pd.Series(sample_training_target, name="sold_price_log")


# --- Mock Fixtures ---


@pytest.fixture
def mock_lgbm_model() -> MagicMock:
    """Mock LGBMRegressor for testing without actual training."""
    from lightgbm import LGBMRegressor

    model = MagicMock(spec=LGBMRegressor)
    model.predict.return_value = np.array([14.5, 15.0, 15.5])  # Log-scale predictions
    model.feature_importances_ = np.array([0.3, 0.2, 0.2, 0.15, 0.15])
    return model


@pytest.fixture
def mock_subprocess_success(mocker: Any) -> MagicMock:
    """Mock subprocess.run that returns success."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Success"
    mock_result.stderr = ""
    return mocker.patch("subprocess.run", return_value=mock_result)


@pytest.fixture
def mock_subprocess_failure(mocker: Any) -> MagicMock:
    """Mock subprocess.run that returns failure."""
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = "Error: command failed"
    return mocker.patch("subprocess.run", return_value=mock_result)


# --- File System Fixtures ---


@pytest.fixture
def temp_metrics_file(tmp_path: Path) -> Path:
    """Temporary metrics JSON file."""
    import json

    metrics = {
        "mae": 250_000,
        "rmse": 350_000,
        "r2": 0.85,
        "mape": 0.12,
    }
    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text(json.dumps(metrics))
    return metrics_path


@pytest.fixture
def temp_metrics_file_high_mae(tmp_path: Path) -> Path:
    """Temporary metrics JSON file with MAE above threshold."""
    import json

    metrics = {
        "mae": 300_000,  # Above typical 255K threshold
        "rmse": 400_000,
        "r2": 0.75,
    }
    metrics_path = tmp_path / "metrics_high_mae.json"
    metrics_path.write_text(json.dumps(metrics))
    return metrics_path


@pytest.fixture
def temp_model_dir(tmp_path: Path) -> Path:
    """Temporary directory for model artifacts."""
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    return model_dir


# --- Vertex AI Output Fixtures ---


@pytest.fixture
def vertex_job_stdout() -> str:
    """Sample Vertex AI job submission stdout."""
    return """
Creating CustomJob
CustomJob created. Resource name: projects/my-project/locations/europe-north1/customJobs/12345678
To stream logs, run:
  gcloud ai custom-jobs stream-logs projects/my-project/locations/europe-north1/customJobs/12345678 --region=europe-north1
Run ID: 20241201-123456
Model saved to: gs://my-bucket/vertex-ai/models/20241201-123456
    """


@pytest.fixture
def vertex_job_stdout_minimal() -> str:
    """Minimal Vertex AI output with just job ID."""
    return "Created: projects/test-project/locations/us-central1/customJobs/999"


@pytest.fixture
def vertex_job_stdout_empty() -> str:
    """Empty Vertex AI output."""
    return ""


# --- Request/Response Fixtures ---


@pytest.fixture
def mock_requests_success(mocker: Any) -> MagicMock:
    """Mock requests.get that returns success."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "healthy"}
    # Patch at the module level where it's imported
    return mocker.patch(
        "estate_value_index.pipelines.tasks.deployment.requests.get",
        return_value=mock_response,
    )


@pytest.fixture
def mock_requests_timeout(mocker: Any) -> MagicMock:
    """Mock requests.get that raises timeout."""
    import requests

    return mocker.patch(
        "estate_value_index.pipelines.tasks.deployment.requests.get",
        side_effect=requests.exceptions.Timeout(),
    )


@pytest.fixture
def mock_requests_error(mocker: Any) -> MagicMock:
    """Mock requests.get that raises connection error."""
    import requests

    return mocker.patch(
        "estate_value_index.pipelines.tasks.deployment.requests.get",
        side_effect=requests.exceptions.ConnectionError(),
    )
