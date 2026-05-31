"""Tests for BigQuery identifier validation."""

from __future__ import annotations

import pytest

from estate_value_index.utils.bigquery_safety import _validate_bq_project_id


@pytest.mark.parametrize(
    "invalid",
    [
        "foo;DROP TABLE",
        "foo`bar",
        "FOO",
        "",
        "a" * 31,
        "a-",
        "-a",
    ],
)
def test_validate_bq_project_id_rejects(invalid: str) -> None:
    with pytest.raises(ValueError, match="invalid GCP project_id"):
        _validate_bq_project_id(invalid)


@pytest.mark.parametrize(
    "valid",
    [
        "estate-value-index",
        "my-project-123",
        "a-b-c-d-e",
    ],
)
def test_validate_bq_project_id_accepts(valid: str) -> None:
    assert _validate_bq_project_id(valid) == valid
