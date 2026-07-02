from __future__ import annotations

from unittest.mock import MagicMock

from estate_value_index.pipelines.core import deployment_pipeline as pipeline
from estate_value_index.pipelines.utils import DeploymentFlowConfig


def _run_flow(
    monkeypatch,
    *,
    dry_run: bool = False,
    healthy: bool | None = None,
    previous_revision: str | None = None,
    auto_rollback: bool = False,
) -> tuple[MagicMock, MagicMock]:
    """Run deployment_pipeline_flow.fn with mocked logger, deploy, and rollback tasks."""
    logger = MagicMock()
    rollback = MagicMock(return_value={"success": True, "to_revision": previous_revision})
    monkeypatch.setattr(pipeline, "get_run_logger", lambda: logger)
    monkeypatch.setattr(pipeline, "get_gcs_bucket", lambda: "model-bucket")
    monkeypatch.setattr(pipeline, "rollback_deployment_task", rollback)
    monkeypatch.setattr(
        pipeline,
        "deploy_to_cloud_run_task",
        lambda **_: {
            "success": True,
            "timestamp": "2026-07-02T00:00:00",
            "service_url": "https://app-abc.run.app" if not dry_run else None,
            "revision": "rev-2" if not dry_run else None,
            "previous_revision": previous_revision,
            "healthy": healthy,
        },
    )

    pipeline.deployment_pipeline_flow.fn(
        DeploymentFlowConfig(
            validate=False, dry_run=dry_run, auto_rollback_on_failure=auto_rollback
        )
    )
    return logger, rollback


def test_dry_run_reports_as_dry_run_not_deployed(monkeypatch):
    logger, _ = _run_flow(monkeypatch, dry_run=True)

    messages = [str(call.args[0]) for call in logger.info.call_args_list]
    assert any("Dry run complete" in m for m in messages)
    assert not any("Deployment successful" in m for m in messages)


def test_real_deploy_reports_as_successful(monkeypatch):
    logger, _ = _run_flow(monkeypatch, dry_run=False)

    messages = [str(call.args[0]) for call in logger.info.call_args_list]
    assert any("Deployment successful" in m for m in messages)
    assert not any("Dry run complete" in m for m in messages)


def test_unhealthy_deploy_with_auto_rollback_rolls_back(monkeypatch):
    logger, rollback = _run_flow(
        monkeypatch, healthy=False, previous_revision="rev-1", auto_rollback=True
    )

    rollback.assert_called_once()
    assert rollback.call_args.kwargs["previous_revision"] == "rev-1"
    messages = [str(call.args[0]) for call in logger.info.call_args_list]
    assert any("Deployment rolled back" in m for m in messages)


def test_unhealthy_deploy_without_auto_rollback_does_not_roll_back(monkeypatch):
    logger, rollback = _run_flow(
        monkeypatch, healthy=False, previous_revision="rev-1", auto_rollback=False
    )

    rollback.assert_not_called()
    warnings = [str(call.args[0]) for call in logger.warning.call_args_list]
    assert any("completed with warnings" in m for m in warnings)


def test_unhealthy_deploy_without_previous_revision_warns(monkeypatch):
    logger, rollback = _run_flow(
        monkeypatch, healthy=False, previous_revision=None, auto_rollback=True
    )

    rollback.assert_not_called()
    warnings = [str(call.args[0]) for call in logger.warning.call_args_list]
    assert any("No previous revision" in m for m in warnings)


def test_healthy_deploy_does_not_roll_back(monkeypatch):
    _, rollback = _run_flow(
        monkeypatch, healthy=True, previous_revision="rev-1", auto_rollback=True
    )

    rollback.assert_not_called()


def test_skipped_validation_counts_as_healthy(monkeypatch):
    logger, rollback = _run_flow(
        monkeypatch, healthy=None, previous_revision="rev-1", auto_rollback=True
    )

    rollback.assert_not_called()
    messages = [str(call.args[0]) for call in logger.info.call_args_list]
    assert any("Deployment successful" in m for m in messages)
