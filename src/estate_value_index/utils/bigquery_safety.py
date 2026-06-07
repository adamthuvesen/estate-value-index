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

import re

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
