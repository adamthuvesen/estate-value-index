from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from estate_value_index.exceptions import DataError
from estate_value_index.ingestion import sync


def _client_with_rows(rows: list[dict[str, Any]]) -> MagicMock:
    client = MagicMock()
    client.query.return_value.result.return_value = [MagicMock(items=row.items) for row in rows]
    return client


def test_sync_writes_iso_jsonl_and_backs_up_the_old_file(tmp_path: Path, mocker: Any) -> None:
    client = _client_with_rows(
        [{"listing_id": "1", "area": "Södermalm", "sold_date": datetime(2026, 1, 2, 3, 4)}]
    )
    mocker.patch.object(sync, "get_bq_client", return_value=client)
    output = tmp_path / "prod.json"
    output.write_text('{"listing_id": "old"}\n')

    assert sync.sync_bigquery_to_local(output) == 1

    assert json.loads(output.read_text()) == {
        "listing_id": "1",
        "area": "Södermalm",
        "sold_date": "2026-01-02T03:04:00",
    }
    assert len(list(tmp_path.glob("prod_backup_*.json"))) == 1


def _summary_client(ids: list[str]) -> MagicMock:
    client = MagicMock()
    client.query.return_value.result.return_value = [
        {
            "count": len(ids),
            "listing_id_count": len(set(ids)),
            "listing_id_checksum": sync._listing_id_checksum(ids),
            "max_record_date": "2026-01-02",
        }
    ]
    return client


def test_verify_sync_passes_on_the_same_listing_set(tmp_path: Path, mocker: Any) -> None:
    local = tmp_path / "prod.json"
    local.write_text(
        '{"listing_id": "1", "sold_date": "2026-01-01"}\n'
        '{"listing_id": "2", "sold_date": "2026-01-02"}\n'
    )
    mocker.patch.object(sync, "get_bq_client", return_value=_summary_client(["1", "2"]))

    assert sync.verify_sync(local)["count"] == 2


def test_verify_sync_fails_on_same_count_different_ids(tmp_path: Path, mocker: Any) -> None:
    local = tmp_path / "prod.json"
    local.write_text(
        '{"listing_id": "1", "sold_date": "2026-01-01"}\n'
        '{"listing_id": "2", "sold_date": "2026-01-02"}\n'
    )
    mocker.patch.object(sync, "get_bq_client", return_value=_summary_client(["1", "3"]))

    with pytest.raises(DataError, match="out of sync"):
        sync.verify_sync(local)


def test_backup_is_a_no_op_when_gcs_is_disabled(tmp_path: Path, mocker: Any) -> None:
    mocker.patch.object(sync, "is_gcs_enabled", return_value=False)
    local = tmp_path / "prod.json"
    local.write_text("{}\n")

    assert sync.backup_listings_to_gcs(local) == []
