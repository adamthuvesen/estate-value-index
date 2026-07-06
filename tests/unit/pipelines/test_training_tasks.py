"""Unit tests for pipelines/tasks/training.py."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from estate_value_index.model_artifacts import (
    NO_LIST_MODEL_ID,
    production_artifact_names,
    required_production_artifact_files,
)
from estate_value_index.pipelines.tasks.training import (
    _get_job_state,
    _parse_vertex_job_output,
    download_model_artifacts_task,
    promote_model_to_production_task,
    validate_model_performance_task,
)


class TestParseVertexJobOutput:
    @pytest.mark.unit
    def test_parse_job_id_from_stdout(self, vertex_job_stdout: str) -> None:
        result = _parse_vertex_job_output(vertex_job_stdout, "")

        assert result["job_id"] is not None
        assert "customJobs" in result["job_id"]
        assert "12345678" in result["job_id"]

    @pytest.mark.unit
    def test_parse_run_id(self, vertex_job_stdout: str) -> None:
        result = _parse_vertex_job_output(vertex_job_stdout, "")

        assert result["run_id"] == "20241201-123456"

    @pytest.mark.unit
    def test_parse_model_uri(self, vertex_job_stdout: str) -> None:
        result = _parse_vertex_job_output(vertex_job_stdout, "")

        assert result["model_uri"] is not None
        assert result["model_uri"].startswith("gs://")
        assert "models" in result["model_uri"]

    @pytest.mark.unit
    def test_parse_output_uri(self) -> None:
        stdout = "Job output saved to: gs://my-bucket/vertex-ai/jobs/20241201-123456"
        result = _parse_vertex_job_output(stdout, "")

        assert result["output_uri"] is not None
        assert "jobs" in result["output_uri"]

    @pytest.mark.unit
    def test_empty_output(self, vertex_job_stdout_empty: str) -> None:
        result = _parse_vertex_job_output(vertex_job_stdout_empty, "")

        assert result["success"] is True
        assert result["job_id"] is None
        assert result["run_id"] is None
        assert result["model_uri"] is None

    @pytest.mark.unit
    def test_minimal_output(self, vertex_job_stdout_minimal: str) -> None:
        result = _parse_vertex_job_output(vertex_job_stdout_minimal, "")

        assert result["job_id"] is not None
        assert "999" in result["job_id"]

    @pytest.mark.unit
    def test_parses_from_stderr_too(self) -> None:
        stderr = "Created: projects/proj/locations/region/customJobs/111"
        result = _parse_vertex_job_output("", stderr)

        assert result["job_id"] is not None
        assert "111" in result["job_id"]

    @pytest.mark.unit
    def test_extracts_run_id_from_model_uri(self) -> None:
        stdout = "Model saved to: gs://bucket/vertex-ai/models/20241215-091500"
        result = _parse_vertex_job_output(stdout, "")
        assert result["run_id"] == "20241215-091500"

    @pytest.mark.unit
    def test_result_has_timestamp(self) -> None:
        result = _parse_vertex_job_output("", "")

        assert "timestamp" in result
        assert result["timestamp"] is not None


class TestGetJobState:
    @pytest.mark.unit
    def test_returns_job_state(self, mocker: Any) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "JOB_STATE_SUCCEEDED\n"
        mocker.patch("subprocess.run", return_value=mock_result)

        state = _get_job_state("projects/p/locations/l/customJobs/123", "europe-north1")
        assert state == "JOB_STATE_SUCCEEDED"

    @pytest.mark.unit
    def test_strips_whitespace(self, mocker: Any) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "  JOB_STATE_RUNNING  \n"
        mocker.patch("subprocess.run", return_value=mock_result)

        state = _get_job_state("projects/p/locations/l/customJobs/123", "us-central1")
        assert state == "JOB_STATE_RUNNING"

    @pytest.mark.unit
    def test_calls_gcloud_correctly(self, mocker: Any) -> None:
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value = MagicMock(returncode=0, stdout="JOB_STATE_PENDING")

        _get_job_state("projects/p/locations/l/customJobs/456", "europe-west1")

        cmd = mock_run.call_args[0][0]
        assert "gcloud" in cmd
        assert "ai" in cmd
        assert "custom-jobs" in cmd
        assert "describe" in cmd
        assert "--region" in cmd
        assert "europe-west1" in cmd


class TestValidateModelPerformance:
    @pytest.mark.unit
    def test_median_ape_under_threshold_passes(self, temp_metrics_file: Path) -> None:
        # Fixture MdAPE is 6%; threshold of 8% should pass
        result = validate_model_performance_task.fn(
            metrics_path=temp_metrics_file,
            max_median_ape=0.08,
        )

        assert result["success"] is True
        assert result["validation_passed"] is True
        assert result["median_ape"] == 0.06

    @pytest.mark.unit
    def test_median_ape_over_threshold_fails(self, temp_metrics_file_high_mdape: Path) -> None:
        # Fixture MdAPE is 10%; threshold of 8% should fail
        result = validate_model_performance_task.fn(
            metrics_path=temp_metrics_file_high_mdape,
            max_median_ape=0.08,
        )

        assert result["validation_passed"] is False
        assert len(result["reasons"]) > 0
        assert "MdAPE" in result["reasons"][0]

    @pytest.mark.unit
    def test_rmse_validation(self, temp_metrics_file: Path) -> None:
        # Fixture RMSE is 350K; threshold of 400K should pass
        result = validate_model_performance_task.fn(
            metrics_path=temp_metrics_file,
            max_median_ape=0.08,
            max_rmse=400_000,
        )

        assert result["validation_passed"] is True
        assert result["rmse"] == 350_000

    @pytest.mark.unit
    def test_rmse_over_threshold_fails(self, temp_metrics_file: Path) -> None:
        # Fixture RMSE is 350K; threshold of 300K should fail
        result = validate_model_performance_task.fn(
            metrics_path=temp_metrics_file,
            max_median_ape=0.08,
            max_rmse=300_000,
        )

        assert result["validation_passed"] is False
        assert any("RMSE" in r for r in result["reasons"])

    @pytest.mark.unit
    def test_missing_median_ape_raises(self, tmp_path: Path) -> None:
        metrics_path = tmp_path / "bad_metrics.json"
        metrics_path.write_text(json.dumps({"rmse": 350_000}))

        with pytest.raises(ValueError, match="median_ape not found"):
            validate_model_performance_task.fn(metrics_path=metrics_path)

    @pytest.mark.unit
    def test_returns_correct_structure(self, temp_metrics_file: Path) -> None:
        result = validate_model_performance_task.fn(
            metrics_path=temp_metrics_file, max_median_ape=0.08
        )

        for field in [
            "success",
            "timestamp",
            "validation_passed",
            "median_ape",
            "mae",
            "rmse",
            "reasons",
        ]:
            assert field in result

    @pytest.mark.unit
    def test_handles_missing_rmse(self, tmp_path: Path) -> None:
        metrics_path = tmp_path / "mdape_only.json"
        metrics_path.write_text(json.dumps({"median_ape": 0.05}))

        result = validate_model_performance_task.fn(metrics_path=metrics_path, max_median_ape=0.08)

        assert result["validation_passed"] is True
        assert result["rmse"] == 0.0


class TestDownloadModelArtifacts:
    @pytest.mark.unit
    def test_invalid_model_uri_raises(self, temp_model_dir: Path) -> None:
        with pytest.raises(ValueError, match="Invalid model_uri"):
            download_model_artifacts_task.fn(model_uri="not-a-gcs-uri", local_dir=temp_model_dir)

    @pytest.mark.unit
    def test_empty_model_uri_raises(self, temp_model_dir: Path) -> None:
        with pytest.raises(ValueError, match="Invalid model_uri"):
            download_model_artifacts_task.fn(model_uri="", local_dir=temp_model_dir)

    @pytest.mark.unit
    def test_http_uri_raises(self, temp_model_dir: Path) -> None:
        with pytest.raises(ValueError, match="Invalid model_uri"):
            download_model_artifacts_task.fn(
                model_uri="https://storage.googleapis.com/bucket/model",
                local_dir=temp_model_dir,
            )

    @pytest.mark.unit
    def test_creates_local_dir(self, tmp_path: Path, mocker: Any) -> None:
        mocker.patch(
            "estate_value_index.pipelines.tasks.training.run_command",
            return_value=MagicMock(stdout="", stderr=""),
        )

        local_dir = tmp_path / "new_models_dir"
        assert not local_dir.exists()

        local_dir.mkdir(parents=True)
        (local_dir / production_artifact_names(NO_LIST_MODEL_ID).model).touch()

        result = download_model_artifacts_task.fn(
            model_uri="gs://bucket/vertex-ai/models/20241201",
            local_dir=local_dir,
        )

        assert result["success"] is True
        assert result["local_dir"] == str(local_dir)

    @pytest.mark.unit
    def test_returns_artifacts_dict(self, temp_model_dir: Path, mocker: Any) -> None:
        mocker.patch(
            "estate_value_index.pipelines.tasks.training.run_command",
            return_value=MagicMock(stdout="", stderr=""),
        )

        for filename in required_production_artifact_files():
            (temp_model_dir / filename).touch()

        result = download_model_artifacts_task.fn(
            model_uri="gs://bucket/models/20241201",
            local_dir=temp_model_dir,
        )

        assert result["success"] is True
        assert "artifacts" in result
        assert len(result["artifacts"]) >= 1

    @pytest.mark.unit
    def test_no_artifacts_raises(self, temp_model_dir: Path, mocker: Any) -> None:
        mocker.patch(
            "estate_value_index.pipelines.tasks.training.run_command",
            return_value=MagicMock(stdout="", stderr=""),
        )

        with pytest.raises(FileNotFoundError, match="No model artifacts found"):
            download_model_artifacts_task.fn(
                model_uri="gs://bucket/models/empty",
                local_dir=temp_model_dir,
            )


class TestPromoteModelToProduction:
    @pytest.mark.unit
    def test_promotes_sha256_sidecar_with_joblib(self, mocker: Any) -> None:
        """The .sha256 sidecar must be promoted alongside the joblib, else the
        API server refuses the model on an integrity mismatch (no-models 503)."""
        mocker.patch(
            "estate_value_index.pipelines.tasks.training.get_gcs_bucket",
            return_value="test-bucket",
        )
        copied: list[list[str]] = []
        mocker.patch(
            "estate_value_index.pipelines.tasks.training.run_command",
            side_effect=lambda cmd, *a, **k: copied.append(cmd),
        )

        promote_model_to_production_task.fn("gs://test-bucket/vertex-ai/models/20260706-160501")

        dests = [cmd[-1] for cmd in copied if "cp" in cmd]
        assert any(d.endswith(production_artifact_names(NO_LIST_MODEL_ID).model) for d in dests)
        assert any(d.endswith(production_artifact_names(NO_LIST_MODEL_ID).sidecar) for d in dests), (
            "sidecar must be promoted alongside the joblib"
        )
