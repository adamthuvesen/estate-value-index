"""Unit tests for pipelines/tasks/sync.py."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from estate_value_index.pipelines.tasks.sync import (
    sync_bigquery_to_local_task,
    sync_local_to_gcs_task,
    verify_sync_task,
)


class TestSyncBigqueryToLocalTask:
    @pytest.mark.unit
    def test_missing_bigquery_config_uses_defaults(self, tmp_path: Path, mocker: Any) -> None:
        mock_client = MagicMock()
        mock_row_1 = MagicMock()
        mock_row_1.items.return_value = [("listing_id", "1"), ("price", 1000000)]
        mock_row_2 = MagicMock()
        mock_row_2.items.return_value = [("listing_id", "2"), ("price", 2000000)]
        mock_client.query.return_value.result.return_value = [mock_row_1, mock_row_2]

        mocker.patch(
            "estate_value_index.pipelines.tasks.sync.get_bq_config",
            return_value=MagicMock(
                client=mock_client,
                full_table_id="project.dataset.table",
            ),
        )

        output_file = tmp_path / "output.jsonl"
        result = sync_bigquery_to_local_task.fn(output_file=output_file)

        assert result["success"] is True
        assert result["records_synced"] == 2
        assert output_file.exists()

    @pytest.mark.unit
    def test_writes_jsonl_format(self, tmp_path: Path, mocker: Any) -> None:
        mock_client = MagicMock()
        mock_row = MagicMock()
        mock_row.items.return_value = [("listing_id", "123"), ("area", "Södermalm")]
        mock_client.query.return_value.result.return_value = [mock_row]

        mocker.patch(
            "estate_value_index.pipelines.tasks.sync.get_bq_config",
            return_value=MagicMock(
                client=mock_client,
                full_table_id="project.dataset.table",
            ),
        )

        output_file = tmp_path / "output.jsonl"
        sync_bigquery_to_local_task.fn(output_file=output_file)

        with open(output_file, encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]

        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["listing_id"] == "123"
        assert parsed["area"] == "Södermalm"

    @pytest.mark.unit
    def test_converts_datetime_to_isoformat(self, tmp_path: Path, mocker: Any) -> None:
        mock_client = MagicMock()
        mock_row = MagicMock()
        test_datetime = datetime(2024, 1, 15, 10, 30, 0)
        mock_row.items.return_value = [
            ("listing_id", "1"),
            ("sold_date", test_datetime),
        ]
        mock_client.query.return_value.result.return_value = [mock_row]

        mocker.patch(
            "estate_value_index.pipelines.tasks.sync.get_bq_config",
            return_value=MagicMock(
                client=mock_client,
                full_table_id="project.dataset.table",
            ),
        )

        output_file = tmp_path / "output.jsonl"
        sync_bigquery_to_local_task.fn(output_file=output_file)

        with open(output_file, encoding="utf-8") as f:
            data = json.loads(f.readline())

        assert data["sold_date"] == "2024-01-15T10:30:00"

    @pytest.mark.unit
    def test_creates_backup_of_existing_file(self, tmp_path: Path, mocker: Any) -> None:
        mock_client = MagicMock()
        mock_row = MagicMock()
        mock_row.items.return_value = [("listing_id", "new")]
        mock_client.query.return_value.result.return_value = [mock_row]

        mocker.patch(
            "estate_value_index.pipelines.tasks.sync.get_bq_config",
            return_value=MagicMock(
                client=mock_client,
                full_table_id="project.dataset.table",
            ),
        )

        output_file = tmp_path / "output.json"
        output_file.write_text('{"listing_id": "old"}\n')

        sync_bigquery_to_local_task.fn(output_file=output_file, backup_existing=True)

        with open(output_file, encoding="utf-8") as f:
            data = json.loads(f.readline())
        assert data["listing_id"] == "new"

        backup_files = list(tmp_path.glob("output_backup_*.json"))
        assert len(backup_files) == 1

    @pytest.mark.unit
    def test_skips_backup_when_disabled(self, tmp_path: Path, mocker: Any) -> None:
        mock_client = MagicMock()
        mock_row = MagicMock()
        mock_row.items.return_value = [("listing_id", "new")]
        mock_client.query.return_value.result.return_value = [mock_row]

        mocker.patch(
            "estate_value_index.pipelines.tasks.sync.get_bq_config",
            return_value=MagicMock(
                client=mock_client,
                full_table_id="project.dataset.table",
            ),
        )

        output_file = tmp_path / "output.json"
        output_file.write_text('{"listing_id": "old"}\n')

        sync_bigquery_to_local_task.fn(output_file=output_file, backup_existing=False)

        backup_files = list(tmp_path.glob("output_backup_*.json"))
        assert len(backup_files) == 0

    @pytest.mark.unit
    def test_returns_correct_result_structure(self, tmp_path: Path, mocker: Any) -> None:
        mock_client = MagicMock()
        mock_client.query.return_value.result.return_value = []

        mocker.patch(
            "estate_value_index.pipelines.tasks.sync.get_bq_config",
            return_value=MagicMock(
                client=mock_client,
                full_table_id="project.dataset.table",
            ),
        )

        output_file = tmp_path / "output.jsonl"
        result = sync_bigquery_to_local_task.fn(output_file=output_file)

        assert "success" in result
        assert "timestamp" in result
        assert "source" in result
        assert "destination" in result
        assert "records_synced" in result


class TestSyncLocalToGcsTask:
    @pytest.mark.unit
    def test_missing_local_file_raises(self, tmp_path: Path) -> None:
        non_existent = tmp_path / "missing.json"

        with pytest.raises(FileNotFoundError):
            sync_local_to_gcs_task.fn(local_file=non_existent)

    @pytest.mark.unit
    def test_skips_upload_when_gcs_disabled(self, tmp_path: Path, mocker: Any) -> None:
        local_file = tmp_path / "data.json"
        local_file.write_text('{"listing_id": "1"}\n')

        mocker.patch("estate_value_index.utils.gcs.is_gcs_enabled", return_value=False)

        result = sync_local_to_gcs_task.fn(local_file=local_file)

        assert result["success"] is True
        assert result["destination"] == "gcs://disabled"
        assert result["records_synced"] == 0

    @pytest.mark.unit
    def test_uploads_to_gcs_when_enabled(self, tmp_path: Path, mocker: Any) -> None:
        local_file = tmp_path / "data.json"
        local_file.write_text('{"listing_id": "1"}\n{"listing_id": "2"}\n')

        mocker.patch("estate_value_index.utils.gcs.is_gcs_enabled", return_value=True)

        mock_gcs_client = MagicMock()
        mock_gcs_client.upload_file.return_value = "gs://bucket/path/data.json"
        mocker.patch("estate_value_index.utils.gcs.GCSClient", return_value=mock_gcs_client)

        result = sync_local_to_gcs_task.fn(local_file=local_file)

        assert result["success"] is True
        assert "gs://" in result["destination"]
        assert result["records_synced"] == 2

    @pytest.mark.unit
    def test_creates_timestamped_archive(self, tmp_path: Path, mocker: Any) -> None:
        local_file = tmp_path / "data.json"
        local_file.write_text('{"listing_id": "1"}\n')

        mocker.patch("estate_value_index.utils.gcs.is_gcs_enabled", return_value=True)

        mock_gcs_client = MagicMock()
        mock_gcs_client.upload_file.return_value = "gs://bucket/path"
        mocker.patch("estate_value_index.utils.gcs.GCSClient", return_value=mock_gcs_client)

        sync_local_to_gcs_task.fn(local_file=local_file)

        # Main upload + timestamped archive
        assert mock_gcs_client.upload_file.call_count == 2

    @pytest.mark.unit
    def test_counts_records_correctly(self, tmp_path: Path, mocker: Any) -> None:
        local_file = tmp_path / "data.json"
        local_file.write_text('{"id": "1"}\n\n{"id": "2"}\n{"id": "3"}\n\n')

        mocker.patch("estate_value_index.utils.gcs.is_gcs_enabled", return_value=True)

        mock_gcs_client = MagicMock()
        mock_gcs_client.upload_file.return_value = "gs://bucket/path"
        mocker.patch("estate_value_index.utils.gcs.GCSClient", return_value=mock_gcs_client)

        result = sync_local_to_gcs_task.fn(local_file=local_file)

        assert result["records_synced"] == 3


class TestVerifySyncTask:
    @pytest.mark.unit
    def test_files_in_sync(self, tmp_path: Path, mocker: Any) -> None:
        local_file = tmp_path / "data.json"
        local_file.write_text('{"id": "1"}\n{"id": "2"}\n{"id": "3"}\n')

        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([{"count": 3}])
        mock_client.query.return_value.result.return_value = mock_result

        mocker.patch(
            "estate_value_index.pipelines.tasks.sync.get_bq_config",
            return_value=MagicMock(
                client=mock_client,
                full_table_id="project.dataset.table",
            ),
        )

        result = verify_sync_task.fn(local_file=local_file)

        assert result["success"] is True
        assert result["in_sync"] is True
        assert result["local_count"] == 3
        assert result["bigquery_count"] == 3
        assert result["difference"] == 0

    @pytest.mark.unit
    def test_files_out_of_sync(self, tmp_path: Path, mocker: Any) -> None:
        local_file = tmp_path / "data.json"
        local_file.write_text('{"id": "1"}\n{"id": "2"}\n')  # 2 records

        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([{"count": 5}])  # 5 in BigQuery
        mock_client.query.return_value.result.return_value = mock_result

        mocker.patch(
            "estate_value_index.pipelines.tasks.sync.get_bq_config",
            return_value=MagicMock(
                client=mock_client,
                full_table_id="project.dataset.table",
            ),
        )

        result = verify_sync_task.fn(local_file=local_file)

        assert result["in_sync"] is False
        assert result["local_count"] == 2
        assert result["bigquery_count"] == 5
        assert result["difference"] == 3

    @pytest.mark.unit
    def test_missing_local_file_raises(self, tmp_path: Path, mocker: Any) -> None:
        mock_client = MagicMock()
        mocker.patch(
            "estate_value_index.pipelines.tasks.sync.get_bq_config",
            return_value=MagicMock(
                client=mock_client,
                full_table_id="project.dataset.table",
            ),
        )

        non_existent = tmp_path / "missing.json"

        with pytest.raises(FileNotFoundError):
            verify_sync_task.fn(local_file=non_existent)

    @pytest.mark.unit
    def test_empty_local_file(self, tmp_path: Path, mocker: Any) -> None:
        local_file = tmp_path / "empty.json"
        local_file.write_text("")

        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([{"count": 0}])
        mock_client.query.return_value.result.return_value = mock_result

        mocker.patch(
            "estate_value_index.pipelines.tasks.sync.get_bq_config",
            return_value=MagicMock(
                client=mock_client,
                full_table_id="project.dataset.table",
            ),
        )

        result = verify_sync_task.fn(local_file=local_file)

        assert result["in_sync"] is True
        assert result["local_count"] == 0
        assert result["bigquery_count"] == 0

    @pytest.mark.unit
    def test_returns_correct_result_structure(self, tmp_path: Path, mocker: Any) -> None:
        local_file = tmp_path / "data.json"
        local_file.write_text('{"id": "1"}\n')

        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([{"count": 1}])
        mock_client.query.return_value.result.return_value = mock_result

        mocker.patch(
            "estate_value_index.pipelines.tasks.sync.get_bq_config",
            return_value=MagicMock(
                client=mock_client,
                full_table_id="project.dataset.table",
            ),
        )

        result = verify_sync_task.fn(local_file=local_file)

        assert "success" in result
        assert "in_sync" in result
        assert "local_count" in result
        assert "bigquery_count" in result
        assert "difference" in result
        assert "timestamp" in result
