"""Tasks for syncing data between BigQuery, local storage, and GCS."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from prefect import task

from estate_value_index.exceptions import DataError
from estate_value_index.pipelines.types import SyncResult
from estate_value_index.pipelines.utils import get_bq_config, get_task_logger


@task(
    name="sync-bigquery-to-local",
    description="Download data from BigQuery to local JSONL file",
    retries=3,
    retry_delay_seconds=30,
    timeout_seconds=900,
)
def sync_bigquery_to_local_task(
    output_file: Path | None = None,
    project_id: str | None = None,
    dataset_id: str | None = None,
    table_id: str | None = None,
    backup_existing: bool = True,
) -> SyncResult:
    """Download all data from BigQuery and sync to local file.

    Args:
        output_file: Local file to write to
        project_id: GCP project ID (default: from env)
        dataset_id: BigQuery dataset (default: booli_raw)
        table_id: BigQuery table (default: listings)
        backup_existing: Create backup of existing file before overwriting

    Returns:
        SyncResult with sync statistics
    """
    logger = get_task_logger(__name__)

    bq_config = get_bq_config(project_id, dataset_id, table_id)
    client = bq_config.client
    table_ref = bq_config.full_table_id

    if output_file is None:
        output_file = Path("data/raw/booli/booli_listings_prod.json")
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Syncing from {table_ref} to {output_file}")

    query = f"SELECT * FROM `{table_ref}` ORDER BY scraped_at DESC"
    results = client.query(query).result()

    listings = [dict(row.items()) for row in results]

    logger.info(f"Downloaded {len(listings)} listings from BigQuery")

    def _json_default(value: Any) -> Any:
        # Match the previous per-cell `.isoformat()` walk's output exactly:
        # `str(datetime)` would emit "2024-01-15 10:30:00" (space separator),
        # but downstream consumers expect ISO-T form. Routing through a JSON
        # default still removes the per-cell pre-walk while preserving format.
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    # Backup existing file
    if backup_existing and output_file.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = (
            output_file.parent / f"{output_file.stem}_backup_{timestamp}{output_file.suffix}"
        )
        logger.info(f"Creating backup: {backup_file}")
        output_file.rename(backup_file)

    # Write JSONL
    with open(output_file, "w", encoding="utf-8") as f:
        for listing in listings:
            f.write(json.dumps(listing, ensure_ascii=False, default=_json_default) + "\n")

    # Verify
    with open(output_file, encoding="utf-8") as f:
        verify_count = sum(1 for line in f if line.strip())

    if verify_count != len(listings):
        raise DataError(
            f"Verification mismatch: wrote {len(listings)} but verified {verify_count}",
            context={"expected": len(listings), "verified": verify_count, "file": str(output_file)},
        )

    logger.info(f"Sync complete: {len(listings)} listings")

    return SyncResult(
        success=True,
        timestamp=datetime.now().isoformat(),
        source=table_ref,
        destination=str(output_file),
        records_synced=len(listings),
    )


@task(
    name="sync-local-to-gcs",
    description="Upload local file to GCS backup",
    retries=3,
    retry_delay_seconds=30,
    timeout_seconds=300,
)
def sync_local_to_gcs_task(
    local_file: Path | None = None,
    gcs_path: str = "raw/booli_listings_prod.json",
) -> SyncResult:
    """Upload local file to GCS as backup.

    Args:
        local_file: Local file to upload
        gcs_path: GCS destination path

    Returns:
        SyncResult with upload statistics
    """
    logger = get_task_logger(__name__)

    if local_file is None:
        local_file = Path("data/raw/booli/booli_listings_prod.json")
    local_file = Path(local_file)

    if not local_file.exists():
        raise FileNotFoundError(f"Local file not found: {local_file}")

    logger.info(f"Uploading {local_file} to GCS")

    from estate_value_index.utils.gcs import GCSClient, is_gcs_enabled

    if not is_gcs_enabled():
        logger.warning("GCS not enabled, skipping upload")
        return SyncResult(
            success=True,
            timestamp=datetime.now().isoformat(),
            source=str(local_file),
            destination="gcs://disabled",
            records_synced=0,
        )

    gcs_client = GCSClient()
    gcs_uri = gcs_client.upload_file(local_file, gcs_path)

    # Also create timestamped archive
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = f"raw/archive/booli_listings_{timestamp}.json"
    gcs_client.upload_file(local_file, archive_path)

    # Count records for result
    with open(local_file, encoding="utf-8") as f:
        record_count = sum(1 for line in f if line.strip())

    logger.info(f"Upload complete: {gcs_uri}")

    return SyncResult(
        success=True,
        timestamp=datetime.now().isoformat(),
        source=str(local_file),
        destination=gcs_uri,
        records_synced=record_count,
    )


@task(
    name="verify-sync",
    description="Verify that local file and BigQuery are in sync",
    retries=2,
    retry_delay_seconds=10,
)
def verify_sync_task(
    local_file: Path | None = None,
    project_id: str | None = None,
    dataset_id: str | None = None,
    table_id: str | None = None,
) -> dict:
    """Verify that local file and BigQuery have the same number of records.

    Args:
        local_file: Local file to verify
        project_id: GCP project ID
        dataset_id: BigQuery dataset
        table_id: BigQuery table

    Returns:
        Verification results with in_sync status
    """
    logger = get_task_logger(__name__)

    bq_config = get_bq_config(project_id, dataset_id, table_id)
    client = bq_config.client
    table_ref = bq_config.full_table_id

    if local_file is None:
        local_file = Path("data/raw/booli/booli_listings_prod.json")
    local_file = Path(local_file)

    logger.info(f"Verifying sync between {local_file} and {table_ref}")

    # Count local records
    with open(local_file, encoding="utf-8") as f:
        local_count = sum(1 for line in f if line.strip())

    # Count BigQuery records
    query = f"SELECT COUNT(*) as count FROM `{table_ref}`"
    bq_count = list(client.query(query).result())[0]["count"]

    in_sync = local_count == bq_count
    difference = abs(local_count - bq_count)

    if in_sync:
        logger.info(f"Files are in sync: {local_count} listings")
    else:
        logger.warning(f"OUT OF SYNC: local={local_count}, BigQuery={bq_count} (diff={difference})")

    return {
        "success": True,
        "in_sync": in_sync,
        "local_count": local_count,
        "bigquery_count": bq_count,
        "difference": difference,
        "timestamp": datetime.now().isoformat(),
    }
