"""Contract tests for fix-prefect-flow-signatures (C5, C6).

Validates that the deployment parameter dicts for `vertex_training_flow`
(scheduled monthly training) and the ingestion flow match their flow
signatures. The bug surfaced because Prefect only validates parameter names
at run time, so a stale call site silently breaks scheduled runs.
"""

from __future__ import annotations

import inspect

import pytest

prefect = pytest.importorskip("prefect")

from estate_value_index.pipelines import deploy_flows
from estate_value_index.pipelines.core.data_pipeline import ingest_booli_flow
from estate_value_index.pipelines.core.training_pipeline import (
    vertex_training_flow as train_model_flow,
)


def _flow_param_names(flow) -> set[str]:
    fn = getattr(flow, "fn", flow)
    return set(inspect.signature(fn).parameters)


def test_train_deployment_parameters_match_vertex_training_flow():
    valid = _flow_param_names(train_model_flow)
    parameters = deploy_flows.TRAIN_DEPLOYMENT_PARAMETERS
    invalid = set(parameters) - valid
    assert not invalid, (
        f"train_deployment passes parameter keys not present on vertex_training_flow: "
        f"{sorted(invalid)}"
    )


def test_ingestion_deployment_parameters_match_ingestion_flow():
    valid = _flow_param_names(ingest_booli_flow)
    invalid = set(deploy_flows.INGESTION_DEPLOYMENT_PARAMETERS) - valid
    assert not invalid, (
        f"ingestion deployment passes parameter keys not present on ingest_booli_flow: "
        f"{sorted(invalid)}"
    )
