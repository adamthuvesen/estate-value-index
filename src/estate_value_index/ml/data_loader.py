"""Data loading utilities for Booli listing exports."""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from estate_value_index.exceptions import BigQueryError, exception_context
from estate_value_index.utils.bigquery_safety import _validate_bq_project_id
from estate_value_index.utils.clients import get_bq_client
from estate_value_index.utils.settings import load_env_config

JSON_GLOB = "*.json"

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


def _coerce_records(value: Any) -> list[dict]:
    """Normalise a decoded JSON object into a list of dict records."""

    if isinstance(value, list):
        records = [item for item in value if isinstance(item, dict)]
        return records
    if isinstance(value, dict):
        return [value]
    raise ValueError(f"Unsupported JSON payload type: {type(value)!r}")


def load_raw_records(paths: Sequence[Path]) -> list[dict]:
    """Load raw listing records from the provided JSON files."""

    all_records: list[dict] = []
    for path in paths:
        raw_text = path.read_text(encoding="utf-8")
        for obj in _iter_json_objects(raw_text):
            all_records.extend(_coerce_records(obj))
    return all_records


def _coerce_numeric(df: pd.DataFrame, columns: Iterable[str]) -> None:
    for column in columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")


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

    json_paths = sorted(p for p in data_path.glob(glob) if p.is_file())
    # Also search in subdirectories if no files found in root
    if not json_paths:
        json_paths = sorted(p for p in data_path.rglob(glob) if p.is_file())
    if not json_paths:
        return pd.DataFrame()

    records = load_raw_records(json_paths)
    if not records:
        return pd.DataFrame()

    frame = pd.DataFrame.from_records(records)

    # Normalise common column types
    numeric_columns = [
        "listing_price",
        "sold_price",
        "living_area",
        "rooms",
        "monthly_fee",
        "price_per_sqm",
        "days_on_market",
        "construction_year",
        "floor",
    ]
    _coerce_numeric(frame, numeric_columns)

    for column in ("scraped_at", "sold_date"):
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")

    if drop_duplicate_listing_ids and "listing_id" in frame.columns:
        sort_columns = [col for col in ("listing_id", "scraped_at") if col in frame.columns]
        frame = frame.sort_values(sort_columns)
        frame = frame.drop_duplicates(subset=["listing_id"], keep="last")

    return frame.reset_index(drop=True)


def _find_project_root(start: Path) -> Path:
    """Walk upward from ``start`` until a ``pyproject.toml`` is found."""
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise FileNotFoundError(
        f"Could not locate project root (no pyproject.toml found above {start})"
    )


def load_default_dataset(*, drop_duplicate_listing_ids: bool = True) -> pd.DataFrame:
    """Load data from the repo's ``data/`` directory.

    Walks upward from this module until a ``pyproject.toml`` marker is found,
    then loads listings from ``<project_root>/data``. Raises ``FileNotFoundError``
    rather than silently returning an empty DataFrame when the marker or the
    data directory is missing.
    """
    project_root = _find_project_root(Path(__file__).resolve())
    default_data_dir = project_root / "data"
    if not default_data_dir.is_dir():
        raise FileNotFoundError(f"Default data directory not found: {default_data_dir}")
    return load_listings(default_data_dir, drop_duplicate_listing_ids=drop_duplicate_listing_ids)


def load_from_bigquery(
    project_id: str | None = None,
    dataset_id: str | None = None,
    table_id: str | None = None,
    *,
    drop_duplicate_listing_ids: bool = True,
    where_clause: str | None = None,
) -> pd.DataFrame:
    """Load Booli listings from BigQuery.

    Args:
        project_id: GCP project ID. If None, uses environment config.
        dataset_id: BigQuery dataset name. If None, uses environment config.
        table_id: BigQuery table name. If None, uses environment config.
        drop_duplicate_listing_ids: Whether to deduplicate by listing_id.
        where_clause: Optional SQL predicate (without the ``WHERE`` keyword).
            **Trusted input only** — must be authored by operators (notebooks,
            training scripts). Never pass request-derived or user-controlled
            strings; there is no parameterisation for arbitrary SQL fragments.

    Returns:
        DataFrame with listings from BigQuery.

    Raises:
        ImportError: If google-cloud-bigquery is not installed.
        BigQueryError: If the BigQuery query fails.
    """
    if not HAS_BIGQUERY:
        raise ImportError(
            "google-cloud-bigquery is required for BigQuery support. "
            "Install it with: pip install google-cloud-bigquery"
        )

    # Load environment configuration
    env_config = load_env_config()

    # Use provided values or fall back to environment config
    project_id = _validate_bq_project_id(project_id or env_config.bigquery_project_id)
    dataset_id = dataset_id or env_config.bq_dataset_raw
    table_id = table_id or env_config.bq_table_listings

    # Build query
    query = f"""
        SELECT *
        FROM `{project_id}.{dataset_id}.{table_id}`
    """

    # trusted-input: optional predicate only; call sites are operator-controlled
    # (train_model.py, feature_materialization.py, scripts/*.py) — never user/request input.
    if where_clause:
        query += f"\n        WHERE {where_clause}"

    try:
        client = get_bq_client(project_id)
        df = client.query(query).to_dataframe()
    except Exception as e:
        raise BigQueryError(
            f"Failed to query BigQuery: {e}",
            context=exception_context("load_from_bigquery", dataset=dataset_id, table=table_id),
        ) from e

    # Apply same normalization as load_listings()
    numeric_columns = [
        "listing_price",
        "sold_price",
        "living_area",
        "rooms",
        "monthly_fee",
        "price_per_sqm",
        "days_on_market",
        "construction_year",
        "floor",
    ]
    _coerce_numeric(df, numeric_columns)

    for column in ("scraped_at", "sold_date"):
        if column in df.columns:
            df[column] = pd.to_datetime(df[column], errors="coerce")

    if drop_duplicate_listing_ids and "listing_id" in df.columns:
        sort_columns = [col for col in ("listing_id", "scraped_at") if col in df.columns]
        df = df.sort_values(sort_columns)
        df = df.drop_duplicates(subset=["listing_id"], keep="last")

    return df.reset_index(drop=True)


def load_features_from_bigquery(
    project_id: str | None = None,
    dataset_id: str | None = None,
    table_id: str | None = None,
    *,
    where_clause: str | None = None,
) -> pd.DataFrame:
    """Load pre-computed engineered features from BigQuery.

    This function loads features materialized by
    ``uv run python -m estate_value_index.cli features``, skipping the feature
    engineering step.

    Args:
        project_id: GCP project ID. If None, uses environment config.
        dataset_id: BigQuery dataset name. If None, uses environment config.
        table_id: BigQuery table name. If None, uses environment config.
        where_clause: Optional SQL predicate (without the ``WHERE`` keyword).
            **Trusted input only** — same contract as ``load_from_bigquery``.

    Returns:
        DataFrame with pre-computed engineered features ready for training.

    Raises:
        ImportError: If google-cloud-bigquery is not installed.
        BigQueryError: If the BigQuery query fails.
    """
    if not HAS_BIGQUERY:
        raise ImportError(
            "google-cloud-bigquery is required for BigQuery support. "
            "Install it with: pip install google-cloud-bigquery"
        )

    # Load environment configuration
    env_config = load_env_config()

    # Use provided values or fall back to environment config
    project_id = _validate_bq_project_id(project_id or env_config.bigquery_project_id)
    dataset_id = dataset_id or env_config.bq_dataset_features
    table_id = table_id or env_config.bq_table_features

    # Build query
    query = f"""
        SELECT *
        FROM `{project_id}.{dataset_id}.{table_id}`
    """

    # trusted-input: same boundary as load_from_bigquery (operator-authored only).
    if where_clause:
        query += f"\n        WHERE {where_clause}"

    try:
        client = get_bq_client(project_id)
        df = client.query(query).to_dataframe()
    except Exception as e:
        raise BigQueryError(
            f"Failed to query BigQuery features: {e}",
            context=exception_context(
                "load_features_from_bigquery", dataset=dataset_id, table=table_id
            ),
        ) from e

    # Convert categorical features to category dtype
    categorical_cols = [
        "area",
        "age_bucket",
        "space_efficiency",
        "area_price_tier",
        "postal_prefix",
        "stockholm_district",
        "market_cycle",
        "swedish_season",
        "school_period",
        "dom_momentum",
        "area_price_momentum",
        "architectural_era",
        "renovation_likelihood",
        "has_elevator",
        "has_balcony",
        "floor_tier",
    ]

    for col in categorical_cols:
        if col in df.columns:
            df[col] = df[col].astype("category")

    # Convert date columns
    if "sold_date" in df.columns:
        df["sold_date"] = pd.to_datetime(df["sold_date"], errors="coerce")
    if "feature_date" in df.columns:
        df["feature_date"] = pd.to_datetime(df["feature_date"], errors="coerce")

    return df
