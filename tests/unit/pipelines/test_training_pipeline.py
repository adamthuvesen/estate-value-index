"""Unit tests for the Vertex training flow helpers."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import estate_value_index.pipelines.tasks as pipeline_tasks
from estate_value_index.pipelines.constants import DEFAULT_MAE_THRESHOLD
from estate_value_index.pipelines.core import training_pipeline
from estate_value_index.pipelines.core.training_pipeline import (
    _artifact_locations_from_job_info,
    _download_artifacts_stage,
    _generate_enrichment_stage,
    _monitor_job_stage,
    _resolve_artifacts_from_job_info,
    _submit_training_job_stage,
    _validate_and_promote_stage,
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


class TestValidateAndPromoteStage:
    def _validation_result(self, passed: bool) -> dict:
        return {
            "validation_passed": passed,
            "mae": 271_788.0,
            "rmse": None,
            "r2": None,
            "reasons": [] if passed else ["MAE (271,788) exceeds threshold"],
        }

    @pytest.mark.unit
    def test_sets_validation_mae_passed_true_when_validation_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            training_pipeline,
            "validate_model_performance_task",
            lambda **kwargs: self._validation_result(passed=True),
        )
        config = TrainingFlowConfig(local_model_dir=str(tmp_path), dry_run=True)
        state = _VertexJobState(resolved_model_prefix="vertex-lgbm-20260702-112242")
        (tmp_path / "vertex-lgbm-20260702-112242_metrics_lgbm.json").write_text("{}")
        results: dict = {"steps": {}}

        _validate_and_promote_stage(config, state, results, MagicMock())

        assert results["validation_passed"] is True
        assert results["validation_mae_passed"] is True

    @pytest.mark.unit
    def test_sets_validation_mae_passed_false_when_validation_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The production failure path: ml-pipeline.yml reads
        validation_mae_passed and must not silently default to True."""
        monkeypatch.setattr(
            training_pipeline,
            "validate_model_performance_task",
            lambda **kwargs: self._validation_result(passed=False),
        )
        config = TrainingFlowConfig(local_model_dir=str(tmp_path), dry_run=True)
        state = _VertexJobState(resolved_model_prefix="vertex-lgbm-20260702-112242")
        (tmp_path / "vertex-lgbm-20260702-112242_metrics_lgbm.json").write_text("{}")
        results: dict = {"steps": {}}

        _validate_and_promote_stage(config, state, results, MagicMock())

        assert results["validation_passed"] is False
        assert results["validation_mae_passed"] is False

    @pytest.mark.unit
    def test_sets_validation_mae_passed_false_when_metrics_file_missing(
        self, tmp_path: Path
    ) -> None:
        config = TrainingFlowConfig(local_model_dir=str(tmp_path), dry_run=True)
        state = _VertexJobState(resolved_model_prefix="vertex-lgbm-20260702-112242")
        results: dict = {"steps": {}}

        _validate_and_promote_stage(config, state, results, MagicMock())

        assert results["validation_passed"] is False
        assert results["validation_mae_passed"] is False


class TestGenerateEnrichmentStage:
    @pytest.mark.unit
    def test_skips_when_validation_failed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Promotion is validation-gated, so enrichment must not run (and crash
        on missing production-named files) after a failed validation."""
        called: list[str] = []
        monkeypatch.setattr(
            pipeline_tasks,
            "generate_area_statistics_task",
            lambda **kwargs: called.append("area_stats") or {},
        )
        results: dict = {"validation_passed": False, "steps": {}}

        _generate_enrichment_stage(TrainingFlowConfig(), results, MagicMock())

        assert results["steps"]["enrichment"] == {"skipped": True, "reason": "validation_failed"}
        assert called == []

    @pytest.mark.unit
    def test_skips_when_validation_key_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called: list[str] = []
        monkeypatch.setattr(
            pipeline_tasks,
            "generate_area_statistics_task",
            lambda **kwargs: called.append("area_stats") or {},
        )
        results: dict = {"steps": {}}

        _generate_enrichment_stage(TrainingFlowConfig(), results, MagicMock())

        assert results["steps"]["enrichment"] == {"skipped": True, "reason": "validation_failed"}
        assert called == []

    @pytest.mark.unit
    def test_runs_when_validation_passed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called: list[str] = []
        monkeypatch.setattr(
            pipeline_tasks,
            "generate_area_statistics_task",
            lambda **kwargs: called.append("area_stats") or {"records_generated": 1},
        )
        monkeypatch.setattr(
            pipeline_tasks,
            "generate_value_analysis_task",
            lambda **kwargs: called.append("value_analysis") or {"records_generated": 1},
        )
        monkeypatch.setattr(
            pipeline_tasks,
            "upload_enrichment_to_gcs_task",
            lambda **kwargs: called.append("upload") or {"uploaded_files": 1},
        )
        monkeypatch.setattr(training_pipeline, "get_gcs_bucket", lambda: "test-bucket")
        results: dict = {"validation_passed": True, "steps": {}}

        _generate_enrichment_stage(TrainingFlowConfig(), results, MagicMock())

        assert called == ["area_stats", "value_analysis", "upload"]
        assert "enrichment" not in results["steps"]


class TestMaeThresholdSingleSourceOfTruth:
    @pytest.mark.unit
    def test_workflow_yml_gate_matches_default_mae_threshold(self) -> None:
        """ml-pipeline.yml cannot import Python constants, so its inline MAE
        gate must be kept equal to DEFAULT_MAE_THRESHOLD by hand."""
        workflow_path = Path(__file__).parents[3] / ".github" / "workflows" / "ml-pipeline.yml"
        workflow_text = workflow_path.read_text()

        gates = re.findall(r"if mae > (\d+)", workflow_text)

        assert gates, "MAE quality gate not found in ml-pipeline.yml"
        assert [int(gate) for gate in gates] == [DEFAULT_MAE_THRESHOLD]

    @pytest.mark.unit
    def test_production_flow_uses_default_mae_threshold(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict = {}
        monkeypatch.setattr(
            training_pipeline,
            "vertex_training_flow",
            lambda config: captured.update(max_mae=config.max_mae) or {},
        )

        training_pipeline.production_vertex_training_flow.fn(rebuild=False, register=False)

        assert captured["max_mae"] == DEFAULT_MAE_THRESHOLD

    @pytest.mark.unit
    def test_validate_task_default_matches_constant(self) -> None:
        import inspect

        from estate_value_index.pipelines.tasks.training import (
            validate_model_performance_task,
        )

        signature = inspect.signature(validate_model_performance_task.fn)
        assert signature.parameters["max_mae"].default == DEFAULT_MAE_THRESHOLD
