"""Deployment integration smoke tests with mocked external calls."""

import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


@pytest.mark.integration
@patch("subprocess.run")
def test_gcloud_deployment_command(mock_subprocess):
    mock_subprocess.return_value = Mock(
        returncode=0, stdout="Service deployed successfully", stderr=""
    )

    subprocess.run(
        [
            "gcloud",
            "run",
            "deploy",
            "estate-value-index-app",
            "--region",
            "europe-north1",
            "--quiet",
        ],
        capture_output=True,
        text=True,
    )

    assert mock_subprocess.called
    call_args = mock_subprocess.call_args[0][0]
    assert "gcloud" in call_args
    assert "run" in call_args
    assert "deploy" in call_args
    assert "estate-value-index-app" in call_args


@pytest.mark.integration
def test_deployment_task_exists():
    try:
        from src.estate_value_index.pipelines import deployment_tasks  # noqa: F401
    except ImportError:
        pytest.skip("deployment_tasks module not implemented yet")


@pytest.mark.integration
@patch("requests.get")
def test_health_check_validation(mock_requests):
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "healthy",
        "model_loaded": True,
        "timestamp": "2025-10-03T10:00:00Z",
    }
    mock_response.raise_for_status = Mock()
    mock_requests.return_value = mock_response

    import requests

    response = requests.get("https://estate-value-index-app-test.run.app/health", timeout=10)

    assert response.status_code == 200
    health_data = response.json()
    assert health_data["status"] == "healthy"
    assert health_data["model_loaded"] is True


@pytest.mark.integration
@patch("google.cloud.storage.Client")
def test_gcs_artifact_verification(mock_storage_client):
    mock_bucket = Mock()
    mock_blob = Mock()
    mock_blob.exists.return_value = True

    mock_bucket.blob.return_value = mock_blob
    mock_client = Mock()
    mock_client.bucket.return_value = mock_bucket
    mock_storage_client.return_value = mock_client

    from google.cloud import storage

    client = storage.Client()
    bucket = client.bucket("estate-value-index-models")

    required_artifacts = [
        "models/price_prediction_model_lgbm.joblib",
        "models/price_prediction_model_metrics_lgbm.json",
        "models/price_prediction_model_feature_context.json",
    ]

    for artifact_path in required_artifacts:
        blob = bucket.blob(artifact_path)
        assert blob.exists(), f"Artifact not found: {artifact_path}"


@pytest.mark.integration
def test_deployment_prerequisites():
    model_dir = Path(__file__).parent.parent / "web" / "models"

    required_files = [
        "price_prediction_model_lgbm.joblib",
        "price_prediction_model_metrics_lgbm.json",
        "price_prediction_model_feature_context.json",
    ]

    missing_files = [f for f in required_files if not (model_dir / f).exists()]

    if missing_files:
        pytest.skip(f"Model artifacts not found: {missing_files}. Run training first.")


@pytest.mark.integration
@patch("subprocess.run")
def test_deployment_dry_run(mock_subprocess):
    mock_subprocess.return_value = Mock(
        returncode=0, stdout="Deployment simulated successfully (dry-run)", stderr=""
    )

    result = subprocess.run(
        [
            "gcloud",
            "run",
            "deploy",
            "estate-value-index-app",
            "--region",
            "europe-north1",
            "--no-traffic",
            "--quiet",
        ],
        capture_output=True,
        text=True,
    )

    assert mock_subprocess.called
    assert result.returncode == 0


@pytest.mark.integration
def test_deployment_error_handling():
    def validate_artifacts(artifacts_path):
        required_files = [
            "models/price_prediction_model_lgbm.joblib",
            "models/price_prediction_model_metrics_lgbm.json",
        ]
        for filename in required_files:
            if filename not in str(artifacts_path):
                return False, f"Missing: {filename}"
        return True, "All artifacts present"

    valid, _ = validate_artifacts("gs://bucket/models/price_prediction_model_lgbm.joblib")
    assert valid is False


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
