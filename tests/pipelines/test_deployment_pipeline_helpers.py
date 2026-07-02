from __future__ import annotations

from unittest.mock import MagicMock

from estate_value_index.pipelines.core import deployment_pipeline as pipeline
from estate_value_index.pipelines.utils import DeploymentFlowConfig


def _run_flow(monkeypatch, *, dry_run: bool) -> MagicMock:
    """Run deployment_pipeline_flow.fn with mocked logger and deploy task."""
    logger = MagicMock()
    monkeypatch.setattr(pipeline, "get_run_logger", lambda: logger)
    monkeypatch.setattr(pipeline, "get_gcs_bucket", lambda: "model-bucket")
    monkeypatch.setattr(
        pipeline,
        "deploy_to_cloud_run_task",
        lambda **_: {
            "success": True,
            "timestamp": "2026-07-02T00:00:00",
            "service_url": "https://app-abc.run.app" if not dry_run else None,
            "revision": "rev-2" if not dry_run else None,
        },
    )

    pipeline.deployment_pipeline_flow.fn(DeploymentFlowConfig(validate=False, dry_run=dry_run))
    return logger


def test_dry_run_reports_as_dry_run_not_deployed(monkeypatch):
    logger = _run_flow(monkeypatch, dry_run=True)

    messages = [str(call.args[0]) for call in logger.info.call_args_list]
    assert any("Dry run complete" in m for m in messages)
    assert not any("Deployment successful" in m for m in messages)


def test_real_deploy_reports_as_successful(monkeypatch):
    logger = _run_flow(monkeypatch, dry_run=False)

    messages = [str(call.args[0]) for call in logger.info.call_args_list]
    assert any("Deployment successful" in m for m in messages)
    assert not any("Dry run complete" in m for m in messages)
