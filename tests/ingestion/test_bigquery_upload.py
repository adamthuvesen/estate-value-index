from __future__ import annotations

from types import SimpleNamespace

import pytest

from estate_value_index.ingestion.bigquery_upload import _execute_merge, prepare_bq_row


def test_prepare_bq_row_rejects_missing_listing_id() -> None:
    with pytest.raises(ValueError, match="listing_id"):
        prepare_bq_row({"listing_id": None})


def test_prepare_bq_row_rejects_blank_listing_id() -> None:
    with pytest.raises(ValueError, match="listing_id"):
        prepare_bq_row({"listing_id": " "})


def test_prepare_bq_row_strips_listing_id() -> None:
    row = prepare_bq_row({"listing_id": "  abc-1  "})

    assert row["listing_id"] == "abc-1"


class _FakeMergeJob:
    def __init__(self, dml_stats: SimpleNamespace | None) -> None:
        self.dml_stats = dml_stats

    def result(self) -> None:
        return None


class _FakeMergeClient:
    def __init__(self, job: _FakeMergeJob) -> None:
        self.job = job
        self.queries: list[str] = []

    def query(self, sql: str) -> _FakeMergeJob:
        self.queries.append(sql)
        return self.job


def test_execute_merge_reads_row_counts_from_the_job_dml_stats() -> None:
    stats = SimpleNamespace(inserted_row_count=7, updated_row_count=3)
    client = _FakeMergeClient(_FakeMergeJob(stats))

    counts = _execute_merge(
        client,  # pyright: ignore[reportArgumentType]  # fake with the two methods used
        "p.d.t",
        "p.d.tmp",
        [],
        update_existing=True,
    )

    assert counts == (7, 3)
    assert "MERGE `p.d.t`" in client.queries[0]


def test_execute_merge_counts_zero_rows_without_dml_stats() -> None:
    client = _FakeMergeClient(_FakeMergeJob(None))

    counts = _execute_merge(
        client,  # pyright: ignore[reportArgumentType]  # fake with the two methods used
        "p.d.t",
        "p.d.tmp",
        [],
        update_existing=False,
    )

    assert counts == (0, 0)
