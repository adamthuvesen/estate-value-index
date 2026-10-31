"""Spend and production-write gates refuse without approval and record zero side effects.

Each gate test uses a fake client or a patched ``subprocess.run`` and asserts that a
refused call touches nothing, while an approved call makes the expected call.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest

from estate_value_index.analytics import publish
from estate_value_index.cli import sync_listings, vertex_train
from estate_value_index.exceptions import InfrastructureError
from estate_value_index.ingestion import bigquery_upload, geocoding, ingest, sync
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


@pytest.fixture
def vertex_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
    monkeypatch.setenv("GCS_BUCKET", "bucket")


def _vertex_job(state: str) -> str:
    return json.dumps(
        {
            "name": "projects/test-project/locations/europe-north1/customJobs/123",
            "state": state,
            "jobSpec": {
                "workerPoolSpecs": [
                    {
                        "containerSpec": {
                            "env": [
                                {
                                    "name": "MODEL_ARTIFACTS_URI",
                                    "value": "gs://bucket/vertex-ai/models/run-1",
                                }
                            ]
                        }
                    }
                ]
            },
        }
    )


def test_vertex_train_refuses_without_approval(run_process: MagicMock, vertex_env: None) -> None:
    with pytest.raises(ApprovalRequired):
        vertex_train.main([])
    assert run_process.call_count == 0


def test_vertex_train_dry_run_starts_no_process(
    run_process: MagicMock, vertex_env: None, capsys: pytest.CaptureFixture[str]
) -> None:
    assert vertex_train.main(["--dry-run", "--tune"]) == 0
    assert run_process.call_count == 0
    spec = json.loads(capsys.readouterr().out)
    assert spec["workerPoolSpecs"][0]["containerSpec"]["args"][-1] == "--tune"


def test_vertex_train_approved_reads_ids_from_the_json_response(
    run_process: MagicMock, vertex_env: None, mocker: Any, tmp_path: Path
) -> None:
    run_process.side_effect = [
        _completed(_vertex_job("JOB_STATE_PENDING")),
        _completed(_vertex_job("JOB_STATE_SUCCEEDED")),
    ]
    download = mocker.patch.object(vertex_train, "download_model_artifacts")

    assert (
        vertex_train.main(["--approved", "--poll-seconds", "0", "--model-dir", str(tmp_path)]) == 0
    )

    create, describe = (call.args[0] for call in run_process.call_args_list)
    assert create[:4] == ["gcloud", "ai", "custom-jobs", "create"]
    assert create[-1] == "--format=json"
    assert describe[4] == "projects/test-project/locations/europe-north1/customJobs/123"
    assert download.call_args.args[0] == "gs://bucket/vertex-ai/models/run-1"


def test_vertex_train_fails_loudly_when_the_job_fails(
    run_process: MagicMock, vertex_env: None, mocker: Any
) -> None:
    run_process.side_effect = [
        _completed(_vertex_job("JOB_STATE_PENDING")),
        _completed(_vertex_job("JOB_STATE_FAILED")),
    ]
    download = mocker.patch.object(vertex_train, "download_model_artifacts")

    with pytest.raises(InfrastructureError, match="JOB_STATE_FAILED"):
        vertex_train.main(["--approved", "--poll-seconds", "0"])
    download.assert_not_called()


def test_vertex_train_rejects_a_response_without_a_job_name(
    run_process: MagicMock, vertex_env: None
) -> None:
    run_process.return_value = _completed(json.dumps({"state": "JOB_STATE_PENDING"}))
    with pytest.raises(InfrastructureError, match="custom job name"):
        vertex_train.main(["--approved", "--poll-seconds", "0"])


# --- Model promotion ---


@pytest.fixture
def fake_storage(mocker: Any) -> MagicMock:
    client = MagicMock()
    mocker.patch("estate_value_index.utils.clients.get_storage_client", return_value=client)
    mocker.patch("estate_value_index.analytics.publish.get_storage_client", return_value=client)
    return client


def test_model_promotion_refuses_without_approval(fake_storage: MagicMock) -> None:
    with pytest.raises(ApprovalRequired):
        gcs_module.promote_model_artifacts("gs://bucket/vertex-ai/models/run-1", ("a.joblib",))
    assert fake_storage.mock_calls == []


def test_model_promotion_approved_copies_to_production_path(fake_storage: MagicMock) -> None:
    promoted = gcs_module.promote_model_artifacts(
        "gs://bucket/vertex-ai/models/run-1", ("a.joblib", "a.joblib.sha256"), approved=True
    )
    assert promoted == ["gs://bucket/models/a.joblib", "gs://bucket/models/a.joblib.sha256"]
    assert fake_storage.bucket.return_value.copy_blob.call_count == 2


# --- BigQuery writes ---


@pytest.fixture
def fake_bq(mocker: Any) -> MagicMock:
    client = MagicMock()
    client.insert_rows_json.return_value = []
    client.get_table.return_value.schema = [MagicMock(), MagicMock()]
    client.get_table.return_value.schema[0].name = "listing_id"
    client.get_table.return_value.schema[1].name = "area"
    client.query.return_value._properties = {}
    client.query.return_value.to_dataframe.return_value = pd.DataFrame()
    for module in (bigquery_upload, geocoding):
        mocker.patch.object(module, "get_bq_client", return_value=client)
    return client


def _listings_file(tmp_path: Path) -> Path:
    listings = tmp_path / "listings.jsonl"
    listings.write_text(json.dumps({"listing_id": "1", "area": "Solna"}) + "\n")
    return listings


def test_bigquery_listing_upload_refuses_without_approval(
    fake_bq: MagicMock, tmp_path: Path
) -> None:
    with pytest.raises(ApprovalRequired):
        bigquery_upload.upload_to_bigquery(_listings_file(tmp_path), truncate=True)
    assert fake_bq.mock_calls == []


def test_bigquery_listing_upload_approved_loads_and_merges(
    fake_bq: MagicMock, tmp_path: Path
) -> None:
    bigquery_upload.upload_to_bigquery(_listings_file(tmp_path), approved=True)

    fake_bq.load_table_from_json.assert_called_once()
    assert "MERGE" in fake_bq.query.call_args.args[0]


def test_bigquery_geocode_insert_refuses_without_approval(fake_bq: MagicMock) -> None:
    with pytest.raises(ApprovalRequired):
        geocoding.insert_geocodes("test-project", [{"address": "a"}])
    assert fake_bq.mock_calls == []


def test_bigquery_geocode_insert_approved_inserts_rows(fake_bq: MagicMock) -> None:
    geocoding.insert_geocodes("test-project", [{"address": "a"}], approved=True)
    fake_bq.insert_rows_json.assert_called_once()


def test_geocoding_refuses_before_any_bigquery_client(fake_bq: MagicMock) -> None:
    with pytest.raises(ApprovalRequired):
        geocoding.geocode_new_addresses(rate_limit_delay=0)
    assert fake_bq.mock_calls == []


def test_ingest_with_load_refuses_before_fetching(tmp_path: Path) -> None:
    fetch = MagicMock()
    with pytest.raises(ApprovalRequired):
        ingest.ingest_listings(
            base_config_file=tmp_path / "config.json",
            output_dir=tmp_path,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 7),
            window_days=7,
            max_pages=1,
            dry_run=False,
            load=True,
            fetch=fetch,
        )
    fetch.assert_not_called()


# --- GCS uploads ---


class _FakeBucket:
    def __init__(self) -> None:
        self.uploads: list[str] = []

    def blob(self, name: str) -> MagicMock:
        blob = MagicMock()
        blob.upload_from_filename.side_effect = lambda _: self.uploads.append(name)
        return blob


def _fake_gcs_client(monkeypatch: pytest.MonkeyPatch) -> tuple[gcs_module.GCSClient, _FakeBucket]:
    bucket = _FakeBucket()
    monkeypatch.setattr(gcs_module, "is_gcs_enabled", lambda: True)
    monkeypatch.setattr(gcs_module, "get_gcs_bucket", lambda: "bucket")
    monkeypatch.setattr(
        "estate_value_index.utils.clients.get_storage_client",
        lambda: MagicMock(bucket=lambda name: bucket),
    )
    return gcs_module.GCSClient(), bucket


def test_gcs_upload_file_refuses_without_approval(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, bucket = _fake_gcs_client(monkeypatch)
    artifact = tmp_path / "model.joblib"
    artifact.write_bytes(b"x")

    with pytest.raises(ApprovalRequired):
        client.upload_file(artifact, "models/model.joblib")
    assert bucket.uploads == []

    client.upload_file(artifact, "models/model.joblib", approved=True)
    assert bucket.uploads == ["models/model.joblib"]


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
    fake_storage: MagicMock, tmp_path: Path
) -> None:
    (tmp_path / "stats.json").write_text("{}")

    with pytest.raises(ApprovalRequired):
        publish.upload_enrichment_to_gcs(tmp_path, "bucket")
    assert fake_storage.mock_calls == []

    uris = publish.upload_enrichment_to_gcs(tmp_path, "bucket", approved=True)
    assert uris == ["gs://bucket/derived/stats.json"]


def test_listings_backup_refuses_without_approval(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, bucket = _fake_gcs_client(monkeypatch)
    monkeypatch.setattr(sync, "is_gcs_enabled", lambda: True)
    monkeypatch.setattr(sync, "GCSClient", lambda: client)
    listings = _listings_file(tmp_path)

    with pytest.raises(ApprovalRequired):
        sync.backup_listings_to_gcs(listings)
    assert bucket.uploads == []


def test_sync_command_refuses_before_reading_bigquery_when_gcs_is_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    read_bigquery = MagicMock()
    monkeypatch.setattr(sync_listings, "is_gcs_enabled", lambda: True)
    monkeypatch.setattr(sync_listings, "sync_bigquery_to_local", read_bigquery)

    with pytest.raises(ApprovalRequired):
        sync_listings.main(["--output", str(tmp_path / "listings.jsonl")])
    read_bigquery.assert_not_called()
