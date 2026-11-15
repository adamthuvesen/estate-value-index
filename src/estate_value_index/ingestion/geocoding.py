"""Geocode new listing addresses with OSM Nominatim and store them in ``booli_raw.geocodes``."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any, Protocol, cast

import pandas as pd

from estate_value_index.exceptions import InfrastructureError
from estate_value_index.utils.approval import require_approval
from estate_value_index.utils.bigquery_safety import safe_table_ref, validate_bq_project_id
from estate_value_index.utils.clients import get_bq_client
from estate_value_index.utils.settings import get_settings

logger = logging.getLogger(__name__)


class GeocodedLocation(Protocol):
    latitude: float
    longitude: float


class Geocoder(Protocol):
    """The part of ``geopy.geocoders.Nominatim`` used here."""

    def geocode(self, query: str, *, timeout: float) -> GeocodedLocation | None: ...


def geocode_address(address: str, area: str, geolocator: Geocoder) -> tuple[float, float] | None:
    """Geocode a Swedish address using OSM Nominatim.

    Tries full address first, falls back to area only.

    Args:
        address: Street address (e.g., "Storgatan 1")
        area: Area/neighborhood name (e.g., "Södermalm")
        geolocator: Configured Nominatim geocoder instance

    Returns:
        (latitude, longitude) tuple or None if geocoding fails
    """
    if pd.isna(address) or not address:
        return None

    # Try with full address first. Broad catch is intentional: a single
    # address failing (timeout, service error, malformed response) must not
    # abort the whole batch — we fall back to area-only, then to None.
    full_address = f"{address}, {area}, Stockholm, Sweden"
    try:
        location = geolocator.geocode(full_address, timeout=10)
        if location:
            return (location.latitude, location.longitude)
    except Exception as e:
        logger.debug(f"Full address geocoding failed for '{full_address}': {e}")

    # Fallback to area only — same per-address best-effort rationale.
    try:
        area_address = f"{area}, Stockholm, Sweden"
        location = geolocator.geocode(area_address, timeout=10)
        if location:
            logger.debug(f"Falling back to area-only geocoding for '{address}'")
            return (location.latitude, location.longitude)
    except Exception as e:
        logger.debug(f"Area-only geocoding failed for '{area}': {e}")

    return None


def insert_geocodes(project_id: str, rows: list[dict[str, Any]], approved: bool = False) -> None:
    """Insert geocode rows into ``booli_raw.geocodes`` (BigQuery streaming insert)."""
    require_approval("write geocodes to BigQuery", approved)

    client = get_bq_client(project_id)
    errors = client.insert_rows_json(safe_table_ref(project_id, "booli_raw", "geocodes"), rows)
    if errors:
        raise RuntimeError(f"BigQuery geocode insert errors: {errors[:3]}")


def _geocode_row(geocode_key: str, coords: tuple[float, float] | None) -> dict[str, Any]:
    lat, lon = coords if coords else (None, None)
    return {
        "address": geocode_key,
        "lat": lat,
        "lon": lon,
        "geocoded_at": datetime.now(UTC).isoformat(),
        "source": "nominatim" if coords else "nominatim_failed",
    }


def geocode_new_addresses(
    project_id: str | None = None,
    batch_size: int = 100,
    rate_limit_delay: float = 1.1,
    approved: bool = False,
) -> dict[str, int]:
    """Geocode listing addresses that ``booli_raw.geocodes`` does not hold yet.

    The approval check runs first, so a refusal does not follow hours of
    rate-limited geocoding. Returns counts: new_addresses, geocoded, failed.
    """
    require_approval("write geocodes to BigQuery", approved)

    from google.cloud import bigquery

    project_id = validate_bq_project_id(project_id or get_settings().require_bigquery_project_id())
    client = get_bq_client(project_id)

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
        query_parameters=[bigquery.ScalarQueryParameter("batch_size", "INT64", batch_size)]
    )
    missing_df = client.query(query, job_config=job_config).to_dataframe()
    counts = {"new_addresses": len(missing_df), "geocoded": 0, "failed": 0}
    logger.info("Found %d addresses to geocode", counts["new_addresses"])
    if missing_df.empty:
        return counts

    try:
        from geopy.geocoders import Nominatim

        # geopy ships no type hints, so pyright infers an async return type for geocode().
        geolocator = cast("Geocoder", Nominatim(user_agent="estate-value-index-pipeline"))
    except ImportError as exc:
        raise InfrastructureError("geopy is required for geocoding: uv sync --extra geo") from exc

    new_geocodes = []
    for _, row in missing_df.iterrows():
        coords = geocode_address(row["address"], row["area"], geolocator)
        new_geocodes.append(_geocode_row(row["geocode_key"], coords))
        counts["geocoded" if coords else "failed"] += 1
        time.sleep(rate_limit_delay)

    insert_geocodes(project_id, new_geocodes, approved=approved)
    logger.info("Geocoding complete: %d geocoded, %d failed", counts["geocoded"], counts["failed"])
    return counts
