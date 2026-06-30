"""Tasks for data ingestion: processing, BigQuery upload, and geocoding."""

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

from prefect import task

from estate_value_index.exceptions import InfrastructureError
from estate_value_index.pipelines.types import ProcessingResult, UploadResult
from estate_value_index.pipelines.utils import get_bq_config, get_task_logger
from estate_value_index.utils.bigquery_safety import quote_identifier, safe_table_ref
from estate_value_index.utils.clients import get_bq_client


class GeocodeResult(TypedDict):
    """Result from geocoding task."""

    success: bool
    timestamp: str
    new_addresses: int
    geocoded: int
    failed: int
    skipped: int


@task(
    name="process-listings",
    description="Process scraped listings: merge, clean areas, impute missing values",
    retries=2,
    retry_delay_seconds=30,
    timeout_seconds=600,
)
def process_listings_task(
    input_file: Path,
    production_file: Path | None = None,
    output_file: Path | None = None,
    min_area_count: int = 5,
    days_threshold: int = 1000,
    dry_run: bool = False,
) -> ProcessingResult:
    """Process scraped listings using unified processing pipeline.

    Performs:
    1. Merge new listings with existing production data (deduplication)
    2. Clean and standardize area names
    3. Impute days_on_market values > threshold using area-based medians

    Args:
        input_file: Path to new scraped listings file
        production_file: Path to existing production data (optional)
        output_file: Path to write processed data (defaults to production_file)
        min_area_count: Minimum listings per area for consolidation
        days_threshold: Threshold for days_on_market imputation
        dry_run: If True, don't write output file

    Returns:
        ProcessingResult with processing statistics
    """
    logger = get_task_logger(__name__)

    if dry_run:
        return ProcessingResult(
            success=True,
            timestamp=datetime.now().isoformat(),
            input_file=str(input_file),
            output_file=str(output_file or production_file or input_file),
            total_listings=0,
            dry_run=True,
        )

    from estate_value_index.ingestion.processing import process_pipeline

    if production_file is None:
        production_file = Path("data/raw/booli/booli_listings_prod.json")
    if output_file is None:
        output_file = production_file

    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    logger.info(f"Processing listings from {input_file}")

    process_pipeline(
        input_file=input_file,
        production_file=production_file,
        output_file=output_file,
        min_area_count=min_area_count,
        days_threshold=days_threshold,
        dry_run=dry_run,
    )

    # Count results
    total_listings = 0
    if output_file.exists():
        with open(output_file, encoding="utf-8") as f:
            total_listings = sum(1 for line in f if line.strip())

    logger.info(f"Processing complete: {total_listings} listings")

    return ProcessingResult(
        success=True,
        timestamp=datetime.now().isoformat(),
        input_file=str(input_file),
        output_file=str(output_file),
        total_listings=total_listings,
        dry_run=dry_run,
    )


def _load_unique_bq_rows(processed_file: Path, prepare_bq_row) -> list[dict]:
    listings = []
    seen_ids: set[str] = set()

    with open(processed_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            raw_listing = json.loads(line)
            listing_id = raw_listing.get("listing_id")
            if listing_id in seen_ids:
                continue
            if listing_id:
                seen_ids.add(listing_id)
            listings.append(prepare_bq_row(raw_listing))

    return listings


def _temp_table_ref(bq_config) -> str:
    temp_table_id = f"{bq_config.table_id}_temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return safe_table_ref(bq_config.project_id, bq_config.dataset_id, temp_table_id)


def _load_temp_table(client, bigquery, temp_table_ref: str, listings: list[dict], schema) -> None:
    temp_table = bigquery.Table(temp_table_ref, schema=schema)
    client.create_table(temp_table)

    load_job = client.load_table_from_json(
        listings,
        temp_table_ref,
        job_config=bigquery.LoadJobConfig(schema=schema, write_disposition="WRITE_TRUNCATE"),
    )
    load_job.result()


def _merge_query(table_ref: str, temp_table_ref: str, schema, *, update_existing: bool) -> str:
    insert_fields = ", ".join(quote_identifier(field.name) for field in schema)
    insert_values = ", ".join(f"source.{quote_identifier(field.name)}" for field in schema)
    insert_clause = f"WHEN NOT MATCHED THEN INSERT ({insert_fields}) VALUES ({insert_values})"

    if not update_existing:
        matched_clause = ""
    else:
        field_names = [field.name for field in schema if field.name != "listing_id"]
        update_clause = ", ".join(
            f"target.{quote_identifier(f)} = source.{quote_identifier(f)}" for f in field_names
        )
        matched_clause = f"WHEN MATCHED THEN UPDATE SET {update_clause}"

    return f"""
        MERGE `{table_ref}` AS target
        USING `{temp_table_ref}` AS source
        ON target.listing_id = source.listing_id
        {matched_clause}
        {insert_clause}
        """


def _merge_dml_counts(merge_job) -> tuple[int, int]:
    stats = merge_job._properties.get("statistics", {}).get("query", {}).get("dmlStats", {})
    return int(stats.get("insertedRowCount", 0)), int(stats.get("updatedRowCount", 0))


def _execute_merge(client, table_ref: str, temp_table_ref: str, schema, *, update_existing: bool):
    merge_job = client.query(
        _merge_query(
            table_ref,
            temp_table_ref,
            schema,
            update_existing=update_existing,
        )
    )
    merge_job.result()
    return _merge_dml_counts(merge_job)


def _merge_temp_table(
    logger, client, table_ref: str, temp_table_ref: str, schema
) -> tuple[int, int]:
    try:
        return _execute_merge(client, table_ref, temp_table_ref, schema, update_existing=True)
    except Exception as e:
        if "streaming buffer" not in str(e).lower():
            raise

        logger.warning("Streaming buffer conflict - falling back to INSERT-only mode")
        inserted_rows, _ = _execute_merge(
            client,
            table_ref,
            temp_table_ref,
            schema,
            update_existing=False,
        )
        return inserted_rows, 0


@task(
    name="upload-to-bigquery",
    description="Upload processed listings to BigQuery",
    retries=3,
    retry_delay_seconds=60,
    timeout_seconds=900,
)
def upload_to_bigquery_task(
    processed_file: Path,
    project_id: str | None = None,
    dataset_id: str | None = None,
    table_id: str | None = None,
    truncate: bool = False,
) -> UploadResult:
    """Upload processed listings to BigQuery.

    Uses MERGE-based upsert with listing_id as primary key to prevent duplicates.

    Args:
        processed_file: Path to processed JSONL file
        project_id: GCP project ID (default: from env)
        dataset_id: BigQuery dataset (default: booli_raw)
        table_id: BigQuery table (default: listings)
        truncate: If True, truncate table before upload

    Returns:
        UploadResult with upload statistics
    """
    logger = get_task_logger(__name__)

    # Check file exists FIRST (before any GCP operations that require credentials)
    if not processed_file.exists():
        raise FileNotFoundError(f"Processed file not found: {processed_file}")

    from google.cloud import bigquery

    from estate_value_index.ingestion.bigquery_upload import prepare_bq_row

    bq_config = get_bq_config(project_id, dataset_id, table_id)
    client = bq_config.client
    table_ref = bq_config.full_table_id

    logger.info(f"Uploading to BigQuery: {table_ref}")

    if truncate:
        logger.info(f"Truncating table {table_ref}")
        client.query(f"TRUNCATE TABLE `{table_ref}`").result()

    listings = _load_unique_bq_rows(processed_file, prepare_bq_row)
    logger.info(f"Loaded {len(listings)} unique listings from file")

    temp_table_ref = _temp_table_ref(bq_config)

    try:
        target_table = client.get_table(table_ref)
        _load_temp_table(client, bigquery, temp_table_ref, listings, target_table.schema)
        inserted_rows, updated_rows = _merge_temp_table(
            logger,
            client,
            table_ref,
            temp_table_ref,
            target_table.schema,
        )

        logger.info(f"MERGE complete: {inserted_rows} inserted, {updated_rows} updated")

        return UploadResult(
            success=True,
            timestamp=datetime.now().isoformat(),
            rows_uploaded=inserted_rows + updated_rows,
            table=table_ref,
        )

    finally:
        client.delete_table(temp_table_ref, not_found_ok=True)


@task(
    name="geocode-new-addresses",
    description="Geocode new addresses not yet in geocode cache",
    retries=1,
    retry_delay_seconds=60,
    timeout_seconds=7200,  # 2 hours (geocoding is slow due to rate limits)
)
def geocode_new_addresses_task(
    project_id: str | None = None,
    batch_size: int = 100,
    rate_limit_delay: float = 1.1,
) -> GeocodeResult:
    """Geocode addresses that are in listings but not in geocode cache.

    This task:
    1. Queries BigQuery for addresses in listings but not in geocodes table
    2. Geocodes them using OSM Nominatim (with rate limiting)
    3. Uploads new geocodes to BigQuery

    Args:
        project_id: GCP project ID (default: from env)
        batch_size: Maximum addresses to geocode per run (for rate limiting)
        rate_limit_delay: Delay between geocoding requests (seconds)

    Returns:
        GeocodeResult with geocoding statistics
    """
    logger = get_task_logger(__name__)

    from google.cloud import bigquery

    from estate_value_index.ml.geocoding import geocode_address
    from estate_value_index.utils.bigquery_safety import _validate_bq_project_id
    from estate_value_index.utils.settings import load_env_config

    env_config = load_env_config()
    project_id = _validate_bq_project_id(project_id or env_config.bigquery_project_id)

    client = get_bq_client(project_id)

    # Find addresses not yet geocoded
    query = f"""
    WITH listing_addresses AS (
        SELECT DISTINCT
            address,
            area,
            CONCAT(address, ', ', LOWER(REPLACE(REPLACE(REPLACE(REPLACE(area, 'ö', 'o'), 'ä', 'a'), 'å', 'a'), ' ', '_'))) as geocode_key
        FROM {safe_table_ref(project_id, "booli_raw", "listings", quote=True)}
        WHERE address IS NOT NULL AND area IS NOT NULL
    ),
    existing_geocodes AS (
        SELECT address as geocode_key
        FROM {safe_table_ref(project_id, "booli_raw", "geocodes", quote=True)}
    )
    SELECT la.address, la.area, la.geocode_key
    FROM listing_addresses la
    LEFT JOIN existing_geocodes eg ON la.geocode_key = eg.geocode_key
    WHERE eg.geocode_key IS NULL
    LIMIT @batch_size
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("batch_size", "INT64", batch_size),
        ]
    )

    logger.info("Querying for addresses not yet geocoded...")
    missing_df = client.query(query, job_config=job_config).to_dataframe()

    new_addresses = len(missing_df)
    logger.info(f"Found {new_addresses} addresses to geocode")

    if new_addresses == 0:
        return GeocodeResult(
            success=True,
            timestamp=datetime.now().isoformat(),
            new_addresses=0,
            geocoded=0,
            failed=0,
            skipped=0,
        )

    # Initialize geocoder
    try:
        from geopy.geocoders import Nominatim

        geolocator = Nominatim(user_agent="estate-value-index-pipeline")
    except ImportError as exc:
        raise InfrastructureError(
            "geopy is required for geocoding but is not installed - run: pip install geopy"
        ) from exc

    # Geocode each address
    new_geocodes = []
    geocoded = 0
    failed = 0

    for i, row in missing_df.iterrows():
        address = row["address"]
        area = row["area"]
        geocode_key = row["geocode_key"]

        logger.info(f"Geocoding {i + 1}/{new_addresses}: {address}, {area}")

        try:
            coords = geocode_address(address, area, geolocator)

            if coords:
                lat, lon = coords
                new_geocodes.append(
                    {
                        "address": geocode_key,
                        "lat": lat,
                        "lon": lon,
                        "geocoded_at": datetime.now(UTC).isoformat(),
                        "source": "nominatim",
                    }
                )
                geocoded += 1
                logger.info(f"  ({lat:.6f}, {lon:.6f})")
            else:
                # Store failed geocode with NULL coords
                new_geocodes.append(
                    {
                        "address": geocode_key,
                        "lat": None,
                        "lon": None,
                        "geocoded_at": datetime.now(UTC).isoformat(),
                        "source": "nominatim_failed",
                    }
                )
                failed += 1
                logger.warning("  Could not geocode")

        except Exception as e:
            logger.error(f"  Error: {e}")
            failed += 1

        # Rate limiting
        time.sleep(rate_limit_delay)

    # Upload new geocodes to BigQuery
    if new_geocodes:
        logger.info(f"Uploading {len(new_geocodes)} geocodes to BigQuery...")

        geocodes_table = safe_table_ref(project_id, "booli_raw", "geocodes")

        errors = client.insert_rows_json(geocodes_table, new_geocodes)
        if errors:
            logger.error(f"BigQuery insert errors: {errors[:3]}")
        else:
            logger.info(f"Uploaded {len(new_geocodes)} geocodes")

    logger.info(f"Geocoding complete: {geocoded} successful, {failed} failed")

    return GeocodeResult(
        success=True,
        timestamp=datetime.now().isoformat(),
        new_addresses=new_addresses,
        geocoded=geocoded,
        failed=failed,
        skipped=0,
    )
