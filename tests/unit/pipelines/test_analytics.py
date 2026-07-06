"""Unit tests for pipelines/tasks/analytics.py."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from estate_value_index.pipelines.tasks.analytics import (
    generate_area_statistics_task,
    generate_value_analysis_task,
    upload_enrichment_to_gcs_task,
)


def _mock_gcs_storage(mocker: Any) -> MagicMock:
    """Common GCS storage mock pattern used across tests."""
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()
    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob
    mocker.patch(
        "estate_value_index.pipelines.tasks.analytics.get_storage_client",
        return_value=mock_client,
    )
    return mock_bucket


class TestGenerateAreaStatisticsTask:
    @pytest.mark.unit
    def test_creates_output_directory(self, tmp_path: Path, mocker: Any) -> None:
        output_file = tmp_path / "nested" / "stats" / "area_stats.json"

        def mock_generate(*args, **kwargs):
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text('{"areas": [{"name": "Södermalm"}]}')

        mocker.patch(
            "estate_value_index.analytics.area_statistics.generate_area_statistics",
            side_effect=mock_generate,
        )

        result = generate_area_statistics_task.fn(output_file=output_file)

        assert result["success"] is True
        assert output_file.exists()

    @pytest.mark.unit
    def test_counts_areas_correctly(self, tmp_path: Path, mocker: Any) -> None:
        output_file = tmp_path / "area_stats.json"

        def mock_generate(*args, **kwargs):
            output_file.write_text(
                json.dumps(
                    {
                        "areas": [
                            {"name": "Södermalm"},
                            {"name": "Östermalm"},
                            {"name": "Vasastan"},
                        ]
                    }
                )
            )

        mocker.patch(
            "estate_value_index.analytics.area_statistics.generate_area_statistics",
            side_effect=mock_generate,
        )

        result = generate_area_statistics_task.fn(output_file=output_file)
        assert result["records_generated"] == 3

    @pytest.mark.unit
    def test_raises_if_output_not_created(self, tmp_path: Path, mocker: Any) -> None:
        output_file = tmp_path / "stats.json"

        mocker.patch(
            "estate_value_index.analytics.area_statistics.generate_area_statistics",
            return_value=None,
        )

        with pytest.raises(FileNotFoundError, match="Output file not created"):
            generate_area_statistics_task.fn(output_file=output_file)

    @pytest.mark.unit
    def test_returns_correct_structure(self, tmp_path: Path, mocker: Any) -> None:
        output_file = tmp_path / "stats.json"

        def mock_generate(*args, **kwargs):
            output_file.write_text('{"areas": []}')

        mocker.patch(
            "estate_value_index.analytics.area_statistics.generate_area_statistics",
            side_effect=mock_generate,
        )

        result = generate_area_statistics_task.fn(output_file=output_file)

        assert "success" in result
        assert "timestamp" in result
        assert "output_file" in result
        assert "records_generated" in result

    @pytest.mark.unit
    def test_passes_data_source_parameter(self, tmp_path: Path, mocker: Any) -> None:
        output_file = tmp_path / "stats.json"
        captured_args = {}

        def mock_generate(*args, **kwargs):
            captured_args.update(kwargs)
            output_file.write_text('{"areas": []}')

        mocker.patch(
            "estate_value_index.analytics.area_statistics.generate_area_statistics",
            side_effect=mock_generate,
        )

        generate_area_statistics_task.fn(output_file=output_file, data_source="json")
        assert captured_args["data_source"] == "json"


class TestGenerateValueAnalysisTask:
    @pytest.mark.unit
    def test_creates_output_directory(self, tmp_path: Path, mocker: Any) -> None:
        output_file = tmp_path / "nested" / "analysis" / "value.json"
        data_file = tmp_path / "data.json"
        data_file.write_text('{"listing_id": "1"}\n')

        def mock_generate_value_analysis(*args, **kwargs):
            kwargs["output_file"].parent.mkdir(parents=True, exist_ok=True)
            kwargs["output_file"].write_text('{"statistics": {"total_properties": 10}}')

        mocker.patch(
            "estate_value_index.analytics.value_analysis.generate_value_analysis",
            side_effect=mock_generate_value_analysis,
        )

        result = generate_value_analysis_task.fn(output_file=output_file, data_file=data_file)

        assert result["success"] is True
        assert output_file.exists()

    @pytest.mark.unit
    def test_counts_properties_correctly(self, tmp_path: Path, mocker: Any) -> None:
        output_file = tmp_path / "analysis.json"
        data_file = tmp_path / "data.json"
        data_file.write_text('{"listing_id": "1"}\n')

        def mock_generate_value_analysis(*args, **kwargs):
            kwargs["output_file"].write_text(json.dumps({"statistics": {"total_properties": 150}}))

        mocker.patch(
            "estate_value_index.analytics.value_analysis.generate_value_analysis",
            side_effect=mock_generate_value_analysis,
        )

        result = generate_value_analysis_task.fn(output_file=output_file, data_file=data_file)
        assert result["records_generated"] == 150

    @pytest.mark.unit
    def test_raises_if_output_not_created(self, tmp_path: Path, mocker: Any) -> None:
        output_file = tmp_path / "analysis.json"
        data_file = tmp_path / "data.json"
        data_file.write_text('{"listing_id": "1"}\n')

        mocker.patch("estate_value_index.analytics.value_analysis.generate_value_analysis", return_value=None)

        with pytest.raises(FileNotFoundError, match="Output file not created"):
            generate_value_analysis_task.fn(output_file=output_file, data_file=data_file)

    @pytest.mark.unit
    def test_passes_model_type_parameter(self, tmp_path: Path, mocker: Any) -> None:
        output_file = tmp_path / "analysis.json"
        data_file = tmp_path / "data.json"
        data_file.write_text('{"listing_id": "1"}\n')
        captured_args = {}

        def mock_generate_value_analysis(*args, **kwargs):
            captured_args.update(kwargs)
            kwargs["output_file"].write_text('{"statistics": {"total_properties": 0}}')

        mocker.patch(
            "estate_value_index.analytics.value_analysis.generate_value_analysis",
            side_effect=mock_generate_value_analysis,
        )

        generate_value_analysis_task.fn(
            output_file=output_file, data_file=data_file, model_type="no_list_price"
        )
        assert captured_args["model_type"] == "no_list_price"

    @pytest.mark.unit
    def test_returns_correct_structure(self, tmp_path: Path, mocker: Any) -> None:
        output_file = tmp_path / "analysis.json"
        data_file = tmp_path / "data.json"
        data_file.write_text('{"listing_id": "1"}\n')

        def mock_generate_value_analysis(*args, **kwargs):
            kwargs["output_file"].write_text('{"statistics": {"total_properties": 0}}')

        mocker.patch(
            "estate_value_index.analytics.value_analysis.generate_value_analysis",
            side_effect=mock_generate_value_analysis,
        )

        result = generate_value_analysis_task.fn(output_file=output_file, data_file=data_file)

        assert "success" in result
        assert "timestamp" in result
        assert "output_file" in result
        assert "records_generated" in result


class TestUploadEnrichmentToGcsTask:
    @pytest.mark.unit
    def test_no_files_returns_empty_result(self, tmp_path: Path, mocker: Any) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        mocker.patch("estate_value_index.pipelines.tasks.analytics.get_storage_client")

        result = upload_enrichment_to_gcs_task.fn(local_dir=empty_dir, gcs_bucket="test-bucket")

        assert result["success"] is True
        assert result["uploaded_files"] == 0
        assert result["files"] == []

    @pytest.mark.unit
    def test_uploads_json_files(self, tmp_path: Path, mocker: Any) -> None:
        (tmp_path / "file1.json").write_text("{}")
        (tmp_path / "file2.json").write_text("{}")
        (tmp_path / "not_json.txt").write_text("skip me")

        mock_bucket = _mock_gcs_storage(mocker)

        result = upload_enrichment_to_gcs_task.fn(local_dir=tmp_path, gcs_bucket="test-bucket")

        assert result["success"] is True
        assert result["uploaded_files"] == 2
        assert mock_bucket.blob.return_value.upload_from_filename.call_count == 2

    @pytest.mark.unit
    def test_uses_correct_gcs_prefix(self, tmp_path: Path, mocker: Any) -> None:
        (tmp_path / "stats.json").write_text("{}")
        mock_bucket = _mock_gcs_storage(mocker)

        upload_enrichment_to_gcs_task.fn(
            local_dir=tmp_path,
            gcs_bucket="test-bucket",
            gcs_prefix="custom/prefix/",
        )

        assert "custom/prefix/" in mock_bucket.blob.call_args[0][0]

    @pytest.mark.unit
    def test_includes_file_metadata(self, tmp_path: Path, mocker: Any) -> None:
        (tmp_path / "test.json").write_text('{"key": "value"}')
        _mock_gcs_storage(mocker)

        result = upload_enrichment_to_gcs_task.fn(
            local_dir=tmp_path,
            gcs_bucket="my-bucket",
            gcs_prefix="data/",
        )

        assert len(result["files"]) == 1
        file_info = result["files"][0]
        assert "local_path" in file_info
        assert "gcs_uri" in file_info
        assert "size_bytes" in file_info
        assert file_info["gcs_uri"] == "gs://my-bucket/data/test.json"

    @pytest.mark.unit
    def test_returns_correct_structure(self, tmp_path: Path, mocker: Any) -> None:
        (tmp_path / "file.json").write_text("{}")
        _mock_gcs_storage(mocker)

        result = upload_enrichment_to_gcs_task.fn(local_dir=tmp_path, gcs_bucket="test-bucket")

        for field in ["success", "uploaded_files", "files", "bucket", "prefix", "timestamp"]:
            assert field in result
