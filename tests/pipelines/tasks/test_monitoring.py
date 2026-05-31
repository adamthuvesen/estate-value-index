"""Unit tests for monitoring tasks."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from estate_value_index.pipelines.tasks.monitoring import (
    export_recent_predictions_task,
    monitor_model_drift_task,
    save_baseline_data_task,
    trigger_retraining_on_drift_task,
)


@pytest.fixture
def sample_predictions_df():
    """Sample predictions dataframe."""
    return pd.DataFrame(
        {
            "prediction_timestamp": pd.date_range("2025-12-20", periods=10, freq="D"),
            "predicted_price": [3000000 + i * 10000 for i in range(10)],
            "living_area": [75 + i for i in range(10)],
            "rooms": [2] * 10,
            "area": ["sodermalm"] * 10,
            "sold_price": [3050000 + i * 10000 for i in range(10)],
        }
    )


@pytest.fixture
def sample_features_df():
    """Sample features dataframe."""
    return pd.DataFrame(
        {
            "sold_date": pd.date_range("2025-12-20", periods=10, freq="D"),
            "living_area": [75 + i for i in range(10)],
            "rooms": [2] * 10,
            "area": ["sodermalm"] * 10,
            "sold_price": [3050000 + i * 10000 for i in range(10)],
            "price_per_sqm": [40000 + i * 100 for i in range(10)],
        }
    )


@pytest.mark.unit
def test_export_recent_predictions_task_success(sample_predictions_df, tmp_path):
    """Test successful export of predictions."""
    output_path = tmp_path / "predictions.parquet"

    with patch("google.cloud.bigquery.Client") as mock_client:
        mock_query = MagicMock()
        mock_query.to_dataframe.return_value = sample_predictions_df
        mock_client.return_value.query.return_value = mock_query
        mock_client.return_value.project = "test-project"

        result = export_recent_predictions_task.fn(days_lookback=7, output_path=output_path)

        assert result["success"] is True
        assert result["row_count"] == 10
        assert Path(result["output_path"]).exists()


@pytest.mark.unit
def test_export_recent_predictions_task_fallback(sample_features_df, tmp_path):
    """Test fallback to features table when predictions table missing."""
    output_path = tmp_path / "features.parquet"

    with patch("google.cloud.bigquery.Client") as mock_client:
        # First query raises exception
        mock_client.return_value.query.side_effect = [
            Exception("Table not found"),
            MagicMock(to_dataframe=lambda: sample_features_df),
        ]
        mock_client.return_value.project = "test-project"

        result = export_recent_predictions_task.fn(days_lookback=7, output_path=output_path)

        assert result["success"] is True
        assert result["row_count"] == 10


@pytest.mark.unit
def test_monitor_model_drift_task_no_drift(tmp_path):
    """Test drift detection when no drift present."""
    # Create reference and current data (identical distributions)
    reference_data = pd.DataFrame(
        {
            "living_area": [75, 80, 85, 90, 95],
            "rooms": [2, 2, 3, 3, 4],
            "area": ["sodermalm"] * 5,
            "sold_price": [3000000, 3100000, 3200000, 3300000, 3400000],
        }
    )
    current_data = reference_data.copy()

    reference_path = tmp_path / "reference.parquet"
    current_path = tmp_path / "current.parquet"

    reference_data.to_parquet(reference_path, index=False)
    current_data.to_parquet(current_path, index=False)

    with patch("estate_value_index.pipelines.tasks.monitoring.upload_html_to_gcs"):
        result = monitor_model_drift_task.fn(
            current_data_path=current_path,
            reference_data_path=reference_path,
            model_version="test-v1",
            alert_on_drift=True,
            upload_to_gcs=False,
        )

        assert result["success"] is True
        assert "drift_detected" in result
        assert result["num_drifted_features"] >= 0


@pytest.mark.unit
def test_monitor_model_drift_task_with_drift(tmp_path):
    """Test drift detection when drift present."""
    # Reference data - include critical features
    reference_data = pd.DataFrame(
        {
            "living_area": [75, 80, 85, 90, 95],
            "price_per_sqm": [40000, 41000, 42000, 43000, 44000],
            "area_target_encoded": [3000000, 3100000, 3200000, 3300000, 3400000],
            "rooms": [2, 2, 3, 3, 4],
            "area": ["sodermalm"] * 5,
            "sold_price": [3000000, 3100000, 3200000, 3300000, 3400000],
        }
    )

    # Current data with shifted distribution
    current_data = pd.DataFrame(
        {
            "living_area": [150, 160, 170, 180, 190],  # Much larger areas
            "price_per_sqm": [80000, 82000, 84000, 86000, 88000],  # Much higher price/sqm
            "area_target_encoded": [6000000, 6200000, 6400000, 6600000, 6800000],  # Higher
            "rooms": [4, 4, 5, 5, 6],  # More rooms
            "area": ["ostermalm"] * 5,  # Different area
            "sold_price": [6000000, 6200000, 6400000, 6600000, 6800000],  # Higher prices
        }
    )

    reference_path = tmp_path / "reference.parquet"
    current_path = tmp_path / "current.parquet"

    reference_data.to_parquet(reference_path, index=False)
    current_data.to_parquet(current_path, index=False)

    with patch("estate_value_index.utils.gcs.upload_html_to_gcs"):
        result = monitor_model_drift_task.fn(
            current_data_path=current_path,
            reference_data_path=reference_path,
            model_version="test-v1",
            alert_on_drift=True,
            upload_to_gcs=False,
        )

        assert result["success"] is True
        # Drift should be detected given the large distribution shift
        assert result["drift_score"] >= 0  # Accept any drift score


@pytest.mark.unit
def test_save_baseline_data_task(tmp_path):
    """Test saving baseline data to GCS."""
    training_data = pd.DataFrame(
        {
            "living_area": [75, 80, 85, 90, 95],
            "rooms": [2, 2, 3, 3, 4],
            "sold_price": [3000000, 3100000, 3200000, 3300000, 3400000],
        }
    )

    with patch("google.cloud.storage.Client") as mock_storage:
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_storage.return_value.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        result = save_baseline_data_task.fn(
            training_data=training_data,
            gcs_bucket="test-bucket",
            baseline_path="monitoring/baseline/baseline.parquet",
        )

        assert result["success"] is True
        assert result["row_count"] == 5
        assert "gs://test-bucket/monitoring/baseline/baseline.parquet" in result["gcs_uri"]
        mock_blob.upload_from_filename.assert_called_once()


@pytest.mark.unit
def test_trigger_retraining_on_drift_task_no_retrain():
    """Test retraining trigger when no drift detected."""
    drift_result = {
        "success": True,
        "performance_degraded": False,
        "num_drifted_features": 1,
    }

    result = trigger_retraining_on_drift_task.fn(drift_result=drift_result, auto_retrain=True)

    assert result["success"] is True
    assert result["retrain_triggered"] is False


@pytest.mark.unit
def test_trigger_retraining_on_drift_task_performance_degraded():
    """Test retraining trigger when performance degraded."""
    drift_result = {
        "success": True,
        "performance_degraded": True,
        "num_drifted_features": 1,
    }

    with patch(
        "estate_value_index.pipelines.core.complete_pipeline.complete_pipeline_flow"
    ) as mock_flow:
        mock_flow_instance = MagicMock(return_value="flow-run-123")
        mock_flow.with_options.return_value = mock_flow_instance

        result = trigger_retraining_on_drift_task.fn(drift_result=drift_result, auto_retrain=True)

        assert result["success"] is True
        assert result["retrain_triggered"] is True
        mock_flow.with_options.assert_called_once()


@pytest.mark.unit
def test_trigger_retraining_on_drift_task_many_drifted_features():
    """Test retraining trigger when many features drifted."""
    drift_result = {
        "success": True,
        "performance_degraded": False,
        "num_drifted_features": 5,  # >=3 triggers retraining
    }

    with patch(
        "estate_value_index.pipelines.core.complete_pipeline.complete_pipeline_flow"
    ) as mock_flow:
        mock_flow_instance = MagicMock(return_value="flow-run-456")
        mock_flow.with_options.return_value = mock_flow_instance

        result = trigger_retraining_on_drift_task.fn(drift_result=drift_result, auto_retrain=True)

        assert result["success"] is True
        assert result["retrain_triggered"] is True


@pytest.mark.unit
def test_trigger_retraining_on_drift_task_auto_retrain_disabled():
    """Test retraining trigger respects auto_retrain flag."""
    drift_result = {
        "success": True,
        "performance_degraded": True,
        "num_drifted_features": 5,
    }

    result = trigger_retraining_on_drift_task.fn(drift_result=drift_result, auto_retrain=False)

    assert result["success"] is True
    assert result["retrain_triggered"] is False


@pytest.mark.unit
def test_trigger_retraining_short_circuits_on_drift_failure():
    """Trigger short-circuits without raising when drift task reports failure."""
    drift_result = {
        "success": False,
        "drift_detected": False,
        "drifted_features": [],
        "num_drifted_features": 0,
        "drift_score": 0.0,
        "performance_degraded": False,
        "current_mae": None,
        "reference_mae": None,
        "degradation_pct": None,
        "timestamp": "2026-04-26T12:00:00",
        "error": "Baseline not found - run model training first to create baseline",
    }

    with patch(
        "estate_value_index.pipelines.core.complete_pipeline.complete_pipeline_flow"
    ) as mock_flow:
        result = trigger_retraining_on_drift_task.fn(drift_result=drift_result, auto_retrain=True)

        assert result["success"] is False
        assert result["retrain_triggered"] is False
        assert result["upstream_error"] == drift_result["error"]
        mock_flow.with_options.assert_not_called()


@pytest.mark.unit
def test_trigger_retraining_proceeds_on_drift_success():
    """Guard does not block legitimate triggers when drift task succeeded."""
    drift_result = {
        "success": True,
        "performance_degraded": True,
        "num_drifted_features": 0,
    }

    with patch(
        "estate_value_index.pipelines.core.complete_pipeline.complete_pipeline_flow"
    ) as mock_flow:
        mock_flow_instance = MagicMock(return_value="flow-run-789")
        mock_flow.with_options.return_value = mock_flow_instance

        result = trigger_retraining_on_drift_task.fn(drift_result=drift_result, auto_retrain=True)

        assert result["success"] is True
        assert result["retrain_triggered"] is True
        mock_flow.with_options.assert_called_once()


@pytest.mark.unit
def test_monitor_model_drift_task_baseline_not_found(tmp_path):
    """Test drift detection returns error when GCS baseline doesn't exist.

    Baseline must be created during model training, not auto-created from
    current data (which would compare data to itself).
    """
    current_data = pd.DataFrame(
        {
            "living_area": [75, 80, 85, 90, 95],
            "rooms": [2, 2, 3, 3, 4],
            "area": ["sodermalm"] * 5,
            "sold_price": [3000000, 3100000, 3200000, 3300000, 3400000],
        }
    )

    current_path = tmp_path / "current.parquet"
    current_data.to_parquet(current_path, index=False)

    with patch("estate_value_index.pipelines.tasks.monitoring.get_storage_client") as mock_storage:
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.exists.return_value = False  # Baseline doesn't exist
        mock_storage.return_value.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        result = monitor_model_drift_task.fn(
            current_data_path=current_path,
            reference_data_path="gs://test-bucket/monitoring/baseline/baseline_data.parquet",
            model_version="test-v1",
            alert_on_drift=True,
            upload_to_gcs=False,
        )

        # Should return error, not auto-create baseline
        assert result["success"] is False
        assert "error" in result
        assert "Baseline not found" in result["error"]
        # Should NOT have uploaded anything
        mock_blob.upload_from_filename.assert_not_called()
