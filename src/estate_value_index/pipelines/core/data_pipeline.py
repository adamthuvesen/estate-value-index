#!/usr/bin/env python3
"""Prefect flow for authorized Booli API ingestion and data loading."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from prefect import flow, get_run_logger, task

from estate_value_index.ingestion.booli.api import fetch_booli_api_window
from estate_value_index.pipelines.utils import get_task_logger
from estate_value_index.utils.gcs import GCSClient, is_gcs_enabled
from estate_value_index.utils.settings import get_min_ingestion_validation_rate

DEFAULT_BOOLI_CONFIG = Path("src/estate_value_index/ingestion/config/booli_all_locations.json")


@task(name="fetch-booli-api", retries=1, retry_delay_seconds=60)
def fetch_booli_api(
    max_pages: int = 10,
    config_file: str | None = None,
    output_file: Path | None = None,
) -> Path:
    """Fetch signed Booli API records into the raw-listing JSONL schema."""
    logger = get_task_logger("estate_value_index.ingestion")
    if output_file is None:
        output_dir = Path("data/raw/booli")
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"booli_listings_{timestamp}.jsonl"
    else:
        output_file.parent.mkdir(parents=True, exist_ok=True)
    resolved_config = Path(config_file) if config_file else DEFAULT_BOOLI_CONFIG
    logger.info("Fetching Booli API records (max_pages=%s, config=%s)", max_pages, resolved_config)
    result = fetch_booli_api_window(
        config_file=resolved_config,
        output_file=output_file,
        max_pages=max_pages,
    )
    logger.info("Fetched Booli API records to %s", result)
    return result


def _parse_listing_line(line: str, logger) -> dict[str, Any] | None:
    line = line.strip()
    if not line:
        return None

    try:
        record = json.loads(line)
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse line: {line[:100]}... Error: {e}")
        return None
    if not isinstance(record, dict):
        logger.warning("Skipping non-object JSONL record: %s", line[:100])
        return None
    return record


def _load_listing_records(file_path: Path, logger) -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = []
    with open(file_path) as f:
        for line in f:
            item = _parse_listing_line(line, logger)
            if item is not None:
                data.append(item)
    return data


def _missing_required_fields(item: dict, required_fields: list[str]) -> list[str]:
    return [
        field
        for field in required_fields
        if field not in item
        or item[field] is None
        or (isinstance(item[field], str) and not item[field].strip())
    ]


def _validation_summary(data: list[dict], required_fields: list[str]) -> dict:
    valid = 0
    missing_fields = set()

    for item in data:
        missing = _missing_required_fields(item, required_fields)
        if missing:
            missing_fields.update(missing)
        else:
            valid += 1

    total = len(data)
    return {
        "total_listings": total,
        "valid_listings": valid,
        "invalid_listings": total - valid,
        "validation_rate": valid / total if total > 0 else 0,
        "missing_fields": sorted(missing_fields),
    }


@task(name="validate-listings-data")
def validate_listings(file_path: Path, min_validation_rate: float | None = None) -> dict:
    """Validate ingested listing records.

    Args:
        file_path: Path to JSONL file

    Returns:
        Validation results dict
    """
    logger = get_task_logger(__name__)
    logger.info(f"Validating listings from {file_path}")

    data = _load_listing_records(file_path, logger)
    required_fields = ["listing_id", "sold_price", "living_area", "area"]
    min_validation_rate = (
        get_min_ingestion_validation_rate() if min_validation_rate is None else min_validation_rate
    )
    validation_result = _validation_summary(data, required_fields)

    logger.info(
        "Validation: %s/%s valid (%.1f%%)",
        validation_result["valid_listings"],
        validation_result["total_listings"],
        validation_result["validation_rate"] * 100,
    )

    if validation_result["total_listings"] == 0:
        raise RuntimeError(f"Ingestion produced zero listings: {file_path}")

    if validation_result["validation_rate"] < min_validation_rate:
        raise RuntimeError(
            "Ingestion validation rate "
            f"{validation_result['validation_rate']:.1%} is below "
            f"{min_validation_rate:.1%}"
        )

    return validation_result


@task(name="upload-to-gcs", retries=3, retry_delay_seconds=30)
def upload_to_gcs(file_path: Path, gcs_path: str = "raw/booli_listings_prod.json") -> str:
    """Upload file to GCS, plus a timestamped archive copy."""
    logger = get_run_logger()

    if not is_gcs_enabled():
        logger.warning("GCS not enabled, skipping upload")
        return str(file_path)

    gcs_client = GCSClient()
    logger.info(f"Uploading {file_path} to gs://{gcs_client.bucket_name}/{gcs_path}")
    gcs_uri = gcs_client.upload_file(file_path, gcs_path)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = f"raw/archive/booli_listings_{timestamp}.json"
    gcs_client.upload_file(file_path, archive_path)

    logger.info(f"Uploaded to {gcs_uri}; archived to gs://{gcs_client.bucket_name}/{archive_path}")
    return gcs_uri


@flow(name="Estate Value Index Booli API Ingestion", log_prints=True)
def ingest_booli_flow(
    max_pages: int = 10,
    upload_to_cloud: bool = True,
    config_file: str | None = None,
) -> dict:
    """Fetch Booli API listings, validate, and optionally upload to GCS."""
    logger = get_run_logger()
    logger.info("Starting Booli API ingestion flow")

    output_file = fetch_booli_api(max_pages, config_file)
    validation_results = validate_listings(output_file)

    gcs_uri = None
    if upload_to_cloud:
        gcs_uri = upload_to_gcs(output_file)

    results = {
        "output_file": str(output_file),
        "gcs_uri": gcs_uri,
        "validation": validation_results,
        "timestamp": datetime.now().isoformat(),
    }

    logger.info(f"Flow completed: {validation_results['valid_listings']} valid listings fetched")
    return results


def _pipeline_tasks() -> dict[str, Any]:
    from estate_value_index.pipelines.tasks import (
        geocode_new_addresses_task,
        materialize_features_task,
        process_listings_task,
        sync_bigquery_to_local_task,
        upload_to_bigquery_task,
        verify_sync_task,
    )

    return {
        "geocode_new_addresses": geocode_new_addresses_task,
        "materialize_features": materialize_features_task,
        "process_listings": process_listings_task,
        "sync_bigquery_to_local": sync_bigquery_to_local_task,
        "upload_to_bigquery": upload_to_bigquery_task,
        "verify_sync": verify_sync_task,
    }


def _run_ingestion_stage(
    logger,
    *,
    max_pages: int,
    config_file: str | None,
) -> tuple[Path, dict]:
    logger.info("Stage 1: Fetching listings from Booli API")
    output_file = fetch_booli_api(max_pages, config_file)
    validation_results = validate_listings(output_file)
    return output_file, validation_results


def _run_process_stage(logger, process_listings_task, output_file: Path) -> dict:
    logger.info("Stage 2: Processing listings (merge + clean + impute)")
    return process_listings_task(
        input_file=output_file,
        production_file=Path("data/raw/booli/booli_listings_prod.json"),
        dry_run=False,
    )


def _run_bigquery_upload_stage(
    logger,
    upload_to_bigquery_task,
    process_result: dict,
    *,
    upload_to_bq: bool,
) -> dict | None:
    if not upload_to_bq:
        return None

    logger.info("Stage 3: Uploading to BigQuery")
    return upload_to_bigquery_task(
        processed_file=Path(process_result["output_file"]),
        truncate=False,
    )


def _run_geocode_stage(logger, geocode_new_addresses_task, *, upload_to_bq: bool) -> dict | None:
    if not upload_to_bq:
        return None

    logger.info("Stage 3.5: Geocoding new addresses")
    geocode_result = geocode_new_addresses_task(batch_size=200)
    if geocode_result["new_addresses"] > 0:
        logger.info(
            f"   Geocoded {geocode_result['geocoded']}/{geocode_result['new_addresses']} new addresses"
        )
    else:
        logger.info("   No new addresses to geocode")
    return geocode_result


def _run_feature_materialization_stage(
    logger,
    materialize_features_task,
    *,
    materialize_features: bool,
    upload_to_bq: bool,
) -> dict | None:
    if not (materialize_features and upload_to_bq):
        return None

    logger.info("Stage 4: Materializing features in BigQuery")
    return materialize_features_task(truncate=True)


def _run_sync_stage(
    logger,
    sync_bigquery_to_local_task,
    verify_sync_task,
    *,
    sync_after_upload: bool,
    upload_to_bq: bool,
) -> dict | None:
    if not (sync_after_upload and upload_to_bq):
        return None

    logger.info("Stage 5: Syncing local file from BigQuery")
    sync_result = sync_bigquery_to_local_task()
    verify_result = verify_sync_task()

    if not verify_result.get("in_sync", False):
        raise RuntimeError(f"Sync verification failed: {verify_result}")

    logger.info(f"Sync complete: {sync_result.get('records_synced', 0)} listings")
    logger.info(f"   In sync: {verify_result.get('in_sync', False)}")

    sync_result["verification"] = verify_result
    return sync_result


def _run_gcs_backup_stage(logger, process_result: dict, *, upload_to_cloud: bool) -> str | None:
    if not upload_to_cloud:
        return None

    logger.info("Stage 6: Uploading to GCS (backup)")
    return upload_to_gcs(Path(process_result["output_file"]))


def _complete_ingestion_results(
    *,
    output_file: Path,
    validation_results: dict,
    process_result: dict,
    bq_result: dict | None,
    geocode_result: dict | None,
    feature_result: dict | None,
    sync_result: dict | None,
    gcs_uri: str | None,
) -> dict:
    return {
        "ingestion": {"output_file": str(output_file), "validation": validation_results},
        "processing": process_result,
        "bigquery": bq_result,
        "geocoding": geocode_result,
        "features": feature_result,
        "sync": sync_result,
        "gcs": {"uri": gcs_uri},
        "timestamp": datetime.now().isoformat(),
    }


def _log_complete_ingestion_summary(
    logger,
    *,
    validation_results: dict,
    process_result: dict,
    bq_result: dict | None,
    geocode_result: dict | None,
    feature_result: dict | None,
    sync_result: dict | None,
) -> None:
    logger.info("Complete ingestion pipeline finished")
    logger.info(f"   Fetched: {validation_results['valid_listings']} valid listings")
    logger.info(f"   Processed: {process_result.get('total_listings', 0)} total listings")
    if bq_result:
        logger.info(f"   BigQuery: {bq_result.get('rows_uploaded', 0)} rows uploaded")
    if geocode_result and geocode_result.get("success"):
        logger.info(f"   Geocoded: {geocode_result.get('geocoded', 0)} new addresses")
    if feature_result:
        logger.info(f"   Features: {feature_result.get('row_count', 0)} rows materialized")
    if sync_result and sync_result.get("success"):
        logger.info(f"   Synced: {sync_result.get('records_synced', 0)} listings to local file")
        if sync_result.get("verification"):
            logger.info(f"   Verified: {sync_result['verification'].get('in_sync', False)}")


@flow(name="Estate Value Index Complete Ingestion Pipeline", log_prints=True)
def complete_ingestion_flow(
    max_pages: int = 10,
    upload_to_bq: bool = True,
    materialize_features: bool = True,
    upload_to_cloud: bool = True,
    sync_after_upload: bool = True,
    config_file: str | None = None,
) -> dict:
    """Complete ingestion pipeline: Booli API → Process → BigQuery → Features → Sync.

    This flow extends the basic API ingestion flow with:
    - Processing (merge, clean, impute)
    - BigQuery upload
    - Feature materialization
    - Local file sync (BigQuery → local)
    - GCS backup

    Args:
        max_pages: Maximum API result pages to fetch
        upload_to_bq: Upload to BigQuery after processing
        materialize_features: Materialize features in BigQuery
        upload_to_cloud: Upload to GCS
        sync_after_upload: Sync local file from BigQuery after upload
        config_file: Optional path to config file (e.g., ingestion/config/booli_all_locations.json)

    Returns:
        Complete flow results dict
    """
    logger = get_run_logger()
    logger.info("Starting complete Booli API ingestion pipeline")
    tasks = _pipeline_tasks()

    output_file, validation_results = _run_ingestion_stage(
        logger,
        max_pages=max_pages,
        config_file=config_file,
    )
    process_result = _run_process_stage(logger, tasks["process_listings"], output_file)
    bq_result = _run_bigquery_upload_stage(
        logger,
        tasks["upload_to_bigquery"],
        process_result,
        upload_to_bq=upload_to_bq,
    )
    geocode_result = _run_geocode_stage(
        logger,
        tasks["geocode_new_addresses"],
        upload_to_bq=upload_to_bq,
    )
    feature_result = _run_feature_materialization_stage(
        logger,
        tasks["materialize_features"],
        materialize_features=materialize_features,
        upload_to_bq=upload_to_bq,
    )
    sync_result = _run_sync_stage(
        logger,
        tasks["sync_bigquery_to_local"],
        tasks["verify_sync"],
        sync_after_upload=sync_after_upload,
        upload_to_bq=upload_to_bq,
    )
    gcs_uri = _run_gcs_backup_stage(logger, process_result, upload_to_cloud=upload_to_cloud)

    results = _complete_ingestion_results(
        output_file=output_file,
        validation_results=validation_results,
        process_result=process_result,
        bq_result=bq_result,
        geocode_result=geocode_result,
        feature_result=feature_result,
        sync_result=sync_result,
        gcs_uri=gcs_uri,
    )
    _log_complete_ingestion_summary(
        logger,
        validation_results=validation_results,
        process_result=process_result,
        bq_result=bq_result,
        geocode_result=geocode_result,
        feature_result=feature_result,
        sync_result=sync_result,
    )

    return results


if __name__ == "__main__":
    # Run flow locally for testing
    result = ingest_booli_flow(max_pages=5, upload_to_cloud=False)
    print(json.dumps(result, indent=2))
