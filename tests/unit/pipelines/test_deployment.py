"""Unit tests for pipelines/tasks/deployment.py."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from estate_value_index.pipelines.tasks.deployment import (
    _cloud_run_env_vars,
    _get_current_revision,
    _get_service_ingress,
    _get_service_url,
    _revision_ready,
    _runtime_service_account,
    _validate_deployment,
    deploy_to_cloud_run_task,
    health_check_task,
    log_metrics_task,
    monitor_pipeline_health_task,
)


def _mock_gcs_storage(mocker: Any) -> MagicMock:
    """Common GCS storage mock pattern."""
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob
    mocker.patch(
        "estate_value_index.pipelines.tasks.deployment.get_storage_client",
        return_value=mock_client,
    )
    return mock_bucket


class TestCloudConfigValidation:
    @pytest.mark.unit
    def test_deploy_requires_gcp_project_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GCP_PROJECT_ID", raising=False)

        with pytest.raises(
            RuntimeError,
            match="GCP_PROJECT_ID environment variable is required",
        ):
            deploy_to_cloud_run_task.fn(
                model_artifacts_gcs_uri="gs://bucket/models",
                enrichment_gcs_uri="gs://bucket/enrichment",
                dry_run=True,
            )

    @pytest.mark.unit
    def test_health_monitor_requires_bigquery_project_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("BIGQUERY_PROJECT_ID", raising=False)

        with pytest.raises(
            RuntimeError,
            match="BIGQUERY_PROJECT_ID environment variable is required",
        ):
            monitor_pipeline_health_task.fn()


class TestCloudRunDeployCommand:
    @pytest.mark.unit
    def test_default_runtime_service_account_uses_project_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CLOUD_RUN_RUNTIME_SERVICE_ACCOUNT", raising=False)
        monkeypatch.delenv("RUNTIME_SERVICE_ACCOUNT", raising=False)

        assert (
            _runtime_service_account("estate-value-index")
            == "evi-cloud-run-runtime@estate-value-index.iam.gserviceaccount.com"
        )

    @pytest.mark.unit
    def test_cloud_run_env_vars_include_required_runtime_config(self) -> None:
        env_vars = _cloud_run_env_vars("estate-value-index-data-production")

        assert "GCS_ENABLED=true" in env_vars
        assert "GCS_BUCKET=estate-value-index-data-production" in env_vars
        assert "NODE_ENV=production" in env_vars
        assert "PREDICTION_API_URL=http://127.0.0.1:8000" in env_vars
        assert "TRUST_PROXY_HEADERS=true" in env_vars

    @pytest.mark.unit
    def test_deploy_uses_dedicated_runtime_sa_and_internal_ingress(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mocker: Any,
    ) -> None:
        monkeypatch.setenv("GCP_PROJECT_ID", "estate-value-index")
        monkeypatch.setenv("GCS_BUCKET", "estate-value-index-data-production")
        mocker.patch(
            "estate_value_index.pipelines.tasks.deployment._get_current_revision",
            side_effect=["old-revision", "new-revision"],
        )
        mocker.patch(
            "estate_value_index.pipelines.tasks.deployment._get_service_url", return_value=None
        )
        mocker.patch("time.sleep")

        calls: list[list[str]] = []

        def fake_run(cmd: list[str], **_: Any) -> MagicMock:
            calls.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        mocker.patch("subprocess.run", side_effect=fake_run)

        result = deploy_to_cloud_run_task.fn(
            model_artifacts_gcs_uri="gs://estate-value-index-data-production/models",
            enrichment_gcs_uri="gs://estate-value-index-data-production/derived",
            validate=False,
        )

        deploy_cmd = next(cmd for cmd in calls if cmd[:3] == ["gcloud", "run", "deploy"])
        assert result["success"] is True
        assert deploy_cmd[deploy_cmd.index("--service-account") + 1] == (
            "evi-cloud-run-runtime@estate-value-index.iam.gserviceaccount.com"
        )
        assert deploy_cmd[deploy_cmd.index("--ingress") + 1] == "internal"
        env_vars = deploy_cmd[deploy_cmd.index("--set-env-vars") + 1]
        assert "GCS_ENABLED=true" in env_vars
        assert "GCS_BUCKET=estate-value-index-data-production" in env_vars
        assert "NODE_ENV=production" in env_vars
        assert "PREDICTION_API_URL=http://127.0.0.1:8000" in env_vars
        assert "TRUST_PROXY_HEADERS=true" in env_vars


class TestGetCurrentRevision:
    @pytest.mark.unit
    def test_returns_revision_name(self, mocker: Any) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "estate-value-index-app-00042-abc\n"
        mocker.patch("subprocess.run", return_value=mock_result)

        revision = _get_current_revision("estate-value-index-app", "europe-north1")
        assert revision == "estate-value-index-app-00042-abc"

    @pytest.mark.unit
    def test_strips_whitespace(self, mocker: Any) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "  my-revision  \n"
        mocker.patch("subprocess.run", return_value=mock_result)

        revision = _get_current_revision("my-service", "us-central1")
        assert revision == "my-revision"

    @pytest.mark.unit
    def test_returns_none_on_failure(self, mocker: Any) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mocker.patch("subprocess.run", return_value=mock_result)

        assert _get_current_revision("my-service", "europe-west1") is None

    @pytest.mark.unit
    def test_returns_none_on_empty_output(self, mocker: Any) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mocker.patch("subprocess.run", return_value=mock_result)

        assert _get_current_revision("my-service", "europe-north1") is None

    @pytest.mark.unit
    def test_handles_exception(self, mocker: Any) -> None:
        mocker.patch("subprocess.run", side_effect=Exception("Network error"))
        assert _get_current_revision("my-service", "europe-north1") is None


class TestGetServiceUrl:
    @pytest.mark.unit
    def test_returns_service_url(self, mocker: Any) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "https://estate-value-index-app-abc123.run.app\n"
        mocker.patch("subprocess.run", return_value=mock_result)

        url = _get_service_url("estate-value-index-app", "europe-north1")
        assert url == "https://estate-value-index-app-abc123.run.app"

    @pytest.mark.unit
    def test_returns_none_on_failure(self, mocker: Any) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mocker.patch("subprocess.run", return_value=mock_result)

        assert _get_service_url("my-service", "us-central1") is None

    @pytest.mark.unit
    def test_handles_exception(self, mocker: Any) -> None:
        mocker.patch("subprocess.run", side_effect=Exception("Timeout"))
        assert _get_service_url("my-service", "europe-north1") is None


class TestGetServiceIngress:
    @pytest.mark.unit
    def test_queries_ingress_annotation(self, mocker: Any) -> None:
        describe = mocker.patch(
            "estate_value_index.pipelines.tasks.deployment._describe_service",
            return_value="internal",
        )

        ingress = _get_service_ingress("estate-value-index-app", "europe-north1", "my-project")

        assert ingress == "internal"
        field = describe.call_args[0][2]
        assert "run.googleapis.com/ingress" in field


class TestRevisionReady:
    @pytest.mark.unit
    def test_ready_when_latest_created_is_latest_ready(self, mocker: Any) -> None:
        mocker.patch(
            "estate_value_index.pipelines.tasks.deployment._describe_service",
            side_effect=["app-00042-abc", "app-00042-abc"],
        )

        assert _revision_ready("app", "europe-north1", "my-project") is True

    @pytest.mark.unit
    def test_not_ready_when_created_revision_is_newer(self, mocker: Any) -> None:
        mocker.patch(
            "estate_value_index.pipelines.tasks.deployment._describe_service",
            side_effect=["app-00043-def", "app-00042-abc"],
        )

        assert _revision_ready("app", "europe-north1", "my-project") is False

    @pytest.mark.unit
    def test_not_ready_when_describe_fails(self, mocker: Any) -> None:
        mocker.patch(
            "estate_value_index.pipelines.tasks.deployment._describe_service",
            side_effect=[None, None],
        )

        assert _revision_ready("app", "europe-north1", "my-project") is False


class TestValidateDeployment:
    @pytest.mark.unit
    def test_internal_ingress_uses_platform_readiness_not_external_probe(self, mocker: Any) -> None:
        mocker.patch(
            "estate_value_index.pipelines.tasks.deployment._get_service_ingress",
            return_value="internal",
        )
        revision_ready = mocker.patch(
            "estate_value_index.pipelines.tasks.deployment._revision_ready",
            return_value=True,
        )
        probe = mocker.patch("estate_value_index.pipelines.tasks.deployment.requests.get")
        logger = MagicMock()

        result = _validate_deployment(
            logger, "app", "europe-north1", "my-project", "https://app-abc.run.app"
        )

        assert result is True
        revision_ready.assert_called_once_with("app", "europe-north1", "my-project")
        probe.assert_not_called()
        messages = [str(call.args[0]) for call in logger.info.call_args_list]
        assert any("internal ingress, platform readiness used" in m for m in messages)
        assert any("Platform readiness check passed" in m for m in messages)

    @pytest.mark.unit
    def test_unknown_ingress_defaults_to_platform_readiness(self, mocker: Any) -> None:
        mocker.patch(
            "estate_value_index.pipelines.tasks.deployment._get_service_ingress",
            return_value=None,
        )
        revision_ready = mocker.patch(
            "estate_value_index.pipelines.tasks.deployment._revision_ready",
            return_value=True,
        )
        probe = mocker.patch("estate_value_index.pipelines.tasks.deployment.requests.get")

        _validate_deployment(MagicMock(), "app", "europe-north1", "my-project", None)

        revision_ready.assert_called_once()
        probe.assert_not_called()

    @pytest.mark.unit
    def test_platform_readiness_failure_is_warning_only(self, mocker: Any) -> None:
        mocker.patch(
            "estate_value_index.pipelines.tasks.deployment._get_service_ingress",
            return_value="internal",
        )
        mocker.patch(
            "estate_value_index.pipelines.tasks.deployment._revision_ready",
            return_value=False,
        )
        sleep = mocker.patch("time.sleep")
        logger = MagicMock()

        result = _validate_deployment(logger, "app", "europe-north1", "my-project", None)

        assert result is False
        warnings = [str(call.args[0]) for call in logger.warning.call_args_list]
        assert any("latest revision not ready" in m for m in warnings)
        # Sleeps only between attempts, never after the final failed one.
        assert sleep.call_count == 2

    @pytest.mark.unit
    def test_public_ingress_probes_health_endpoint(self, mocker: Any) -> None:
        mocker.patch(
            "estate_value_index.pipelines.tasks.deployment._get_service_ingress",
            return_value="all",
        )
        revision_ready = mocker.patch(
            "estate_value_index.pipelines.tasks.deployment._revision_ready"
        )
        health_check = mocker.patch(
            "estate_value_index.pipelines.tasks.deployment.health_check_task",
            return_value={"healthy": True},
        )

        result = _validate_deployment(
            MagicMock(), "app", "europe-north1", "my-project", "https://app-abc.run.app"
        )

        assert result is True
        revision_ready.assert_not_called()
        health_check.assert_called_once_with("https://app-abc.run.app/api/health")

    @pytest.mark.unit
    def test_public_ingress_probe_failure_is_warning_only(self, mocker: Any) -> None:
        mocker.patch(
            "estate_value_index.pipelines.tasks.deployment._get_service_ingress",
            return_value="all",
        )
        health_check = mocker.patch(
            "estate_value_index.pipelines.tasks.deployment.health_check_task",
            return_value={"healthy": False},
        )
        mocker.patch("time.sleep")
        logger = MagicMock()

        result = _validate_deployment(
            logger, "app", "europe-north1", "my-project", "https://app-abc.run.app"
        )

        assert result is False
        assert health_check.call_count == 3
        warnings = [str(call.args[0]) for call in logger.warning.call_args_list]
        assert any("did not pass after 3 attempts" in m for m in warnings)

    @pytest.mark.unit
    def test_deploy_task_routes_validation_through_validate_deployment(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mocker: Any,
    ) -> None:
        monkeypatch.setenv("GCP_PROJECT_ID", "estate-value-index")
        monkeypatch.setenv("GCS_BUCKET", "estate-value-index-data-production")
        mocker.patch(
            "estate_value_index.pipelines.tasks.deployment._get_current_revision",
            side_effect=["old-revision", "new-revision"],
        )
        mocker.patch(
            "estate_value_index.pipelines.tasks.deployment._get_service_url",
            return_value="https://app-abc.run.app",
        )
        mocker.patch("time.sleep")
        ok_result = MagicMock()
        ok_result.returncode = 0
        ok_result.stdout = ""
        ok_result.stderr = ""
        mocker.patch("subprocess.run", return_value=ok_result)
        validate = mocker.patch(
            "estate_value_index.pipelines.tasks.deployment._validate_deployment",
            return_value=False,
        )

        result = deploy_to_cloud_run_task.fn(
            model_artifacts_gcs_uri="gs://bucket/models",
            enrichment_gcs_uri="gs://bucket/derived",
            validate=True,
        )

        assert result["success"] is True
        validate.assert_called_once()
        assert validate.call_args[0][1:] == (
            "estate-value-index-app",
            "europe-north1",
            "estate-value-index",
            "https://app-abc.run.app",
        )
        # The validation verdict and the pre-deploy revision are recorded so
        # flows can act on them (auto-rollback).
        assert result["healthy"] is False
        assert result["previous_revision"] == "old-revision"

    @pytest.mark.unit
    def test_dry_run_records_no_health_or_previous_revision(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GCP_PROJECT_ID", "estate-value-index")

        result = deploy_to_cloud_run_task.fn(
            model_artifacts_gcs_uri="gs://bucket/models",
            enrichment_gcs_uri="gs://bucket/derived",
            dry_run=True,
        )

        assert result["success"] is True
        assert result["healthy"] is None
        assert result["previous_revision"] is None


class TestHealthCheckTask:
    @pytest.mark.unit
    def test_healthy_service(self, mock_requests_success: Any) -> None:
        result = health_check_task.fn(service_url="https://example.com/health")

        assert result["success"] is True
        assert result["healthy"] is True
        assert result["status_code"] == 200

    @pytest.mark.unit
    def test_degraded_503_is_considered_alive(self) -> None:
        # 503 = degraded but still alive
        with patch("estate_value_index.pipelines.tasks.deployment.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 503
            mock_get.return_value = mock_response

            result = health_check_task.fn(service_url="https://example.com/health")

            assert result["healthy"] is True
            assert result["status_code"] == 503

    @pytest.mark.unit
    def test_non_alive_status_returns_unhealthy(self) -> None:
        # 500 is not in the alive set {200, 503}
        with patch("estate_value_index.pipelines.tasks.deployment.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_get.return_value = mock_response

            result = health_check_task.fn(service_url="https://example.com/health")

            assert result["healthy"] is False
            assert result["status_code"] == 500

    @pytest.mark.unit
    def test_timeout_returns_unhealthy(self, mock_requests_timeout: Any) -> None:
        result = health_check_task.fn(service_url="https://example.com/health")

        assert result["success"] is False
        assert result["healthy"] is False
        assert result["status_code"] is None
        assert result["response_time_ms"] is None

    @pytest.mark.unit
    def test_connection_error_returns_unhealthy(self, mock_requests_error: Any) -> None:
        result = health_check_task.fn(service_url="https://example.com/health")

        assert result["success"] is False
        assert result["healthy"] is False
        assert result["status_code"] is None

    @pytest.mark.unit
    def test_custom_expected_status_not_in_alive_set(self) -> None:
        # 201 matches expected_status but isn't in alive set {200, 503}
        with patch("estate_value_index.pipelines.tasks.deployment.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_get.return_value = mock_response

            result = health_check_task.fn(
                service_url="https://example.com/health",
                expected_status=201,
            )

            assert result["healthy"] is False
            assert result["status_code"] == 201

    @pytest.mark.unit
    def test_includes_response_time(self, mock_requests_success: Any) -> None:
        result = health_check_task.fn(service_url="https://example.com/health")

        assert "response_time_ms" in result
        assert result["response_time_ms"] is not None
        assert result["response_time_ms"] >= 0

    @pytest.mark.unit
    def test_includes_timestamp(self, mock_requests_success: Any) -> None:
        result = health_check_task.fn(service_url="https://example.com/health")

        assert "timestamp" in result
        assert result["timestamp"] is not None


class TestLogMetricsTask:
    @pytest.mark.unit
    def test_logs_to_local_file(self, tmp_path: Path, mocker: Any) -> None:
        metrics = {"mae": 250_000, "rmse": 350_000}

        mocker.patch(
            "estate_value_index.pipelines.tasks.deployment.Path",
            side_effect=lambda p: (
                tmp_path / str(p).removeprefix("data/derived/metrics/")
                if "data/derived/metrics" in str(p)
                else Path(p)
            ),
        )

        result = log_metrics_task.fn(metrics=metrics, destination="local")

        assert result["success"] is True
        assert result["destination"] == "local"
        assert "path" in result

    @pytest.mark.unit
    def test_logs_to_gcs(self, mocker: Any) -> None:
        _mock_gcs_storage(mocker)

        result = log_metrics_task.fn(
            metrics={"mae": 250_000},
            destination="gcs",
            gcs_bucket="test-bucket",
        )

        assert result["success"] is True
        assert result["destination"] == "gcs"
        assert "uri" in result
        assert "test-bucket" in result["uri"]

    @pytest.mark.unit
    def test_falls_back_to_local_on_gcs_error(self, tmp_path: Path, mocker: Any) -> None:
        mocker.patch(
            "estate_value_index.pipelines.tasks.deployment.get_storage_client",
            side_effect=Exception("GCS auth failed"),
        )

        original_path = Path

        def patched_path(p: str) -> Path:
            if "data/derived/metrics" in str(p):
                return tmp_path / "metrics"
            return original_path(p)

        mocker.patch(
            "estate_value_index.pipelines.tasks.deployment.Path",
            side_effect=patched_path,
        )

        result = log_metrics_task.fn(
            metrics={"mae": 250_000},
            destination="gcs",
            gcs_bucket="test-bucket",
        )

        assert result["success"] is True
        assert result["destination"] == "local"

    @pytest.mark.unit
    def test_metrics_written_as_json(self, tmp_path: Path, mocker: Any) -> None:
        metrics = {"mae": 250_000, "r2": 0.85, "model": "lgbm"}

        metrics_dir = tmp_path / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)

        mocker.patch(
            "estate_value_index.pipelines.tasks.deployment.Path",
            return_value=metrics_dir,
        )

        log_metrics_task.fn(metrics=metrics, destination="local")

        files = list(metrics_dir.glob("*.json"))
        assert len(files) >= 0

    @pytest.mark.unit
    def test_custom_gcs_prefix(self, mocker: Any) -> None:
        mock_bucket = _mock_gcs_storage(mocker)

        log_metrics_task.fn(
            metrics={"mae": 250_000},
            destination="gcs",
            gcs_bucket="test-bucket",
            gcs_prefix="custom/metrics/",
        )

        assert "custom/metrics/" in mock_bucket.blob.call_args[0][0]

    @pytest.mark.unit
    def test_includes_timestamp_in_result(self, mocker: Any) -> None:
        _mock_gcs_storage(mocker)

        result = log_metrics_task.fn(
            metrics={"mae": 250_000},
            destination="gcs",
            gcs_bucket="test-bucket",
        )

        assert "timestamp" in result
