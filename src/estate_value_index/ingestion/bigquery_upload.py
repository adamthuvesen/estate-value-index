"""Convert normalized listings to BigQuery rows and load them into the listings table."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from estate_value_index.ingestion.listing_row import validate_listing_rows
from estate_value_index.utils.approval import require_approval
from estate_value_index.utils.bigquery_safety import quote_identifier, safe_table_ref
from estate_value_index.utils.clients import get_bq_client
from estate_value_index.utils.settings import get_settings

logger = logging.getLogger(__name__)


def _clean_listing_id(value: Any) -> str:
    listing_id = "" if value is None else str(value).strip()
    if not listing_id or listing_id.lower() == "none":
        raise ValueError("listing_id is required and cannot be blank")
    return listing_id


def prepare_bq_row(item: dict[str, Any]) -> dict[str, Any]:
    """Convert a normalized listing to a BigQuery-compatible row."""
    scraped_at_value = item.get("scraped_at")
    if isinstance(scraped_at_value, str):
        try:
            scraped_at = datetime.fromisoformat(scraped_at_value)
        except ValueError:
            scraped_at = datetime.now(UTC)
    else:
        scraped_at = datetime.now(UTC)

    def to_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(float(value))
        except ValueError, TypeError:
            return None

    def to_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except ValueError, TypeError:
            return None

    return {
        "listing_id": _clean_listing_id(item.get("listing_id")),
        "url": item.get("url"),
        "scraped_at": scraped_at.isoformat(),
        "scraped_at_date": scraped_at.date().isoformat(),
        "listing_price": to_int(item.get("listing_price")),
        "sold_price": to_int(item.get("sold_price")),
        "address": item.get("address"),
        "area": item.get("area"),
        "area_original": item.get("area_original"),
        "municipality": item.get("municipality"),
        "latitude": to_float(item.get("latitude", item.get("lat"))),
        "longitude": to_float(item.get("longitude", item.get("lon"))),
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


def _load_unique_bq_rows(processed_file: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    with processed_file.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            raw_listing = json.loads(line)
            listing_id = _clean_listing_id(raw_listing.get("listing_id"))
            if listing_id in seen_ids:
                continue
            seen_ids.add(listing_id)
            raw_listing["listing_id"] = listing_id
            rows.append(prepare_bq_row(raw_listing))
    return rows


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


def _execute_merge(client, table_ref: str, temp_table_ref: str, schema, *, update_existing: bool):
    merge_job = client.query(
        _merge_query(table_ref, temp_table_ref, schema, update_existing=update_existing)
    )
    merge_job.result()
    stats = merge_job._properties.get("statistics", {}).get("query", {}).get("dmlStats", {})
    return int(stats.get("insertedRowCount", 0)), int(stats.get("updatedRowCount", 0))


def _merge_temp_table(client, table_ref: str, temp_table_ref: str, schema) -> tuple[int, int]:
    try:
        return _execute_merge(client, table_ref, temp_table_ref, schema, update_existing=True)
    except Exception as e:
        if "streaming buffer" not in str(e).lower():
            raise
        logger.warning("Streaming buffer conflict - falling back to INSERT-only mode")
        inserted_rows, _ = _execute_merge(
            client, table_ref, temp_table_ref, schema, update_existing=False
        )
        return inserted_rows, 0


def upload_to_bigquery(
    processed_file: Path,
    *,
    truncate: bool = False,
    approved: bool = False,
) -> dict[str, Any]:
    """Load processed listings into the listings table: temp table load, then MERGE on listing_id.

    Every row is checked against ``BigQueryListingRow`` first; one bad row stops the load.
    """
    require_approval("write listings to BigQuery", approved)

    if not processed_file.exists():
        raise FileNotFoundError(f"Processed file not found: {processed_file}")

    from google.cloud import bigquery

    settings = get_settings()
    project_id = settings.require_bigquery_project_id()
    table_ref = settings.listings_table_ref()
    listings = validate_listing_rows(_load_unique_bq_rows(processed_file))
    logger.info("Loaded %d unique listings from %s", len(listings), processed_file)

    client = get_bq_client(project_id)
    if truncate:
        logger.info("Truncating table %s", table_ref)
        client.query(f"TRUNCATE TABLE `{table_ref}`").result()

    temp_table_ref = safe_table_ref(
        project_id,
        settings.bigquery_dataset_raw,
        f"{settings.bigquery_table_listings}_temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    )
    try:
        schema = client.get_table(table_ref).schema
        client.create_table(bigquery.Table(temp_table_ref, schema=schema))
        client.load_table_from_json(
            listings,
            temp_table_ref,
            job_config=bigquery.LoadJobConfig(schema=schema, write_disposition="WRITE_TRUNCATE"),
        ).result()
        inserted_rows, updated_rows = _merge_temp_table(client, table_ref, temp_table_ref, schema)
    finally:
        client.delete_table(temp_table_ref, not_found_ok=True)

    logger.info("MERGE complete: %d inserted, %d updated", inserted_rows, updated_rows)
    return {"rows_uploaded": inserted_rows + updated_rows, "table": table_ref}
