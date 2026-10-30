from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from estate_value_index.exceptions import DataValidationError
from estate_value_index.ingestion import bigquery_upload
from estate_value_index.ingestion.bigquery_upload import prepare_bq_row
from estate_value_index.ingestion.listing_row import BigQueryListingRow, validate_listing_rows

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[2] / "schemas" / "bq_raw_listings.json").read_text()
)


def _row(**overrides: Any) -> dict[str, Any]:
    return (
        prepare_bq_row(
            {
                "listing_id": "1",
                "sold_price": 5_000_000,
                "living_area": 54.5,
                "elevator": True,
                "sold_date": "2026-01-02",
                "scraped_at": "2026-01-03T10:00:00",
            }
        )
        | overrides
    )


def test_row_model_matches_the_bigquery_schema_file() -> None:
    assert list(BigQueryListingRow.model_fields) == [field["name"] for field in SCHEMA]
    required = {field["name"] for field in SCHEMA if field["mode"] == "REQUIRED"}
    assert required <= {
        name for name, field in BigQueryListingRow.model_fields.items() if field.is_required()
    }


def test_prepared_rows_pass() -> None:
    assert validate_listing_rows([_row()]) == [_row()]


@pytest.mark.parametrize(
    "bad",
    [
        {"living_area": "54"},
        {"elevator": "yes"},
        {"sold_date": "not-a-date"},
        {"images": "a.jpg"},
        {"unexpected_column": 1},
    ],
)
def test_malformed_rows_are_rejected_with_a_count(bad: dict[str, Any]) -> None:
    with pytest.raises(DataValidationError, match="1 of 2 listing rows"):
        validate_listing_rows([_row(), _row(**bad)])


def test_upload_rejects_malformed_rows_before_any_bigquery_call(
    tmp_path: Path, mocker: Any
) -> None:
    client = MagicMock()
    mocker.patch.object(bigquery_upload, "get_bq_client", return_value=client)
    listings = tmp_path / "listings.jsonl"
    listings.write_text(json.dumps({"listing_id": "1", "living_area": "fifty"}) + "\n")

    with pytest.raises(DataValidationError):
        bigquery_upload.upload_to_bigquery(listings, approved=True)
    assert client.mock_calls == []


def test_upload_deduplicates_listing_ids(tmp_path: Path, mocker: Any) -> None:
    client = MagicMock()
    client.get_table.return_value.schema = []
    client.query.return_value._properties = {}
    mocker.patch.object(bigquery_upload, "get_bq_client", return_value=client)
    listings = tmp_path / "listings.jsonl"
    listings.write_text(
        '{"listing_id": "1", "sold_price": 1}\n'
        '{"listing_id": "1", "sold_price": 2}\n'
        '{"listing_id": "2", "sold_price": 3}\n'
    )

    bigquery_upload.upload_to_bigquery(listings, approved=True)

    loaded = client.load_table_from_json.call_args.args[0]
    assert [row["listing_id"] for row in loaded] == ["1", "2"]
