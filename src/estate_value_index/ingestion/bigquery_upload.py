"""BigQuery upload utilities for Booli listings.

This module provides functions for:
- Loading JSONL data files
- Preparing BigQuery rows
- Uploading data to BigQuery with MERGE deduplication
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from google.cloud import bigquery
from google.cloud.exceptions import GoogleCloudError

from estate_value_index.ingestion.processing import load_jsonl_file
from estate_value_index.utils.clients import get_bq_client
from estate_value_index.utils.settings import bq_table, get_batch_size, load_env_config


def prepare_bq_row(item: dict[str, Any]) -> dict[str, Any]:
    """Convert JSONL item to BigQuery-compatible row."""
    # Extract scraped_at timestamp
    scraped_at_str = item.get("scraped_at")
    if isinstance(scraped_at_str, str):
        try:
            scraped_at = datetime.fromisoformat(scraped_at_str)
        except ValueError:
            scraped_at = datetime.now(UTC)
    else:
        scraped_at = datetime.now(UTC)

    def to_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None

    bq_row = {
        "listing_id": str(item.get("listing_id")),
        "url": item.get("url"),
        "scraped_at": scraped_at.isoformat(),
        "scraped_at_date": scraped_at.date().isoformat(),
        "listing_price": to_int(item.get("listing_price")),
        "sold_price": to_int(item.get("sold_price")),
        "address": item.get("address"),
        "area": item.get("area"),
        "area_original": item.get("area_original"),
        "municipality": item.get("municipality"),
        "living_area": item.get("living_area"),
        "rooms": to_int(item.get("rooms")),
        "property_type": item.get("property_type"),
        "construction_year": to_int(item.get("construction_year")),
        "monthly_fee": to_int(item.get("monthly_fee")),
        "price_per_sqm": to_int(item.get("price_per_sqm")),
        "floor": to_int(item.get("floor")),
        "elevator": item.get("elevator"),
        "balcony": item.get("balcony"),
        "sold_date": item.get("sold_date"),
        "days_on_market": to_int(item.get("days_on_market")),
        "price_change": to_int(item.get("price_change")),
        "description": item.get("description"),
        "images": item.get("images", []) or [],
        "source_page": item.get("source_page"),
    }

    return bq_row


def _load_listings(data_file: Path) -> list[dict[str, Any]]:
    """Load listings from a JSONL file with progress logging."""
    print(f"Loading data from: {data_file}")
    listings = load_jsonl_file(Path(data_file))
    print(f"Loaded {len(listings)} listings")
    return listings


def _prepare_rows(listings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert listings to BigQuery rows, dropping duplicates by listing_id."""
    print(f"Preparing {len(listings)} rows for BigQuery...")
    bq_rows = []
    seen_ids: set[str] = set()
    duplicates_skipped = 0

    for item in listings:
        try:
            listing_id = item.get("listing_id")

            if listing_id in seen_ids:
                duplicates_skipped += 1
                continue

            if listing_id:
                seen_ids.add(listing_id)

            bq_row = prepare_bq_row(item)
            bq_rows.append(bq_row)
        except Exception as e:
            print(f"Warning: Failed to prepare row for {item.get('listing_id')}: {e}")
            continue

    print(f"Prepared {len(bq_rows)} unique rows")
    if duplicates_skipped > 0:
        print(f"Skipped {duplicates_skipped} duplicate listing_ids")

    return bq_rows


def _load_temp_table(
    client: bigquery.Client,
    temp_table_id: str,
    bq_rows: list[dict[str, Any]],
    batch_size: int,
) -> tuple[int, int]:
    """Insert rows into the temp table in batches.

    Returns:
        Tuple of (total_inserted, total_errors).
    """
    print(f"\n1. Loading {len(bq_rows)} rows into temp table...")

    total_inserted = 0
    total_errors = 0

    for i in range(0, len(bq_rows), batch_size):
        batch = bq_rows[i : i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(bq_rows) + batch_size - 1) // batch_size

        try:
            errors = client.insert_rows_json(temp_table_id, batch)

            if errors:
                print(f"Batch {batch_num}/{total_batches}: {len(errors)} errors")
                for error in errors[:3]:
                    print(f"   Error: {error}")
                total_errors += len(errors)
            else:
                total_inserted += len(batch)
                print(
                    f"Batch {batch_num}/{total_batches}: {len(batch)} rows loaded (total: {total_inserted})"
                )

        except GoogleCloudError as e:
            print(f"Batch {batch_num}/{total_batches} failed: {e}")
            total_errors += len(batch)
        except Exception as e:
            print(f"Unexpected error in batch {batch_num}/{total_batches}: {e}")
            total_errors += len(batch)

    if total_errors > 0:
        print(f"\n{total_errors} rows failed to load into temp table")
        print(f"   Continuing with MERGE for {total_inserted} successfully loaded rows...")

    return total_inserted, total_errors


def _merge_temp_table(client: bigquery.Client, full_table_id: str, temp_table_id: str) -> None:
    """Merge the temp table into the main table, deduplicating by listing_id."""
    print("\n2. Merging temp table into main table (deduplicating by listing_id)...")

    merge_query = f"""
    MERGE `{full_table_id}` T
    USING `{temp_table_id}` S
    ON T.listing_id = S.listing_id
    WHEN MATCHED AND S.scraped_at > T.scraped_at THEN
      UPDATE SET
        url = S.url,
        scraped_at = S.scraped_at,
        scraped_at_date = S.scraped_at_date,
        listing_price = S.listing_price,
        sold_price = S.sold_price,
        address = S.address,
        area = S.area,
        area_original = S.area_original,
        municipality = S.municipality,
        living_area = S.living_area,
        rooms = S.rooms,
        property_type = S.property_type,
        construction_year = S.construction_year,
        monthly_fee = S.monthly_fee,
        price_per_sqm = S.price_per_sqm,
        floor = S.floor,
        elevator = S.elevator,
        balcony = S.balcony,
        sold_date = S.sold_date,
        days_on_market = S.days_on_market,
        price_change = S.price_change,
        description = S.description,
        images = S.images,
        source_page = S.source_page
    WHEN NOT MATCHED THEN
      INSERT (
        listing_id, url, scraped_at, scraped_at_date, listing_price, sold_price,
        address, area, area_original, municipality, living_area, rooms, property_type,
        construction_year, monthly_fee, price_per_sqm, floor, elevator, balcony,
        sold_date, days_on_market, price_change, description, images, source_page
      )
      VALUES (
        S.listing_id, S.url, S.scraped_at, S.scraped_at_date, S.listing_price, S.sold_price,
        S.address, S.area, S.area_original, S.municipality, S.living_area, S.rooms, S.property_type,
        S.construction_year, S.monthly_fee, S.price_per_sqm, S.floor, S.elevator, S.balcony,
        S.sold_date, S.days_on_market, S.price_change, S.description, S.images, S.source_page
      )
    """

    merge_job = client.query(merge_query)
    merge_job.result()

    if hasattr(merge_job, "num_dml_affected_rows"):
        rows_affected = merge_job.num_dml_affected_rows
        print(f"MERGE complete: {rows_affected} rows affected (inserted or updated)")
    else:
        print("MERGE complete")


def _upload_via_merge(
    client: bigquery.Client,
    full_table_id: str,
    temp_table_id: str,
    bq_rows: list[dict[str, Any]],
    batch_size: int,
) -> tuple[int, int] | None:
    """Run the temp-table load + MERGE, cleaning up the temp table afterward.

    Returns:
        Tuple of (total_inserted, total_errors) on success, None on failure.
    """
    try:
        target_table = client.get_table(full_table_id)
        temp_table = bigquery.Table(temp_table_id, schema=target_table.schema)
        temp_table.expires = datetime.now(UTC) + timedelta(hours=2)
        client.create_table(temp_table, exists_ok=True)

        total_inserted, total_errors = _load_temp_table(client, temp_table_id, bq_rows, batch_size)

        _merge_temp_table(client, full_table_id, temp_table_id)

        print("\n3. Cleaning up temp table...")
        client.delete_table(temp_table_id, not_found_ok=True)
        print("Temp table deleted")

    except Exception as e:
        print(f"\nMERGE operation failed: {e}")
        print("   Attempting to clean up temp table...")
        try:
            client.delete_table(temp_table_id, not_found_ok=True)
            print("Temp table cleaned up")
        except Exception:
            print(f"Could not delete temp table: {temp_table_id}")
        return None

    return total_inserted, total_errors


def _verify_row_count(client: bigquery.Client, full_table_id: str) -> None:
    """Log the current row count of the target table; best-effort."""
    print("\nVerifying data...")
    try:
        query = f"SELECT COUNT(*) as count FROM `{full_table_id}`"
        result = client.query(query).result()
        row_count = list(result)[0]["count"]
        print(f"BigQuery table has {row_count} rows")
    except Exception as e:
        print(f"Could not verify row count: {e}")


def upload_to_bigquery(
    data_file: Path,
    project_id: str | None = None,
    dataset_id: str | None = None,
    table_id: str | None = None,
    batch_size: int | None = None,
    dry_run: bool = False,
) -> bool:
    """Upload JSONL data to BigQuery with MERGE deduplication.

    Args:
        data_file: Path to JSONL data file
        project_id: GCP project ID (default: from environment config)
        dataset_id: BigQuery dataset ID (default: from environment config)
        table_id: BigQuery table ID (default: from environment config)
        batch_size: Batch size for inserts (default: from config)
        dry_run: If True, don't write to BigQuery

    Returns:
        True on success, False on failure
    """
    env_config = load_env_config()

    project_id = project_id or env_config.bigquery_project_id
    dataset_id = dataset_id or env_config.bq_dataset_raw
    table_id = table_id or env_config.bq_table_listings
    batch_size = batch_size or get_batch_size()

    full_table_id = bq_table(project_id, dataset_id, table_id)

    print("\nStarting BigQuery Migration")
    print(f"   Source: {data_file}")
    print(f"   Target: {full_table_id}")
    print(f"   Batch size: {batch_size}")
    print(f"   Dry run: {dry_run}")
    print()

    listings = _load_listings(data_file)

    if not listings:
        print("No data to migrate")
        return False

    bq_rows = _prepare_rows(listings)

    if dry_run:
        print("\nDry run complete - no data written to BigQuery")
        print(f"   Sample row: {json.dumps(bq_rows[0], indent=2, default=str)}")
        return True

    print("\nConnecting to BigQuery...")
    try:
        client = get_bq_client(project_id)
        print(f"Connected to project: {project_id}")
    except Exception as e:
        print(f"Failed to connect to BigQuery: {e}")
        return False

    print("\nUploading data to BigQuery (MERGE deduplication)...")
    print("   Note: Using temp table + MERGE to prevent duplicates")

    temp_table_id = (
        f"{project_id}.{dataset_id}.listings_temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )

    result = _upload_via_merge(client, full_table_id, temp_table_id, bq_rows, batch_size)
    if result is None:
        return False
    total_inserted, total_errors = result

    _verify_row_count(client, full_table_id)

    print("\nMigration Summary:")
    print(f"   Rows inserted: {total_inserted}")
    print(f"   Errors: {total_errors}")
    print(f"   Success rate: {100 * total_inserted / len(bq_rows):.1f}%")

    if total_errors > 0:
        print(f"\nMigration completed with {total_errors} errors")
        return False
    else:
        print("\nMigration completed successfully!")
        return True
