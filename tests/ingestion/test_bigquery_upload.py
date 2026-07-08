from __future__ import annotations

import pytest

from estate_value_index.ingestion.bigquery_upload import _prepare_rows, prepare_bq_row


def test_prepare_bq_row_rejects_missing_listing_id() -> None:
    with pytest.raises(ValueError, match="listing_id"):
        prepare_bq_row({"listing_id": None})


def test_prepare_rows_rejects_blank_listing_id() -> None:
    with pytest.raises(ValueError, match="listing_id"):
        _prepare_rows([{"listing_id": " "}])


def test_prepare_bq_row_strips_listing_id() -> None:
    row = prepare_bq_row({"listing_id": "  abc-1  "})

    assert row["listing_id"] == "abc-1"
