"""Tests for BigQuery identifier validation and safe SQL composition."""

from __future__ import annotations

import datetime

import pytest

from estate_value_index.utils.bigquery_safety import (
    Filter,
    _validate_bq_dataset_id,
    _validate_bq_project_id,
    _validate_bq_table_id,
    build_filter_clause,
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


def test_build_filter_clause_empty() -> None:
    assert build_filter_clause([]) == ("", [])


def test_build_filter_clause_binary_scalar() -> None:
    sql, params = build_filter_clause([Filter("sold_price", ">=", 3_000_000)])
    assert sql == "WHERE `sold_price` >= @filter_0"
    assert len(params) == 1
    assert (params[0].name, params[0].type_, params[0].value) == ("filter_0", "INT64", 3_000_000)


def test_build_filter_clause_ands_multiple_predicates() -> None:
    sql, params = build_filter_clause(
        [
            Filter("sold_date", ">=", datetime.date(2024, 1, 1)),
            Filter("area", "=", "Södermalm"),
        ]
    )
    assert sql == "WHERE `sold_date` >= @filter_0 AND `area` = @filter_1"
    assert [p.type_ for p in params] == ["DATE", "STRING"]


def test_build_filter_clause_in_uses_array_param_and_unnest() -> None:
    sql, params = build_filter_clause([Filter("area", "IN", ["Södermalm", "Vasastan"])])
    assert sql == "WHERE `area` IN UNNEST(@filter_0)"
    assert params[0].array_type == "STRING"
    assert params[0].values == ["Södermalm", "Vasastan"]


def test_build_filter_clause_unary_takes_no_param() -> None:
    sql, params = build_filter_clause([Filter("sold_price", "IS NOT NULL")])
    assert sql == "WHERE `sold_price` IS NOT NULL"
    assert params == []


def test_build_filter_clause_operator_is_case_insensitive() -> None:
    sql, _ = build_filter_clause([Filter("area", "in", ["A", "B"])])
    assert sql == "WHERE `area` IN UNNEST(@filter_0)"


@pytest.mark.parametrize(
    ("value", "bq_type"),
    [
        (True, "BOOL"),
        (5, "INT64"),
        (1.5, "FLOAT64"),
        ("x", "STRING"),
        (datetime.date(2024, 1, 1), "DATE"),
        (datetime.datetime(2024, 1, 1, 12, 0), "TIMESTAMP"),
    ],
)
def test_build_filter_clause_infers_scalar_type(value: object, bq_type: str) -> None:
    _, params = build_filter_clause([Filter("c", "=", value)])
    assert params[0].type_ == bq_type


def test_build_filter_clause_rejects_bad_column() -> None:
    with pytest.raises(ValueError, match="invalid BigQuery identifier"):
        build_filter_clause([Filter("area; DROP TABLE x", "=", "A")])


def test_build_filter_clause_rejects_unknown_operator() -> None:
    with pytest.raises(ValueError, match="unsupported filter operator"):
        build_filter_clause([Filter("area", "LIKE", "A%")])


def test_build_filter_clause_rejects_unary_with_value() -> None:
    with pytest.raises(ValueError, match="takes no value"):
        build_filter_clause([Filter("area", "IS NULL", "x")])


def test_build_filter_clause_rejects_empty_in() -> None:
    with pytest.raises(ValueError, match="non-empty sequence"):
        build_filter_clause([Filter("area", "IN", [])])


def test_build_filter_clause_rejects_binary_without_value() -> None:
    with pytest.raises(ValueError, match="requires a value"):
        build_filter_clause([Filter("area", "=", None)])


def test_build_filter_clause_rejects_unsupported_value_type() -> None:
    with pytest.raises(ValueError, match="unsupported filter value type"):
        build_filter_clause([Filter("area", "=", {"nope": 1})])
