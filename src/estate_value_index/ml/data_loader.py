"""Data loading utilities for Booli listing exports."""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from estate_value_index.exceptions import BigQueryError, exception_context
from estate_value_index.ml.features.micro_area import normalize_coordinate_columns
from estate_value_index.utils.bigquery_safety import (
    Filter,
    build_filter_clause,
    safe_table_ref,
    validate_bq_project_id,
)
from estate_value_index.utils.clients import get_bq_client
from estate_value_index.utils.settings import get_settings

JSON_GLOB = "*.json"
_NUMERIC_COLUMNS = [
    "listing_price",
    "sold_price",
    "living_area",
    "rooms",
    "monthly_fee",
    "price_per_sqm",
    "days_on_market",
    "construction_year",
    "floor",
    "latitude",
    "longitude",
    "lat",
    "lon",
]
_DATETIME_COLUMNS = ("scraped_at", "sold_date")

# Optional BigQuery support
HAS_BIGQUERY = importlib.util.find_spec("google.cloud.bigquery") is not None


def _iter_json_objects(raw_text: str) -> Iterator[Any]:
    """Yield JSON objects from a raw string that may contain concatenated payloads."""

    decoder = json.JSONDecoder()
    idx = 0
    length = len(raw_text)
    while idx < length:
        # Skip whitespace between JSON structures
        while idx < length and raw_text[idx].isspace():
            idx += 1
        if idx >= length:
            break
        obj, offset = decoder.raw_decode(raw_text, idx)
        yield obj
        idx = offset


def _coerce_records(value: Any) -> list[dict[str, Any]]:
    """Normalise a decoded JSON object into a list of dict records."""

    if isinstance(value, list):
        records = [item for item in value if isinstance(item, dict)]
        return records
    if isinstance(value, dict):
        return [value]
    raise ValueError(f"Unsupported JSON payload type: {type(value)!r}")


def load_raw_records(paths: Sequence[Path]) -> list[dict[str, Any]]:
    """Load raw listing records from the provided JSON files."""

    all_records: list[dict[str, Any]] = []
    for path in paths:
        raw_text = path.read_text(encoding="utf-8")
        for obj in _iter_json_objects(raw_text):
            all_records.extend(_coerce_records(obj))
    return all_records


def _coerce_numeric(df: pd.DataFrame, columns: Iterable[str]) -> None:
    for column in columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")


def _coerce_datetime(df: pd.DataFrame, columns: Iterable[str]) -> None:
    for column in columns:
        if column in df.columns:
            df[column] = pd.to_datetime(df[column], errors="coerce")


def _listing_json_paths(data_path: Path, glob: str) -> list[Path]:
    json_paths = sorted(p for p in data_path.glob(glob) if p.is_file())
    if json_paths:
        return json_paths
    return sorted(p for p in data_path.rglob(glob) if p.is_file())


def _normalize_listing_frame(
    frame: pd.DataFrame,
    *,
    drop_duplicate_listing_ids: bool,
) -> pd.DataFrame:
    _coerce_numeric(frame, _NUMERIC_COLUMNS)
    _coerce_datetime(frame, _DATETIME_COLUMNS)
    normalize_coordinate_columns(frame)

    if drop_duplicate_listing_ids and "listing_id" in frame.columns:
        sort_columns = [col for col in ("listing_id", "scraped_at") if col in frame.columns]
        frame = frame.sort_values(sort_columns)
        frame = frame.drop_duplicates(subset=["listing_id"], keep="last")

    return frame.reset_index(drop=True)


def _require_bigquery() -> None:
    if not HAS_BIGQUERY:
        raise ImportError(
            "google-cloud-bigquery is required for BigQuery support. "
            "Install it with: pip install google-cloud-bigquery"
        )


def load_listings(
    data_dir: Path | str,
    glob: str = JSON_GLOB,
    *,
    drop_duplicate_listing_ids: bool = True,
) -> pd.DataFrame:
    """Load Booli listing snapshots into a single DataFrame."""

    data_path = Path(data_dir)
    if not data_path.exists():
        raise FileNotFoundError(f"Data directory does not exist: {data_path}")

    json_paths = _listing_json_paths(data_path, glob)
    if not json_paths:
        return pd.DataFrame()

    records = load_raw_records(json_paths)
    if not records:
        return pd.DataFrame()

    frame = pd.DataFrame.from_records(records)
    return _normalize_listing_frame(
        frame,
        drop_duplicate_listing_ids=drop_duplicate_listing_ids,
    )


def load_from_bigquery(
    project_id: str | None = None,
    dataset_id: str | None = None,
    table_id: str | None = None,
    *,
    drop_duplicate_listing_ids: bool = True,
    filters: Sequence[Filter] | None = None,
) -> pd.DataFrame:
    """Load Booli listings from BigQuery.

    Args:
        project_id: GCP project ID. If None, uses environment config.
        dataset_id: BigQuery dataset name. If None, uses environment config.
        table_id: BigQuery table name. If None, uses environment config.
        drop_duplicate_listing_ids: Whether to deduplicate by listing_id.
        filters: Optional structured predicates ANDed into a parameterised
            ``WHERE`` clause (see :class:`~estate_value_index.utils.bigquery_safety.Filter`).
            Columns/operators are validated and values are bound as query
            parameters, so this is safe even for operator-authored filters — it
            replaces the former raw ``where_clause`` string.

    Returns:
        DataFrame with listings from BigQuery.

    Raises:
        ImportError: If google-cloud-bigquery is not installed.
        BigQueryError: If the BigQuery query fails.
    """
    _require_bigquery()
    from google.cloud import bigquery

    settings = get_settings()
    project_id = validate_bq_project_id(project_id or settings.require_bigquery_project_id())
    dataset_id = dataset_id or settings.bigquery_dataset_raw
    table_id = table_id or settings.bigquery_table_listings

    query = f"""
        SELECT *
        FROM {safe_table_ref(project_id, dataset_id, table_id, quote=True)}
    """

    where_sql, query_params = build_filter_clause(filters or [])
    if where_sql:
        query += f"\n        {where_sql}"

    try:
        client = get_bq_client(project_id)
        job_config = (
            bigquery.QueryJobConfig(query_parameters=query_params) if query_params else None
        )
        # Regular tabledata API; some envs can't reach bigquerystorage.googleapis.com.
        df = client.query(query, job_config=job_config).to_dataframe(create_bqstorage_client=False)
    except Exception as e:
        raise BigQueryError(
            f"Failed to query BigQuery: {e}",
            context=exception_context("load_from_bigquery", dataset=dataset_id, table=table_id),
        ) from e
    return _normalize_listing_frame(
        df,
        drop_duplicate_listing_ids=drop_duplicate_listing_ids,
    )
