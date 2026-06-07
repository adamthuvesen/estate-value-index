"""Tests for BigQuery identifier validation and safe SQL composition."""

from __future__ import annotations

import pytest

from estate_value_index.utils.bigquery_safety import (
    _validate_bq_dataset_id,
    _validate_bq_project_id,
    _validate_bq_table_id,
    quote_identifier,
    safe_table_ref,
)


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


@pytest.mark.parametrize(
    "invalid",
    [
        "booli raw",  # space
        "booli-raw",  # hyphen not allowed in datasets
        "booli.raw",  # dot
        "raw;DROP TABLE x",
        "raw`x",
        "",
        "räw",  # non-ASCII word char must not slip through \w
    ],
)
def test_validate_bq_dataset_id_rejects(invalid: str) -> None:
    with pytest.raises(ValueError, match="invalid BigQuery dataset_id"):
        _validate_bq_dataset_id(invalid)


@pytest.mark.parametrize("valid", ["booli_raw", "booli_features", "dataset", "A1_b2"])
def test_validate_bq_dataset_id_accepts(valid: str) -> None:
    assert _validate_bq_dataset_id(valid) == valid


@pytest.mark.parametrize(
    "invalid",
    [
        "listings; DROP TABLE x",
        "list`ings",
        "list.ings",
        "list ings",
        "",
        "läst",
    ],
)
def test_validate_bq_table_id_rejects(invalid: str) -> None:
    with pytest.raises(ValueError, match="invalid BigQuery table_id"):
        _validate_bq_table_id(invalid)


@pytest.mark.parametrize(
    "valid",
    [
        "listings",
        "engineered_features",
        "listings_temp_20240115_103000",  # temp suffix the pipeline appends
        "engineered_features_staging_ab12cd34",  # staging suffix
    ],
)
def test_validate_bq_table_id_accepts(valid: str) -> None:
    assert _validate_bq_table_id(valid) == valid


def test_safe_table_ref_unquoted_and_quoted() -> None:
    assert (
        safe_table_ref("estate-value-index", "booli_raw", "listings")
        == "estate-value-index.booli_raw.listings"
    )
    assert (
        safe_table_ref("estate-value-index", "booli_raw", "listings", quote=True)
        == "`estate-value-index.booli_raw.listings`"
    )


@pytest.mark.parametrize(
    ("project", "dataset", "table"),
    [
        ("proj", "booli_raw", "listings"),  # project too short
        ("estate-value-index", "booli raw", "listings"),  # bad dataset
        ("estate-value-index", "booli_raw", "listings`; DROP TABLE x --"),  # injection
        ("estate-value-index", "booli_raw", "listings WHERE 1=1"),  # injection
    ],
)
def test_safe_table_ref_rejects_bad_components(project: str, dataset: str, table: str) -> None:
    with pytest.raises(ValueError):
        safe_table_ref(project, dataset, table)


@pytest.mark.parametrize("name", ["listing_id", "price_per_sqm", "_private", "col1"])
def test_quote_identifier_accepts(name: str) -> None:
    assert quote_identifier(name) == f"`{name}`"


@pytest.mark.parametrize(
    "name",
    [
        "1col",  # cannot start with a digit
        "col name",  # space
        "col`",  # backtick
        "col;DROP",  # injection
        "",
    ],
)
def test_quote_identifier_rejects(name: str) -> None:
    with pytest.raises(ValueError, match="invalid BigQuery identifier"):
        quote_identifier(name)
