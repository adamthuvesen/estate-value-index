from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

from estate_value_index.pipelines.core import complete_pipeline as pipeline


def test_data_collection_stage_uses_empty_config_and_dry_run_flags(monkeypatch):
    calls = {}

    def fake_complete_scrape_flow(**kwargs):
        calls.update(kwargs)
        return {
            "scraping": {"validation": {"valid_listings": 12}},
            "processing": {"total_listings": 10},
            "bigquery": {},
            "features": {},
        }

    monkeypatch.setattr(pipeline, "complete_scrape_flow", fake_complete_scrape_flow)
    results = {"stages": {}}

    pipeline._run_data_collection_stage(
        MagicMock(),
        results,
        max_pages=3,
        skip_scraping=False,
        config_file=None,
        dry_run=True,
    )

    assert calls == {
        "max_pages": 3,
        "upload_to_bq": False,
        "materialize_features": False,
        "upload_to_cloud": False,
        "config_file": "",
    }
    assert results["stages"]["data_collection"]["processing"]["total_listings"] == 10


def test_sync_stage_records_failure_and_raises(monkeypatch):
    def fail_sync():
        raise RuntimeError("sync exploded")

    monkeypatch.setattr(pipeline, "sync_bigquery_to_local_task", fail_sync)
    results = {"stages": {}}

    try:
        pipeline._run_sync_stage(MagicMock(), results, dry_run=False)
    except RuntimeError as exc:
        assert str(exc) == "sync exploded"
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("sync failure should raise")

    assert results["stages"]["sync"] == {"error": "sync exploded", "success": False}


def test_training_config_matches_vertex_and_local_modes():
    vertex_config = pipeline._training_config(
        tune=True,
        use_vertex=True,
        machine_type="n1-highmem-8",
        rebuild_container=True,
        skip_scraping=False,
        dry_run=True,
    )

    assert vertex_config.tune is True
    assert vertex_config.use_vertex is True
    assert vertex_config.machine_type == "n1-highmem-8"
    assert vertex_config.rebuild_container is True
    assert vertex_config.skip_materialization is True
    assert vertex_config.register_to_vertex is False
    assert vertex_config.stream_logs is True
    assert vertex_config.production_mode is True
    assert vertex_config.dry_run is True

    local_config = pipeline._training_config(
        tune=True,
        use_vertex=False,
        machine_type="ignored",
        rebuild_container=True,
        skip_scraping=True,
        dry_run=True,
    )

    assert local_config.tune is True
    assert local_config.use_vertex is False
    assert local_config.production_mode is True
    assert local_config.skip_materialization is False
    assert local_config.dry_run is False


def test_deployment_skip_reasons_preserve_order():
    reasons = pipeline._deployment_skip_reasons(
        deploy_to_prod=False,
        validation_passed=False,
        dry_run=True,
    )

    assert reasons == ["deploy_to_prod=False", "validation_failed", "dry_run=True"]


def test_deployment_stage_uses_training_uri_or_bucket_fallback(monkeypatch):
    calls = {}

    def fake_deploy_to_cloud_run_task(**kwargs):
        calls.update(kwargs)
        return {"success": True, "service_url": "https://example.test", "revision": "rev-2"}

    monkeypatch.setattr(pipeline, "get_gcs_bucket", lambda: "model-bucket")
    monkeypatch.setattr(pipeline, "deploy_to_cloud_run_task", fake_deploy_to_cloud_run_task)
    results = {"stages": {}}
    logger = MagicMock()

    pipeline._run_deployment_stage(
        logger,
        results,
        {"steps": {"download_artifacts": {}}},
        deploy_to_prod=True,
        validation_passed=True,
        dry_run=False,
        validate_deployment=False,
    )

    assert calls == {
        "model_artifacts_gcs_uri": "gs://model-bucket/models/",
        "enrichment_gcs_uri": "gs://model-bucket/derived/",
        "validate": False,
    }
    assert results["stages"]["deployment"] == {
        "success": True,
        "service_url": "https://example.test",
        "revision": "rev-2",
    }
    # `deployed=` has one source of truth (the pipeline summary); the stage log
    # reports the real DeploymentResult fields instead.
    stage_logs = [str(call.args[0]) for call in logger.info.call_args_list]
    assert not any("deployed=" in message for message in stage_logs)
    assert any(
        "url=https://example.test" in message and "revision=rev-2" in message
        for message in stage_logs
    )


def test_deployment_succeeded_reads_the_recorded_stage():
    assert pipeline._deployment_succeeded({"stages": {}}) is False
    assert (
        pipeline._deployment_succeeded(
            {"stages": {"deployment": {"skipped": True, "reasons": ["dry_run=True"]}}}
        )
        is False
    )
    assert (
        pipeline._deployment_succeeded(
            {"stages": {"deployment": {"success": True, "service_url": "u", "revision": "r"}}}
        )
        is True
    )


def test_pipeline_summary_reports_deployed_from_deployment_stage():
    logger = MagicMock()
    results = {
        "stages": {"deployment": {"success": True, "service_url": "u", "revision": "r"}},
    }

    pipeline._record_pipeline_success(
        logger,
        results,
        start_time=datetime.now(),
        validation_passed=True,
        mae=250_000,
    )

    summary = logger.info.call_args[0][0]
    assert "deployed=True" in summary


def test_pipeline_summary_reports_deployed_false_when_stage_skipped():
    logger = MagicMock()
    results = {
        "stages": {"deployment": {"skipped": True, "reasons": ["deploy_to_prod=False"]}},
    }

    pipeline._record_pipeline_success(
        logger,
        results,
        start_time=datetime.now(),
        validation_passed=True,
        mae=250_000,
    )

    summary = logger.info.call_args[0][0]
    assert "deployed=False" in summary
