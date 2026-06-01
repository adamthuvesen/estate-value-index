"""Feature materialization utilities for BigQuery.

This module provides functions for:
- Preparing feature rows for BigQuery
- Materializing engineered features to BigQuery
- Joining listings with geocodes for distance features
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from estate_value_index.exceptions import BigQueryError, exception_context
from estate_value_index.ml import create_optimized_features, filter_valid_listings
from estate_value_index.ml.data_loader import load_from_bigquery
from estate_value_index.ml.features import CATEGORICAL_FEATURE_NAMES, NUMERIC_FEATURE_NAMES
from estate_value_index.ml.preprocessing import normalize_area_for_model
from estate_value_index.utils.clients import get_bq_client
from estate_value_index.utils.settings import bq_table, get_batch_size, load_env_config

logger = logging.getLogger(__name__)


def join_geocodes(
    df: pd.DataFrame,
    project_id: str,
    geocodes_dataset: str = "booli_raw",
    geocodes_table: str = "geocodes",
) -> pd.DataFrame:
    """Join listings with geocodes to add lat/lon columns.

    Args:
        df: DataFrame with listings (must have 'address' and 'area' columns)
        project_id: GCP project ID
        geocodes_dataset: BigQuery dataset containing geocodes table
        geocodes_table: BigQuery table name for geocodes

    Returns:
        DataFrame with lat/lon columns added
    """
    if "address" not in df.columns or "area" not in df.columns:
        logger.warning("Missing address/area columns, skipping geocode join")
        return df

    # Load geocodes from BigQuery
    client = get_bq_client(project_id)
    geocodes_table_id = f"{project_id}.{geocodes_dataset}.{geocodes_table}"

    try:
        geocodes_df = client.query(
            f"SELECT address, lat, lon FROM `{geocodes_table_id}`"
        ).to_dataframe()
        logger.info("Loaded %d geocodes from BigQuery", len(geocodes_df))
    except Exception as e:
        # Swallowing this would silently train a model without distance
        # features. Fail loud so materialization stops instead of emitting a
        # partially-featured dataset.
        logger.warning("Failed to load geocodes: %s", e)
        raise BigQueryError(
            f"Failed to load geocodes from {geocodes_table_id}: {e}",
            context=exception_context("join_geocodes", table=geocodes_table_id),
        ) from e

    # Create address key for joining
    # Format: "Street Address, normalized_area"
    df = df.copy()
    df["_normalized_area"] = df["area"].apply(
        lambda v: normalize_area_for_model(v, empty_for_unknown=True) if pd.notna(v) else ""
    )
    df["_geocode_key"] = df["address"].astype(str) + ", " + df["_normalized_area"]

    # Join with geocodes
    geocodes_df = geocodes_df.rename(columns={"address": "_geocode_key"})
    df = df.merge(geocodes_df, on="_geocode_key", how="left")

    # Clean up
    df = df.drop(columns=["_geocode_key", "_normalized_area"])

    matched = df["lat"].notna().sum()
    total = len(df)
    logger.info("Geocode match rate: %d/%d (%.1f%%)", matched, total, 100 * matched / total)

    return df


def prepare_feature_rows(df_engineered: pd.DataFrame, feature_date: date) -> list[dict[str, Any]]:
    """Convert engineered features DataFrame to BigQuery-compatible rows.

    Args:
        df_engineered: DataFrame with engineered features
        feature_date: Date features were computed

    Returns:
        List of dictionaries ready for BigQuery insertion
    """
    required_cols = ["listing_id", "sold_price", "sold_date"]
    feature_cols = list(NUMERIC_FEATURE_NAMES) + list(CATEGORICAL_FEATURE_NAMES)

    for col in required_cols:
        if col not in df_engineered.columns:
            if col == "listing_id":
                raise ValueError("listing_id column is required but missing")
            df_engineered[col] = None

    all_cols = required_cols + feature_cols
    available_cols = [c for c in all_cols if c in df_engineered.columns]
    df_subset = df_engineered[available_cols].copy()

    # `feature_date` and `sold_date` need to be ISO strings: `insert_rows_json`
    # below serialises via stdlib JSON which can't encode `datetime.date`.
    df_subset["feature_date"] = (
        feature_date.isoformat() if isinstance(feature_date, date) else feature_date
    )

    if "sold_date" in df_subset.columns:
        sold_dt = pd.to_datetime(df_subset["sold_date"], errors="coerce")
        df_subset["sold_date"] = sold_dt.dt.strftime("%Y-%m-%d").where(sold_dt.notna(), None)

    # Vectorise the cleanup that the per-cell loop used to do row-by-row:
    # 1. Coerce numeric NaN/+-inf to None at the column level.
    # 2. Coerce categorical "nan" strings to None.
    # That lets `to_dict("records")` emit BigQuery-ready dicts directly.
    numeric_cols = df_subset.select_dtypes(include=[np.number]).columns
    if len(numeric_cols):
        cleaned = df_subset[numeric_cols].replace([np.inf, -np.inf], np.nan)
        df_subset[numeric_cols] = cleaned.astype(object).where(cleaned.notna(), None)

    for col in CATEGORICAL_FEATURE_NAMES:
        if col in df_subset.columns:
            df_subset[col] = df_subset[col].astype(str)
            df_subset[col] = df_subset[col].replace("nan", None)

    return df_subset.to_dict("records")


def materialize_features(
    project_id: str | None = None,
    dry_run: bool = False,
    truncate: bool = False,
    batch_size: int | None = None,
) -> dict[str, Any]:
    """Materialize engineered features to BigQuery.

    Args:
        project_id: GCP project ID. If None, uses environment config.
        dry_run: If True, compute features but don't upload
        truncate: If True, clear existing features before uploading
        batch_size: Number of rows to insert per batch. If None, uses config.

    Returns:
        Dictionary with materialization results
    """
    env_config = load_env_config()

    project_id = project_id or env_config.bigquery_project_id
    batch_size = batch_size or get_batch_size()

    logger.info(
        "Starting feature materialization (project=%s, dry_run=%s, truncate=%s)",
        project_id,
        dry_run,
        truncate,
    )

    logger.info("Loading raw data from BigQuery")
    df_raw = load_from_bigquery(project_id=project_id)
    logger.info("Loaded %d raw listings", len(df_raw))

    logger.info("Joining with geocodes for distance features")
    df_raw = join_geocodes(df_raw, project_id)

    logger.info("Filtering valid listings")
    df_filtered = filter_valid_listings(df_raw, min_price=3000000, drop_na_features=False)
    logger.info("After filtering: %d listings", len(df_filtered))

    logger.info("Engineering features")
    df_engineered = create_optimized_features(df_filtered)
    logger.info("Engineered %d total columns", len(df_engineered.columns))

    numeric_count = sum(1 for f in NUMERIC_FEATURE_NAMES if f in df_engineered.columns)
    categorical_count = sum(1 for f in CATEGORICAL_FEATURE_NAMES if f in df_engineered.columns)
    logger.info(
        "Feature counts: numeric=%d/%d, categorical=%d/%d",
        numeric_count,
        len(NUMERIC_FEATURE_NAMES),
        categorical_count,
        len(CATEGORICAL_FEATURE_NAMES),
    )

    logger.info("Preparing data for BigQuery")
    feature_date = date.today()
    rows = prepare_feature_rows(df_engineered, feature_date)
    logger.info("Prepared %d rows", len(rows))

    if dry_run:
        logger.info("Dry run: features computed but not uploaded")
        if rows:
            sample = dict(list(rows[0].items())[:10])
            logger.info("Sample row (first 10 fields): %s", sample)
        return {
            "row_count": len(rows),
            "dry_run": True,
            "feature_date": str(feature_date),
            "numeric_features": numeric_count,
            "categorical_features": categorical_count,
        }

    logger.info("Connecting to BigQuery")
    client = get_bq_client(project_id)

    dataset_id = env_config.bq_dataset_features
    table_id = env_config.bq_table_features
    full_table_id = bq_table(project_id, dataset_id, table_id)

    if truncate:
        from uuid import uuid4

        staging_id = f"{full_table_id}_staging_{uuid4().hex[:8]}"
        upload_target = staging_id
        logger.info("Uploading to staging table %s (production swap on success)", staging_id)
    else:
        staging_id = None
        upload_target = full_table_id
        logger.info("Uploading %d rows to %s", len(rows), full_table_id)

    total_batches = (len(rows) + batch_size - 1) // batch_size
    all_errors: list[Any] = []

    try:
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            batch_num = (i // batch_size) + 1

            errors = client.insert_rows_json(upload_target, batch)

            if errors:
                logger.error(
                    "Batch %d/%d: errors occurred (first 3): %s",
                    batch_num,
                    total_batches,
                    errors[:3],
                )
                all_errors.extend(errors)
            else:
                logger.info("Batch %d/%d: %d rows inserted", batch_num, total_batches, len(batch))

        if all_errors:
            raise RuntimeError(
                f"insert failed: {len(all_errors)} batch error(s); first: {all_errors[0]}"
            )

        if staging_id is not None:
            logger.info("Verifying staging row count")
            count_query = f"SELECT COUNT(*) as count FROM `{staging_id}`"
            staging_count = list(client.query(count_query).result())[0]["count"]
            if staging_count != len(rows):
                raise RuntimeError(
                    f"staging row count mismatch: expected {len(rows)}, got {staging_count}"
                )

            logger.info(
                "Swapping staging → production via CREATE OR REPLACE TABLE %s", full_table_id
            )
            swap_sql = f"CREATE OR REPLACE TABLE `{full_table_id}` AS SELECT * FROM `{staging_id}`"
            client.query(swap_sql).result()
            row_count = staging_count
        else:
            logger.info("Verifying data")
            count_query = f"SELECT COUNT(*) as count FROM `{full_table_id}`"
            row_count = list(client.query(count_query).result())[0]["count"]

        logger.info("BigQuery table has %d rows", row_count)
    finally:
        if staging_id is not None:
            client.delete_table(staging_id, not_found_ok=True)

    logger.info(
        "Materialization complete: rows=%d, feature_date=%s, numeric=%d, categorical=%d",
        len(rows),
        feature_date,
        numeric_count,
        categorical_count,
    )

    return {
        "row_count": row_count,
        "feature_date": str(feature_date),
        "numeric_features": numeric_count,
        "categorical_features": categorical_count,
    }
