"""Unit tests for the Vertex training flow helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from estate_value_index.pipelines.core.training_pipeline import (
    _artifact_locations_from_job_info,
    _resolve_artifacts_from_job_info,
    _VertexJobState,
)


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
