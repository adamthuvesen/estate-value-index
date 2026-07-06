"""Unit tests for pipelines/tasks/ingestion.py."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest

from estate_value_index.pipelines.tasks.ingestion import (
    geocode_new_addresses_task,
    process_listings_task,
    upload_to_bigquery_task,
)


class TestProcessListingsTask:
    @pytest.mark.unit
    def test_dry_run_returns_early(self, tmp_path: Path) -> None:
        input_file = tmp_path / "input.json"
        input_file.write_text('{"listing_id": "1"}\n')

        result = process_listings_task.fn(input_file=input_file, dry_run=True)

        assert result["success"] is True
        assert result["dry_run"] is True
        assert result["total_listings"] == 0

    @pytest.mark.unit
    def test_missing_input_file_raises(self, tmp_path: Path) -> None:
        non_existent = tmp_path / "missing.json"

        with pytest.raises(FileNotFoundError):
            process_listings_task.fn(input_file=non_existent)

    @pytest.mark.unit
    def test_returns_processing_result(self, tmp_path: Path, mocker: Any) -> None:
        input_file = tmp_path / "input.json"
        input_file.write_text('{"listing_id": "1"}\n')

        output_file = tmp_path / "output.json"
        output_file.write_text('{"listing_id": "1"}\n{"listing_id": "2"}\n')

        mocker.patch("estate_value_index.ingestion.processing.process_pipeline")

        result = process_listings_task.fn(input_file=input_file, output_file=output_file)

        assert result["success"] is True
        assert "timestamp" in result
        assert "input_file" in result
        assert "output_file" in result
        assert "total_listings" in result

    @pytest.mark.unit
    def test_uses_default_output_file(self, tmp_path: Path, mocker: Any) -> None:
        input_file = tmp_path / "input.json"
        input_file.write_text('{"listing_id": "1"}\n')

        prod_file = tmp_path / "booli_listings_prod.json"
        prod_file.write_text('{"listing_id": "1"}\n')

        mocker.patch("estate_value_index.ingestion.processing.process_pipeline")

        result = process_listings_task.fn(input_file=input_file, production_file=prod_file)
        assert result["success"] is True

    @pytest.mark.unit
    def test_counts_output_lines(self, tmp_path: Path, mocker: Any) -> None:
        input_file = tmp_path / "input.json"
        input_file.write_text('{"listing_id": "1"}\n')

        output_file = tmp_path / "output.json"
        # 5 records + one empty line that must be skipped
        output_file.write_text(
            '{"listing_id": "1"}\n'
            '{"listing_id": "2"}\n'
            '{"listing_id": "3"}\n'
            "\n"
            '{"listing_id": "4"}\n'
            '{"listing_id": "5"}\n'
        )

        mocker.patch("estate_value_index.ingestion.processing.process_pipeline")

        result = process_listings_task.fn(input_file=input_file, output_file=output_file)
        assert result["total_listings"] == 5


class TestUploadToBigqueryTask:
    @pytest.mark.unit
    def test_missing_file_raises(self, tmp_path: Path) -> None:
        non_existent = tmp_path / "missing.json"

        with pytest.raises(FileNotFoundError):
            upload_to_bigquery_task.fn(processed_file=non_existent)

    @pytest.mark.unit
    def test_deduplicates_listings_in_memory(self, tmp_path: Path, mocker: Any) -> None:
        """listing_id duplicates must be removed before upload."""
        processed_file = tmp_path / "listings.json"
        processed_file.write_text(
            '{"listing_id": "1", "price": 1000000}\n'
            '{"listing_id": "1", "price": 1100000}\n'
            '{"listing_id": "2", "price": 2000000}\n'
        )

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_field_1 = MagicMock()
        mock_field_1.name = "listing_id"
        mock_field_2 = MagicMock()
        mock_field_2.name = "price"
        mock_table.schema = [mock_field_1, mock_field_2]
        mock_client.get_table.return_value = mock_table
        mock_client.create_table.return_value = None
        mock_client.delete_table.return_value = None

        mock_load_job = MagicMock()
        mock_load_job.result.return_value = None
        mock_client.load_table_from_json.return_value = mock_load_job

        mock_merge_job = MagicMock()
        mock_merge_job.result.return_value = None
        mock_merge_job._properties = {
            "statistics": {"query": {"dmlStats": {"insertedRowCount": 2}}}
        }
        mock_client.query.return_value = mock_merge_job

        mocker.patch(
            "estate_value_index.pipelines.tasks.ingestion.get_bq_config",
            return_value=MagicMock(
                client=mock_client,
                full_table_id="project.dataset.table",
                project_id="project",
                dataset_id="dataset",
                table_id="table",
            ),
        )

        mocker.patch(
            "estate_value_index.ingestion.bigquery_upload.prepare_bq_row",
            side_effect=lambda x: x,
        )

        result = upload_to_bigquery_task.fn(processed_file=processed_file)

        loaded_data = mock_client.load_table_from_json.call_args[0][0]
        assert len(loaded_data) == 2
        assert result["success"] is True

    @pytest.mark.unit
    def test_rejects_missing_listing_id_before_upload(self, tmp_path: Path, mocker: Any) -> None:
        processed_file = tmp_path / "listings.json"
        processed_file.write_text('{"listing_id": null, "price": 1000000}\n')

        mocker.patch(
            "estate_value_index.pipelines.tasks.ingestion.get_bq_config",
            return_value=MagicMock(
                client=MagicMock(),
                full_table_id="project.dataset.table",
                project_id="project",
                dataset_id="dataset",
                table_id="table",
            ),
        )

        with pytest.raises(ValueError, match="listing_id"):
            upload_to_bigquery_task.fn(processed_file=processed_file)


class TestGeocodeNewAddressesTask:
    @pytest.mark.unit
    def test_insert_errors_raise(self, mocker: Any) -> None:
        mock_client = MagicMock()
        mock_client.query.return_value.to_dataframe.return_value = pd.DataFrame(
            [{"address": "Street 1", "area": "Solna", "geocode_key": "Street 1, solna"}]
        )
        mock_client.insert_rows_json.return_value = [{"index": 0, "errors": ["bad row"]}]

        mocker.patch("estate_value_index.pipelines.tasks.ingestion.get_bq_client", return_value=mock_client)
        mocker.patch(
            "estate_value_index.utils.settings.load_env_config",
            return_value=MagicMock(bigquery_project_id="test-project"),
        )
        mocker.patch("estate_value_index.ml.geocoding.geocode_address", return_value=(59.3, 18.0))

        with pytest.raises(RuntimeError, match="geocode insert errors"):
            geocode_new_addresses_task.fn(rate_limit_delay=0)
