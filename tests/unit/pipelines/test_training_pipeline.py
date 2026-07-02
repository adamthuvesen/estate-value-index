"""Unit tests for the Vertex training flow helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from estate_value_index.pipelines.core import training_pipeline
from estate_value_index.pipelines.core.training_pipeline import (
    _artifact_locations_from_job_info,
    _download_artifacts_stage,
    _monitor_job_stage,
    _resolve_artifacts_from_job_info,
    _submit_training_job_stage,
    _VertexJobState,
)
from estate_value_index.pipelines.utils import TrainingFlowConfig


class TestArtifactLocationsFromJobInfo:
    @pytest.mark.unit
    def test_reads_model_dir_and_prefix_from_container_args(self) -> None:
        job_info = {
            "jobSpec": {
                "workerPoolSpecs": [
                    {
                        "containerSpec": {
                            "args": [
                                "--model-dir",
                                "gs://bucket/vertex-ai/models/20260101-010203",
                                "--model-prefix",
                                "vertex-lgbm-20260101-010203",
                            ]
                        }
                    }
                ]
            }
        }

        locations = _artifact_locations_from_job_info(job_info)

        assert locations.model_uri == "gs://bucket/vertex-ai/models/20260101-010203"
        assert locations.model_prefix == "vertex-lgbm-20260101-010203"

    @pytest.mark.unit
    def test_uses_model_artifacts_env_var_as_model_uri_fallback(self) -> None:
        job_info = {
            "jobSpec": {
                "workerPoolSpecs": [
                    {
                        "containerSpec": {
                            "env": [
                                {
                                    "name": "MODEL_ARTIFACTS_URI",
                                    "value": "gs://bucket/vertex-ai/models/env-run",
                                }
                            ]
                        }
                    }
                ]
            }
        }

        locations = _artifact_locations_from_job_info(job_info)

        assert locations.model_uri == "gs://bucket/vertex-ai/models/env-run"
        assert locations.model_prefix is None


class TestResolveArtifactsFromJobInfo:
    @pytest.mark.unit
    def test_updates_missing_state_and_submission_results(self) -> None:
        monitoring_results = {
            "job_info": {
                "jobSpec": {
                    "workerPoolSpecs": [
                        {
                            "containerSpec": {
                                "args": [
                                    "--model-dir",
                                    "gs://bucket/vertex-ai/models/20260101-010203",
                                    "--model-prefix",
                                    "custom-prefix",
                                ]
                            }
                        }
                    ]
                }
            }
        }
        state = _VertexJobState(submission_results={})
        results = {"configuration": {}}

        _resolve_artifacts_from_job_info(monitoring_results, state, results, MagicMock())

        assert state.model_uri == "gs://bucket/vertex-ai/models/20260101-010203"
        assert state.run_id == "20260101-010203"
        assert state.resolved_model_prefix == "custom-prefix"
        assert state.submission_results["model_uri"] == state.model_uri
        assert state.submission_results["run_id"] == state.run_id
        assert state.submission_results["model_prefix"] == "custom-prefix"
        assert results["configuration"]["model_prefix"] == "custom-prefix"

    @pytest.mark.unit
    def test_derives_prefix_from_run_id_when_job_info_has_no_prefix(self) -> None:
        monitoring_results = {
            "job_info": {
                "jobSpec": {
                    "workerPoolSpecs": [
                        {
                            "containerSpec": {
                                "env": [
                                    {
                                        "name": "MODEL_ARTIFACTS_URI",
                                        "value": "gs://bucket/vertex-ai/models/env-run",
                                    }
                                ]
                            }
                        }
                    ]
                }
            }
        }
        state = _VertexJobState(submission_results={})
        results = {"configuration": {}}

        _resolve_artifacts_from_job_info(monitoring_results, state, results, MagicMock())

        assert state.run_id == "env-run"
        assert state.resolved_model_prefix == "vertex-lgbm-env-run"


class TestSubmitTrainingJobStage:
    @pytest.mark.unit
    def test_does_not_seed_resolved_prefix_from_configured_prefix(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression for run 28585979280: seeding the state with the production
        prefix blocked the monitor-stage resolver, so the download looked for
        price_prediction_model_* while GCS held vertex-lgbm-{run_id}_*."""
        submission_results = {
            "success": True,
            "job_id": "projects/p/locations/europe-north1/customJobs/123",
            "run_id": "20260702-112242",
            "model_uri": "gs://bucket/vertex-ai/models/20260702-112242",
            "output_uri": None,
            "timestamp": "2026-07-02T11:22:42",
        }
        monkeypatch.setattr(
            training_pipeline,
            "submit_vertex_training_job_task",
            lambda **kwargs: submission_results,
        )
        results = {"configuration": {"model_prefix": "price_prediction_model"}, "steps": {}}

        state, should_return = _submit_training_job_stage(
            TrainingFlowConfig(), results, MagicMock()
        )

        assert should_return is False
        assert state is not None
        assert state.resolved_model_prefix is None
        assert results["configuration"]["model_prefix"] == "price_prediction_model"

    @pytest.mark.unit
    def test_uses_prefix_from_submission_output_when_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        submission_results = {
            "success": True,
            "job_id": "projects/p/locations/europe-north1/customJobs/123",
            "run_id": "20260702-112242",
            "model_uri": "gs://bucket/vertex-ai/models/20260702-112242",
            "model_prefix": "vertex-lgbm-20260702-112242",
            "output_uri": None,
            "timestamp": "2026-07-02T11:22:42",
        }
        monkeypatch.setattr(
            training_pipeline,
            "submit_vertex_training_job_task",
            lambda **kwargs: submission_results,
        )
        results = {"configuration": {"model_prefix": "price_prediction_model"}, "steps": {}}

        state, should_return = _submit_training_job_stage(
            TrainingFlowConfig(), results, MagicMock()
        )

        assert should_return is False
        assert state is not None
        assert state.resolved_model_prefix == "vertex-lgbm-20260702-112242"
        assert results["configuration"]["model_prefix"] == "vertex-lgbm-20260702-112242"


class TestMonitorJobStage:
    @pytest.mark.unit
    def test_resolves_run_prefix_when_model_uri_known_but_prefix_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The production failure path: submission yields a model URI but no
        prefix, so the monitor stage must still derive vertex-lgbm-{run_id}."""
        monkeypatch.setattr(
            training_pipeline,
            "poll_vertex_job_status_task",
            lambda **kwargs: {"success": True, "duration_seconds": 60.0, "job_info": {}},
        )
        state = _VertexJobState(
            job_id="projects/p/locations/europe-north1/customJobs/123",
            run_id="20260702-112242",
            model_uri="gs://bucket/vertex-ai/models/20260702-112242",
            submission_results={},
        )
        results = {"configuration": {"model_prefix": "price_prediction_model"}, "steps": {}}

        _monitor_job_stage(TrainingFlowConfig(), state, results, MagicMock())

        assert state.resolved_model_prefix == "vertex-lgbm-20260702-112242"
        assert results["configuration"]["model_prefix"] == "vertex-lgbm-20260702-112242"


class TestDownloadArtifactsStage:
    @pytest.mark.unit
    def test_downloads_with_resolved_run_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}

        def fake_download(**kwargs):
            captured.update(kwargs)
            return {"success": True, "artifacts": {"lgbm": "web/models/x"}}

        monkeypatch.setattr(training_pipeline, "download_model_artifacts_task", fake_download)
        state = _VertexJobState(
            model_uri="gs://bucket/vertex-ai/models/20260702-112242",
            resolved_model_prefix="vertex-lgbm-20260702-112242",
            submission_results={},
        )
        results = {"steps": {}}

        early_return = _download_artifacts_stage(TrainingFlowConfig(), state, results, MagicMock())

        assert early_return is False
        assert captured["model_prefix"] == "vertex-lgbm-20260702-112242"

    @pytest.mark.unit
    def test_falls_back_to_configured_prefix_when_unresolved(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict = {}

        def fake_download(**kwargs):
            captured.update(kwargs)
            return {"success": True, "artifacts": {"lgbm": "web/models/x"}}

        monkeypatch.setattr(training_pipeline, "download_model_artifacts_task", fake_download)
        config = TrainingFlowConfig()
        state = _VertexJobState(
            model_uri="gs://bucket/vertex-ai/models/20260702-112242",
            submission_results={},
        )
        results = {"steps": {}}

        early_return = _download_artifacts_stage(config, state, results, MagicMock())

        assert early_return is False
        assert captured["model_prefix"] == config.model_prefix
        assert state.resolved_model_prefix == config.model_prefix
