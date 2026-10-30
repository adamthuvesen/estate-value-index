"""Spend and production-write gates refuse without approval and record zero side effects.

Each gate test uses a fake client or a patched ``subprocess.run`` and asserts that a
refused call touches nothing, while an approved call makes the expected call.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest

from estate_value_index.pipelines.tasks import deployment, ingestion, training
from estate_value_index.utils import gcs as gcs_module
from estate_value_index.utils.approval import ApprovalRequired, require_approval


def _completed(stdout: str = "") -> MagicMock:
    return MagicMock(returncode=0, stdout=stdout, stderr="")


@pytest.fixture
def run_process(mocker: Any) -> MagicMock:
    """Patched ``subprocess.run`` that every external process call goes through."""
    return mocker.patch("subprocess.run", return_value=_completed())


def test_require_approval_refuses_with_system_exit() -> None:
    with pytest.raises(SystemExit):
        require_approval("spend money", approved=False)
    require_approval("spend money", approved=True)


def test_refusal_is_not_swallowed_by_except_exception() -> None:
    swallowed = False
    with pytest.raises(ApprovalRequired):
        try:
            require_approval("spend money", approved=False)
        except Exception:
            swallowed = True
    assert not swallowed


# --- Vertex AI ---


def test_vertex_submit_refuses_without_approval(run_process: MagicMock) -> None:
    with pytest.raises(ApprovalRequired):
        training.submit_vertex_training_job()
    assert run_process.call_count == 0


def test_vertex_submit_dry_run_needs_no_approval(run_process: MagicMock) -> None:
    training.submit_vertex_training_job(dry_run=True)
    command = run_process.call_args.args[0]
    assert "--dry-run" in command
    assert "--approved" not in command


def test_vertex_submit_approved_runs_script_and_approves_the_container(
    run_process: MagicMock,
) -> None:
    training.submit_vertex_training_job(approved=True, tune=True)
    command = run_process.call_args.args[0]
    assert command[0].endswith("submit_custom_job.sh")
    assert command[command.index("--") :] == ["--", "--approved", "--tune"]


def test_container_rebuild_refuses_without_approval(run_process: MagicMock) -> None:
    with pytest.raises(ApprovalRequired):
        training.rebuild_container()
    assert run_process.call_count == 0


def test_container_rebuild_approved_runs_build_script(run_process: MagicMock) -> None:
    training.rebuild_container(approved=True)
    assert run_process.call_args.args[0][0].endswith("build_and_push.sh")


def test_model_promotion_refuses_without_approval(run_process: MagicMock) -> None:
    with pytest.raises(ApprovalRequired):
        training.promote_model_to_production("gs://bucket/vertex-ai/models/run-1", "bucket")
    assert run_process.call_count == 0


def test_model_promotion_approved_copies_to_production_path(run_process: MagicMock) -> None:
    training.promote_model_to_production(
        "gs://bucket/vertex-ai/models/run-1", "bucket", approved=True
    )
    destinations = [call.args[0][-1] for call in run_process.call_args_list]
    assert destinations
    assert all(dest.startswith("gs://bucket/models/") for dest in destinations)


def test_model_registration_refuses_without_approval(run_process: MagicMock) -> None:
    with pytest.raises(ApprovalRequired):
        training.register_model_to_vertex("gs://bucket/models/run-1")
    assert run_process.call_count == 0


def test_model_registration_approved_uploads_to_registry(run_process: MagicMock) -> None:
    training.register_model_to_vertex("gs://bucket/models/run-1", approved=True)
    assert run_process.call_args.args[0][:4] == ["gcloud", "ai", "models", "upload"]


# --- Cloud Run ---


def test_cloud_run_deploy_refuses_without_approval(run_process: MagicMock) -> None:
    with pytest.raises(ApprovalRequired):
        deployment.deploy_to_cloud_run("gs://bucket/models", "gs://bucket/derived")
    assert run_process.call_count == 0


def test_cloud_run_deploy_approved_runs_gcloud_deploy(
    run_process: MagicMock, mocker: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
    monkeypatch.setenv("GCS_BUCKET", "bucket")
    mocker.patch("time.sleep")
    deployment.deploy_to_cloud_run(
        "gs://bucket/models", "gs://bucket/derived", validate=False, approved=True
    )
    commands = [call.args[0] for call in run_process.call_args_list]
    assert any(command[:3] == ["gcloud", "run", "deploy"] for command in commands)


def test_cloud_run_rollback_refuses_without_approval(run_process: MagicMock) -> None:
    with pytest.raises(ApprovalRequired):
        deployment.rollback_deployment("rev-1")
    assert run_process.call_count == 0


def test_cloud_run_rollback_approved_moves_traffic(
    run_process: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
    deployment.rollback_deployment("rev-1", approved=True)
    commands = [call.args[0] for call in run_process.call_args_list]
    assert any(
        command[:4] == ["gcloud", "run", "services", "update-traffic"] for command in commands
    )


# --- BigQuery writes ---


@pytest.fixture
def fake_bq(mocker: Any) -> MagicMock:
    client = MagicMock()
    client.insert_rows_json.return_value = []
    mocker.patch.object(ingestion, "get_bq_client", return_value=client)
    return client


def _fake_bq_config(mocker: Any) -> tuple[MagicMock, MagicMock]:
    client = MagicMock()
    client.get_table.return_value.schema = [MagicMock(), MagicMock()]
    client.get_table.return_value.schema[0].name = "listing_id"
    client.get_table.return_value.schema[1].name = "area"
    client.query.return_value._properties = {}
    config = MagicMock(
        client=client,
        full_table_id="test-project.dataset.table",
        project_id="test-project",
        dataset_id="dataset",
        table_id="table",
    )
    get_config = mocker.patch.object(ingestion, "get_bq_config", return_value=config)
    return get_config, client


def test_bigquery_listing_upload_refuses_without_approval(mocker: Any, tmp_path: Path) -> None:
    get_config, client = _fake_bq_config(mocker)
    listings = tmp_path / "listings.jsonl"
    listings.write_text(json.dumps({"listing_id": "1", "area": "Solna"}) + "\n")

    with pytest.raises(ApprovalRequired):
        ingestion.upload_to_bigquery(listings, truncate=True)

    get_config.assert_not_called()
    assert client.mock_calls == []


def test_bigquery_listing_upload_approved_loads_and_merges(mocker: Any, tmp_path: Path) -> None:
    mocker.patch(
        "estate_value_index.ingestion.bigquery_upload.prepare_bq_row", side_effect=lambda row: row
    )
    _, client = _fake_bq_config(mocker)
    listings = tmp_path / "listings.jsonl"
    listings.write_text(json.dumps({"listing_id": "1", "area": "Solna"}) + "\n")

    ingestion.upload_to_bigquery(listings, approved=True)

    client.load_table_from_json.assert_called_once()
    assert "MERGE" in client.query.call_args.args[0]


def test_bigquery_geocode_insert_refuses_without_approval(fake_bq: MagicMock) -> None:
    with pytest.raises(ApprovalRequired):
        ingestion.insert_geocodes("test-project", [{"address": "a"}])
    assert fake_bq.mock_calls == []
    ingestion.get_bq_client.assert_not_called()


def test_bigquery_geocode_insert_approved_inserts_rows(fake_bq: MagicMock) -> None:
    ingestion.insert_geocodes("test-project", [{"address": "a"}], approved=True)
    fake_bq.insert_rows_json.assert_called_once()


def test_geocode_task_refuses_before_any_bigquery_client(fake_bq: MagicMock) -> None:
    with pytest.raises(ApprovalRequired):
        ingestion.geocode_new_addresses_task.fn(rate_limit_delay=0)
    ingestion.get_bq_client.assert_not_called()


# --- GCS uploads ---


class _FakeBucket:
    def __init__(self) -> None:
        self.uploads: list[str] = []

    def blob(self, name: str) -> MagicMock:
        blob = MagicMock()
        blob.upload_from_filename.side_effect = lambda _: self.uploads.append(name)
        return blob


def _fake_gcs_client(monkeypatch: pytest.MonkeyPatch) -> gcs_module.GCSClient:
    monkeypatch.setattr(gcs_module, "is_gcs_enabled", lambda: True)
    monkeypatch.setattr(gcs_module, "get_gcs_bucket", lambda: "bucket")
    monkeypatch.setattr(
        "estate_value_index.utils.clients.get_storage_client",
        lambda: MagicMock(bucket=lambda name: _FakeBucket()),
    )
    return gcs_module.GCSClient()


def test_gcs_upload_file_refuses_without_approval(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _fake_gcs_client(monkeypatch)
    artifact = tmp_path / "model.joblib"
    artifact.write_bytes(b"x")

    with pytest.raises(ApprovalRequired):
        client.upload_file(artifact, "models/model.joblib")
    assert client._bucket.uploads == []

    client.upload_file(artifact, "models/model.joblib", approved=True)
    assert client._bucket.uploads == ["models/model.joblib"]


def test_model_artifact_upload_refuses_before_constructing_a_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(gcs_module, "is_gcs_enabled", lambda: True)
    constructed = MagicMock()
    monkeypatch.setattr(gcs_module, "GCSClient", constructed)

    with pytest.raises(ApprovalRequired):
        gcs_module.upload_model_artifacts(tmp_path, "model")
    constructed.assert_not_called()


def test_training_with_gcs_enabled_refuses_before_training(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from estate_value_index.ml import production_models

    monkeypatch.setattr(production_models, "is_gcs_enabled", lambda: True)
    with pytest.raises(ApprovalRequired):
        production_models.train_and_persist_production_models(
            raw_frame=pd.DataFrame(), model_dir=tmp_path / "models"
        )
    assert not (tmp_path / "models").exists()


def test_enrichment_upload_refuses_before_constructing_a_client(
    mocker: Any, tmp_path: Path
) -> None:
    from estate_value_index.pipelines.tasks import analytics

    storage = mocker.patch.object(analytics, "get_storage_client")
    (tmp_path / "stats.json").write_text("{}")

    with pytest.raises(ApprovalRequired):
        analytics.upload_enrichment_to_gcs_task.fn(tmp_path, "bucket")
    storage.assert_not_called()
