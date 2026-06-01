"""Helpers for safe BigQuery SQL composition.

Rules for this codebase:
- **Identifiers** (e.g. GCP ``project_id``) cannot be passed through
  ``QueryJobConfig.query_parameters``; validate with an allow-list pattern
  (e.g. ``_validate_bq_project_id``) before any string interpolation into SQL.
- **Values** (scalars intended as literals) must use ``QueryJobConfig`` with
  ``ScalarQueryParameter`` / ``ArrayQueryParameter`` — never f-strings or
  ``.format`` for those fragments.
"""

from __future__ import annotations

import re

# GCP project IDs: 6–30 chars, lowercase letters, digits, hyphens; must start
# with a letter and not end with a hyphen.
_BQ_PROJECT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")


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
