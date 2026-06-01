"""Contract tests for fix-prefect-flow-signatures (C5, C6).

Validates that every keyword argument the codebase passes to
`complete_pipeline_flow` (drift-triggered retraining) and the deployment
parameter dict for `vertex_training_flow` (scheduled monthly training)
matches the actual flow signature. The bug surfaced because Prefect only
validates parameter names at run time, so a stale call site silently
breaks scheduled runs.
"""

from __future__ import annotations

import inspect

import pytest

prefect = pytest.importorskip("prefect")

from estate_value_index.pipelines import deploy_flows
from estate_value_index.pipelines.core.complete_pipeline import complete_pipeline_flow
from estate_value_index.pipelines.core.training_pipeline import (
    vertex_training_flow as train_model_flow,
)
from estate_value_index.pipelines.tasks.monitoring import _DRIFT_RETRAIN_KWARGS


def _flow_param_names(flow) -> set[str]:
    fn = getattr(flow, "fn", flow)
    return set(inspect.signature(fn).parameters)


def test_drift_retrain_kwargs_match_complete_pipeline_signature():
    valid = _flow_param_names(complete_pipeline_flow)
    invalid = set(_DRIFT_RETRAIN_KWARGS) - valid
    assert not invalid, (
        f"Drift-retrain passes kwargs not present on complete_pipeline_flow: {sorted(invalid)}"
    )


def test_train_deployment_parameters_match_vertex_training_flow():
    valid = _flow_param_names(train_model_flow)
    parameters = deploy_flows.TRAIN_DEPLOYMENT_PARAMETERS
    invalid = set(parameters) - valid
    assert not invalid, (
        f"train_deployment passes parameter keys not present on vertex_training_flow: "
        f"{sorted(invalid)}"
    )
