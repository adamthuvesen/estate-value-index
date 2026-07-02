#!/usr/bin/env python3
"""Prefect flow for automated Booli scraping and data upload to GCS."""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from prefect import flow, get_run_logger, task

from estate_value_index.pipelines.utils import get_task_logger
from estate_value_index.utils.gcs import GCSClient, is_gcs_enabled


def _blocked_status_from_scrapy_output(output: str) -> str | None:
    block_markers = {
        "403": ("403 Forbidden", "<403"),
        "429": ("429 Too Many Requests", "<429", "429 retries exhausted"),
    }
    for status, markers in block_markers.items():
        if any(marker in output for marker in markers):
            return status
    return None


def _read_new_scrapy_log(log_file: Path, start_offset: int) -> str:
    if not log_file.exists():
        return ""
    try:
        with log_file.open("rb") as file:
            file.seek(start_offset)
            return file.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


@task(name="run-scrapy-spider", retries=1, retry_delay_seconds=60)
def run_scrapy_spider(
    max_pages: int = 10,
    concurrent_requests: int = 4,
    delay: float = 0.1,
    config_file: str | None = None,
    start_page: int | None = None,
    output_file: Path | None = None,
) -> Path:
    """Run Scrapy spider to collect listings.

    Args:
        max_pages: Maximum number of pages to scrape
        concurrent_requests: Number of concurrent requests
        delay: Download delay in seconds
        config_file: Optional path to config file (e.g., ingestion/config/booli_solna_sundbyberg.json)
        start_page: Optional start page for the spider (defaults to spider's default)
        output_file: Optional path to output JSONL file

    Returns:
        Path to output JSONL file
    """
    logger = get_task_logger("estate_value_index.scraper")
    logger.info(
        "Starting Scrapy spider (max_pages=%s, start_page=%s, concurrent=%s, config=%s)",
        max_pages,
        start_page,
        concurrent_requests,
        config_file,
    )

    Path("logs/ingestion").mkdir(parents=True, exist_ok=True)
    scrapy_log_file = Path(os.getenv("BOOLI_LOG_FILE", "logs/ingestion/booli.log"))
    scrapy_log_start = scrapy_log_file.stat().st_size if scrapy_log_file.exists() else 0

    if output_file is None:
        output_dir = Path("data/raw/booli")
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # .jsonl: one JSON object per line, no enclosing array.
        output_file = output_dir / f"booli_listings_{timestamp}.jsonl"
    else:
        output_file.parent.mkdir(parents=True, exist_ok=True)
    output_target = f"{output_file}:jsonlines"

    cmd = [
        sys.executable,
        "-m",
        "scrapy",
        "crawl",
        "-s",
        f"DOWNLOAD_DELAY={delay}",
        "-s",
        f"CONCURRENT_REQUESTS={concurrent_requests}",
        "-o",
        output_target,
        "-a",
        f"max_pages={max_pages}",
    ]
    if start_page is not None:
        cmd.extend(["-a", f"start_page={start_page}"])
    if config_file:
        cmd.extend(["-a", f"config_file={config_file}"])
    # Spider name last to avoid CLI parsing issues
    cmd.append("booli")

    logger.info(f"Running command: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        timeout=3600,
    )

    if result.returncode != 0:
        logger.error(f"Scrapy failed: {result.stderr}")
        raise RuntimeError(f"Scrapy spider failed with code {result.returncode}")

    blocked_status = _blocked_status_from_scrapy_output(
        "\n".join(
            part
            for part in (
                result.stdout,
                result.stderr,
                _read_new_scrapy_log(scrapy_log_file, scrapy_log_start),
            )
            if part
        )
    )
    if blocked_status is not None:
        logger.error("Booli scrape blocked with HTTP %s", blocked_status)
        raise RuntimeError(f"Booli scrape blocked with HTTP {blocked_status}")

    if not output_file.exists():
        raise FileNotFoundError(f"Output file not created: {output_file}")

    with open(output_file) as f:
        listing_count = sum(1 for line in f if line.strip())

    logger.info(f"Scraped {listing_count} listings to {output_file}")
    return output_file


def _parse_listing_line(line: str, logger) -> dict | None:
    line = line.strip()
    if not line or line in ["[", "]"]:
        return None
    if line.endswith(","):
        line = line[:-1]

    try:
        return json.loads(line)
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse line: {line[:100]}... Error: {e}")
        return None


def _load_listing_records(file_path: Path, logger) -> list[dict]:
    data = []
    with open(file_path) as f:
        for line in f:
            item = _parse_listing_line(line, logger)
            if item is not None:
                data.append(item)
    return data


def _missing_required_fields(item: dict, required_fields: list[str]) -> list[str]:
    return [field for field in required_fields if field not in item or item[field] is None]


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
        "missing_fields": list(missing_fields),
    }


@task(name="validate-listings-data")
def validate_listings(file_path: Path) -> dict:
    """Validate scraped listings data.

    Args:
        file_path: Path to JSONL file

    Returns:
        Validation results dict
    """
    logger = get_run_logger()
    logger.info(f"Validating listings from {file_path}")

    data = _load_listing_records(file_path, logger)
    required_fields = ["listing_id", "sold_price", "living_area", "area"]
    validation_result = _validation_summary(data, required_fields)

    logger.info(
        "Validation: %s/%s valid (%.1f%%)",
        validation_result["valid_listings"],
        validation_result["total_listings"],
        validation_result["validation_rate"] * 100,
    )

    if validation_result["validation_rate"] < 0.5:
        logger.warning(f"Low validation rate: {validation_result['validation_rate']:.1%}")

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


@flow(name="Estate Value Index Scraper", log_prints=True)
def scrape_booli_flow(
    max_pages: int = 10,
    concurrent_requests: int = 4,
    delay: float = 0.1,
    upload_to_cloud: bool = True,
    config_file: str | None = None,
) -> dict:
    """Scrape Booli listings, validate, and optionally upload to GCS."""
    logger = get_run_logger()
    logger.info("Starting Booli scraping flow")

    output_file = run_scrapy_spider(max_pages, concurrent_requests, delay, config_file)
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

    logger.info(f"Flow completed: {validation_results['valid_listings']} valid listings scraped")
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


def _run_scrape_stage(
    logger,
    *,
    max_pages: int,
    concurrent_requests: int,
    delay: float,
    config_file: str | None,
) -> tuple[Path, dict]:
    logger.info("Stage 1: Scraping listings")
    output_file = run_scrapy_spider(max_pages, concurrent_requests, delay, config_file)
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
    try:
        geocode_result = geocode_new_addresses_task(batch_size=200)
        if geocode_result["new_addresses"] > 0:
            logger.info(
                f"   Geocoded {geocode_result['geocoded']}/{geocode_result['new_addresses']} new addresses"
            )
        else:
            logger.info("   No new addresses to geocode")
        return geocode_result
    except Exception as e:
        logger.warning(f"Geocoding failed but continuing: {e}")
        return {"error": str(e), "success": False}


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
    try:
        sync_result = sync_bigquery_to_local_task()
        verify_result = verify_sync_task()

        logger.info(f"Sync complete: {sync_result.get('listings_count', 0)} listings")
        logger.info(f"   In sync: {verify_result.get('in_sync', False)}")

        sync_result["verification"] = verify_result
        return sync_result
    except Exception as e:
        logger.warning(f"Sync failed but continuing: {e}")
        return {"error": str(e), "success": False}


def _run_gcs_backup_stage(logger, process_result: dict, *, upload_to_cloud: bool) -> str | None:
    if not upload_to_cloud:
        return None

    logger.info("Stage 6: Uploading to GCS (backup)")
    return upload_to_gcs(Path(process_result["output_file"]))


def _complete_scrape_results(
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
        "scraping": {"output_file": str(output_file), "validation": validation_results},
        "processing": process_result,
        "bigquery": bq_result,
        "geocoding": geocode_result,
        "features": feature_result,
        "sync": sync_result,
        "gcs": {"uri": gcs_uri},
        "timestamp": datetime.now().isoformat(),
    }


def _log_complete_scrape_summary(
    logger,
    *,
    validation_results: dict,
    process_result: dict,
    bq_result: dict | None,
    geocode_result: dict | None,
    feature_result: dict | None,
    sync_result: dict | None,
) -> None:
    logger.info("Complete scraping pipeline finished")
    logger.info(f"   Scraped: {validation_results['valid_listings']} valid listings")
    logger.info(f"   Processed: {process_result.get('total_listings', 0)} total listings")
    if bq_result:
        logger.info(f"   BigQuery: {bq_result.get('uploaded', 0)} rows uploaded")
    if geocode_result and geocode_result.get("success"):
        logger.info(f"   Geocoded: {geocode_result.get('geocoded', 0)} new addresses")
    if feature_result:
        logger.info(f"   Features: {feature_result.get('row_count', 0)} rows materialized")
    if sync_result and sync_result.get("success"):
        logger.info(f"   Synced: {sync_result.get('listings_count', 0)} listings to local file")
        if sync_result.get("verification"):
            logger.info(f"   Verified: {sync_result['verification'].get('in_sync', False)}")


@flow(name="Estate Value Index Complete Scraping Pipeline", log_prints=True)
def complete_scrape_flow(
    max_pages: int = 10,
    concurrent_requests: int = 4,
    delay: float = 0.1,
    upload_to_bq: bool = True,
    materialize_features: bool = True,
    upload_to_cloud: bool = True,
    sync_after_upload: bool = True,
    config_file: str | None = None,
) -> dict:
    """Complete scraping pipeline: Scrape → Process → BigQuery → Features → Sync.

    This flow extends the basic scraping flow with:
    - Processing (merge, clean, impute)
    - BigQuery upload
    - Feature materialization
    - Local file sync (BigQuery → local)
    - GCS backup

    Args:
        max_pages: Maximum pages to scrape
        concurrent_requests: Concurrent request limit
        delay: Download delay
        upload_to_bq: Upload to BigQuery after processing
        materialize_features: Materialize features in BigQuery
        upload_to_cloud: Upload to GCS
        sync_after_upload: Sync local file from BigQuery after upload
        config_file: Optional path to config file (e.g., ingestion/config/booli_solna_sundbyberg.json)

    Returns:
        Complete flow results dict
    """
    logger = get_run_logger()
    logger.info("Starting complete scraping pipeline")
    tasks = _pipeline_tasks()

    output_file, validation_results = _run_scrape_stage(
        logger,
        max_pages=max_pages,
        concurrent_requests=concurrent_requests,
        delay=delay,
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

    results = _complete_scrape_results(
        output_file=output_file,
        validation_results=validation_results,
        process_result=process_result,
        bq_result=bq_result,
        geocode_result=geocode_result,
        feature_result=feature_result,
        sync_result=sync_result,
        gcs_uri=gcs_uri,
    )
    _log_complete_scrape_summary(
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
    result = scrape_booli_flow(max_pages=5, upload_to_cloud=False)
    print(json.dumps(result, indent=2))
