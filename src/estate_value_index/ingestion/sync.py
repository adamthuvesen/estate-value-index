"""Copy the BigQuery listings table to the local production file, check it, and back it up."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from estate_value_index.exceptions import DataError
from estate_value_index.utils.clients import BigQueryClient, get_bq_client
from estate_value_index.utils.gcs import GCSClient, is_gcs_enabled
from estate_value_index.utils.settings import get_settings

logger = logging.getLogger(__name__)

PRODUCTION_LISTINGS_FILE = Path("data/raw/booli/booli_listings_prod.json")
GCS_LISTINGS_PATH = "raw/booli_listings_prod.json"


def _json_default(value: Any) -> Any:
    # ISO "T" form, which downstream readers expect; str(datetime) would use a space.
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _normalize_scalar(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _listing_id_checksum(listing_ids: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(listing_ids)).encode("utf-8")).hexdigest()


def _local_sync_summary(local_file: Path) -> dict[str, Any]:
    with local_file.open(encoding="utf-8") as f:
        listings = [json.loads(line) for line in f if line.strip()]

    listing_ids = [
        str(listing["listing_id"]).strip()
        for listing in listings
        if str(listing.get("listing_id", "")).strip()
    ]
    dates = [
        str(date_value)
        for listing in listings
        if (date_value := listing.get("sold_date") or listing.get("scraped_at"))
    ]
    return {
        "count": len(listings),
        "listing_id_count": len(set(listing_ids)),
        "listing_id_checksum": _listing_id_checksum(listing_ids),
        "max_record_date": max(dates) if dates else None,
    }


def _bigquery_sync_summary(client: BigQueryClient, table_ref: str) -> dict[str, Any]:
    query = f"""
    SELECT
      COUNT(*) AS count,
      COUNT(DISTINCT listing_id) AS listing_id_count,
      LOWER(TO_HEX(SHA256(COALESCE(
        STRING_AGG(CAST(listing_id AS STRING), '\\n' ORDER BY CAST(listing_id AS STRING)),
        ''
      )))) AS listing_id_checksum,
      CAST(MAX(COALESCE(CAST(sold_date AS STRING), CAST(scraped_at AS STRING))) AS STRING)
        AS max_record_date
    FROM `{table_ref}`
    """
    row = next(iter(client.query(query).result()))
    keys = ("count", "listing_id_count", "listing_id_checksum", "max_record_date")
    return {key: _normalize_scalar(row[key]) for key in keys}


def sync_bigquery_to_local(
    output_file: Path = PRODUCTION_LISTINGS_FILE, *, backup_existing: bool = True
) -> int:
    """Write every BigQuery listing to ``output_file`` as JSONL. Returns the row count."""
    settings = get_settings()
    table_ref = settings.listings_table_ref()
    client = get_bq_client(settings.require_bigquery_project_id())
    output_file.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Syncing %s to %s", table_ref, output_file)
    rows = client.query(f"SELECT * FROM `{table_ref}` ORDER BY scraped_at DESC").result()
    listings = [dict(row.items()) for row in rows]

    if backup_existing and output_file.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = output_file.with_name(
            f"{output_file.stem}_backup_{timestamp}{output_file.suffix}"
        )
        logger.info("Backing up %s to %s", output_file, backup_file)
        output_file.rename(backup_file)

    with output_file.open("w", encoding="utf-8") as f:
        for listing in listings:
            f.write(json.dumps(listing, ensure_ascii=False, default=_json_default) + "\n")

    with output_file.open(encoding="utf-8") as f:
        written = sum(1 for line in f if line.strip())
    if written != len(listings):
        raise DataError(
            f"Verification mismatch: wrote {len(listings)} but verified {written}",
            context={"expected": len(listings), "verified": written, "file": str(output_file)},
        )
    logger.info("Synced %d listings", len(listings))
    return len(listings)


def verify_sync(local_file: Path = PRODUCTION_LISTINGS_FILE) -> dict[str, Any]:
    """Raise ``DataError`` unless the local file and BigQuery hold the same listing set."""
    settings = get_settings()
    client = get_bq_client(settings.require_bigquery_project_id())
    local_summary = _local_sync_summary(local_file)
    bq_summary = _bigquery_sync_summary(client, settings.listings_table_ref())
    if local_summary != bq_summary:
        raise DataError(
            "Local file and BigQuery are out of sync",
            context={"local": local_summary, "bigquery": bq_summary},
        )
    logger.info("Local file and BigQuery are in sync: %s listings", local_summary["count"])
    return local_summary


def backup_listings_to_gcs(
    local_file: Path = PRODUCTION_LISTINGS_FILE, *, approved: bool = False
) -> list[str]:
    """Upload the listings file and a timestamped archive copy. A no-op when GCS is disabled."""
    if not local_file.exists():
        raise FileNotFoundError(f"Local file not found: {local_file}")
    if not is_gcs_enabled():
        logger.info("GCS disabled, skipping the listings backup")
        return []

    gcs_client = GCSClient()
    archive_path = f"raw/archive/booli_listings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    return [
        gcs_client.upload_file(local_file, GCS_LISTINGS_PATH, approved=approved),
        gcs_client.upload_file(local_file, archive_path, approved=approved),
    ]
