"""Helpers for safe BigQuery SQL composition.

Rules for this codebase:
- **Identifiers** (project / dataset / table / column names) cannot be passed
  through ``QueryJobConfig.query_parameters``. Validate them against an
  allow-list pattern and quote them via the helpers here before any string
  interpolation into SQL: use :func:`safe_table_ref` for table references and
  :func:`quote_identifier` for column/field names.
- **Values** (scalars intended as literals) must use ``QueryJobConfig`` with
  ``ScalarQueryParameter`` / ``ArrayQueryParameter`` — never f-strings or
  ``.format`` for those fragments.

The validators reject anything outside ``[A-Za-z0-9_-]`` (per component), so a
malformed identifier raises ``ValueError`` *before* it can reach a query string.
``tests/utils/test_no_unsafe_sql.py`` enforces that new dynamic SQL routes
through these helpers (or is explicitly reviewed), preventing regressions.
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

# GCP project IDs: 6–30 chars, lowercase letters, digits, hyphens; must start
# with a letter and not end with a hyphen.
_BQ_PROJECT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
# BigQuery dataset IDs: letters, digits, underscores only; up to 1024 chars.
# Explicit ASCII class (not ``\w``) so Unicode word characters can't slip in.
_BQ_DATASET_ID_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,1024}$")
# Table IDs in this codebase are simple identifiers, including the temp/staging
# suffixes the pipelines append (e.g. ``listings_temp_20240115_103000``,
# ``engineered_features_staging_ab12cd34``). We deliberately restrict to the
# ``[A-Za-z0-9_]`` subset BigQuery shares with datasets rather than allowing the
# full Unicode table-name grammar — stricter than BigQuery, sufficient here.
_BQ_TABLE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,1024}$")
# Column / field identifiers: letters, digits, underscores; cannot start with a
# digit. Capped well under BigQuery's 300-char limit.
_BQ_COLUMN_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,299}$")


def _validate_bq_project_id(value: str) -> str:
    """Return ``value`` if it matches the documented GCP project ID format.

    Args:
        value: Candidate project ID.

    Returns:
        The same string if valid.

    Raises:
        ValueError: If ``value`` is not a well-formed GCP project ID.
    """
    if not isinstance(value, str):
        raise ValueError("invalid GCP project_id: must be a string")
    if _BQ_PROJECT_ID_PATTERN.fullmatch(value) is None:
        raise ValueError(f"invalid GCP project_id: {value!r}")
    return value


def _validate_bq_dataset_id(value: str) -> str:
    """Return ``value`` if it is a well-formed BigQuery dataset ID.

    Raises:
        ValueError: If ``value`` is not a valid dataset identifier.
    """
    if not isinstance(value, str):
        raise ValueError("invalid BigQuery dataset_id: must be a string")
    if _BQ_DATASET_ID_PATTERN.fullmatch(value) is None:
        raise ValueError(f"invalid BigQuery dataset_id: {value!r}")
    return value


def _validate_bq_table_id(value: str) -> str:
    """Return ``value`` if it is a well-formed BigQuery table ID (this codebase's subset).

    Raises:
        ValueError: If ``value`` is not a valid table identifier.
    """
    if not isinstance(value, str):
        raise ValueError("invalid BigQuery table_id: must be a string")
    if _BQ_TABLE_ID_PATTERN.fullmatch(value) is None:
        raise ValueError(f"invalid BigQuery table_id: {value!r}")
    return value


def safe_table_ref(
    project_id: str,
    dataset_id: str,
    table_id: str,
    *,
    quote: bool = False,
) -> str:
    """Validate the three components and join them into ``project.dataset.table``.

    Each component is checked against its allow-list pattern; a malformed value
    raises ``ValueError`` before it can reach SQL. This is the only sanctioned
    way to build a table reference for interpolation into a query string.

    Args:
        project_id: GCP project ID.
        dataset_id: BigQuery dataset ID.
        table_id: BigQuery table ID (may include a temp/staging suffix).
        quote: When ``True``, return the backtick-quoted form (``` `a.b.c` ```)
            for embedding in a query string. When ``False`` (default), return
            the bare ``a.b.c`` form expected by the BigQuery client API
            (``get_table``, ``insert_rows_json``, ``delete_table``, …).

    Returns:
        The validated fully-qualified table reference.

    Raises:
        ValueError: If any component is malformed.
    """
    ref = (
        f"{_validate_bq_project_id(project_id)}"
        f".{_validate_bq_dataset_id(dataset_id)}"
        f".{_validate_bq_table_id(table_id)}"
    )
    return f"`{ref}`" if quote else ref


def quote_identifier(name: str) -> str:
    """Validate a column/field identifier and return it backtick-quoted for SQL.

    Use for any column or field name interpolated into a query (e.g. dynamic
    ``MERGE`` column lists). Backtick-quoting a validated identifier makes it
    safe to embed even though BigQuery has no query parameter for identifiers.

    Args:
        name: Column or field name.

    Returns:
        The backtick-quoted identifier (``` `name` ```).

    Raises:
        ValueError: If ``name`` is not a valid column identifier.
    """
    if not isinstance(name, str):
        raise ValueError("invalid BigQuery identifier: must be a string")
    if _BQ_COLUMN_PATTERN.fullmatch(name) is None:
        raise ValueError(f"invalid BigQuery identifier: {name!r}")
    return f"`{name}`"


# Allowed predicate operators -> arity. This is the closed set a Filter may use;
# anything else is rejected, so an operator can never smuggle in SQL.
_FILTER_OPERATORS: dict[str, str] = {
    "=": "binary",
    "!=": "binary",
    "<": "binary",
    "<=": "binary",
    ">": "binary",
    ">=": "binary",
    "IN": "list",
    "NOT IN": "list",
    "IS NULL": "unary",
    "IS NOT NULL": "unary",
}


@dataclass(frozen=True)
class Filter:
    """A single structured SQL predicate: ``column <operator> value``.

    Pass a list of these to ``load_from_bigquery(filters=...)`` /
    ``load_features_from_bigquery(filters=...)`` instead of a raw SQL string.
    :func:`build_filter_clause` validates the column as an identifier, checks the
    operator against :data:`_FILTER_OPERATORS`, and binds the value as a query
    parameter — so a Filter cannot carry a SQL fragment even when authored by an
    operator. This replaces the former raw ``where_clause`` escape hatch.

    Examples:
        ``Filter("sold_date", ">=", date(2024, 1, 1))``
        ``Filter("area", "IN", ["Södermalm", "Vasastan"])``
        ``Filter("sold_price", "IS NOT NULL")``
    """

    column: str
    operator: str = "="
    value: Any = None


def _bq_scalar_type(value: Any) -> str:
    """Map a Python scalar to its BigQuery query-parameter type name.

    Raises:
        ValueError: If ``value`` is not a supported scalar type.
    """
    # bool before int (bool is an int subclass); datetime before date likewise.
    if isinstance(value, bool):
        return "BOOL"
    if isinstance(value, int):
        return "INT64"
    if isinstance(value, float):
        return "FLOAT64"
    if isinstance(value, str):
        return "STRING"
    if isinstance(value, datetime.datetime):
        return "TIMESTAMP"
    if isinstance(value, datetime.date):
        return "DATE"
    raise ValueError(f"unsupported filter value type: {type(value).__name__}")


def build_filter_clause(filters: Sequence[Filter]) -> tuple[str, list]:
    """Build a parameterised ``WHERE`` clause from structured :class:`Filter`s.

    Args:
        filters: Predicates to AND together. Empty/falsy yields no clause.

    Returns:
        ``(where_sql, query_parameters)``. ``where_sql`` is ``""`` when there are
        no filters, otherwise a string beginning with ``WHERE``. ``query_parameters``
        is a list of BigQuery ``ScalarQueryParameter`` / ``ArrayQueryParameter`` to
        attach via ``QueryJobConfig``.

    Raises:
        ValueError: On an invalid column identifier, a disallowed operator, or a
            value that does not match the operator's arity / a supported type.
    """
    if not filters:
        return "", []

    from google.cloud import bigquery  # lazy: only needed when filters are used

    predicates: list[str] = []
    params: list[Any] = []

    for index, predicate in enumerate(filters):
        column_sql = quote_identifier(predicate.column)
        operator = predicate.operator.strip().upper()
        kind = _FILTER_OPERATORS.get(operator)
        if kind is None:
            raise ValueError(f"unsupported filter operator: {predicate.operator!r}")

        if kind == "unary":
            if predicate.value is not None:
                raise ValueError(f"operator {operator!r} takes no value")
            predicates.append(f"{column_sql} {operator}")
            continue

        param_name = f"filter_{index}"
        if kind == "list":
            if not isinstance(predicate.value, (list, tuple, set)) or not predicate.value:
                raise ValueError(f"operator {operator!r} requires a non-empty sequence value")
            values = list(predicate.value)
            params.append(
                bigquery.ArrayQueryParameter(param_name, _bq_scalar_type(values[0]), values)
            )
            predicates.append(f"{column_sql} {operator} UNNEST(@{param_name})")
        else:  # binary
            if predicate.value is None:
                raise ValueError(f"operator {operator!r} requires a value")
            params.append(
                bigquery.ScalarQueryParameter(
                    param_name, _bq_scalar_type(predicate.value), predicate.value
                )
            )
            predicates.append(f"{column_sql} {operator} @{param_name}")

    return "WHERE " + " AND ".join(predicates), params
