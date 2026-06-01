"""Geocoding utilities for property address resolution.

This module provides geocoding functionality using OpenStreetMap/Nominatim,
with caching to avoid repeated API calls and rate limiting.

Dual cache strategy:
- Local dev: CSV at data/geo/address_geocodes.csv
- Production: BigQuery table booli_raw.geocodes
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from estate_value_index.exceptions import BigQueryError, DataLoadError, exception_context

if TYPE_CHECKING:
    from geopy.geocoders import Nominatim

logger = logging.getLogger(__name__)

DEFAULT_CACHE_PATH = Path("data/geo/address_geocodes.csv")
BQ_GEOCODE_TABLE = "booli_raw.geocodes"


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in meters using Haversine formula.

    Args:
        lat1: Latitude of first point (degrees)
        lon1: Longitude of first point (degrees)
        lat2: Latitude of second point (degrees)
        lon2: Longitude of second point (degrees)

    Returns:
        Distance in meters between the two points
    """
    R = 6371000  # Earth's radius in meters

    lat1_rad = np.radians(lat1)
    lat2_rad = np.radians(lat2)
    delta_lat = np.radians(lat2 - lat1)
    delta_lon = np.radians(lon2 - lon1)

    a = (
        np.sin(delta_lat / 2) ** 2
        + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(delta_lon / 2) ** 2
    )
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

    return R * c


def haversine_distance_vectorized(
    lat: float, lon: float, lat_array: np.ndarray, lon_array: np.ndarray
) -> np.ndarray:
    """Calculate distances from one point to multiple points using Haversine formula.

    Vectorized implementation for efficient bulk distance calculations.

    Args:
        lat: Latitude of origin point (degrees)
        lon: Longitude of origin point (degrees)
        lat_array: Array of target latitudes (degrees)
        lon_array: Array of target longitudes (degrees)

    Returns:
        Array of distances in meters from origin to each target point
    """
    R = 6371000  # Earth's radius in meters

    lat1_rad = np.radians(lat)
    lat2_rad = np.radians(lat_array)
    delta_lat = np.radians(lat_array - lat)
    delta_lon = np.radians(lon_array - lon)

    a = (
        np.sin(delta_lat / 2) ** 2
        + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(delta_lon / 2) ** 2
    )
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

    return R * c


def geocode_address(address: str, area: str, geolocator: Nominatim) -> tuple[float, float] | None:
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


def load_geocode_cache(cache_path: Path | str) -> dict[str, tuple[float, float]]:
    """Load geocode cache from CSV file.

    Args:
        cache_path: Path to the cache CSV file

    Returns:
        Dictionary mapping address strings to (lat, lon) tuples
    """
    cache_path = Path(cache_path)
    if not cache_path.exists():
        return {}

    try:
        cache_df = pd.read_csv(cache_path)
        if "address" not in cache_df.columns:
            logger.warning(f"Cache file {cache_path} missing 'address' column")
            return {}

        cache = {}
        for _, row in cache_df.iterrows():
            addr = row["address"]
            if pd.notna(row.get("lat")) and pd.notna(row.get("lon")):
                cache[addr] = (float(row["lat"]), float(row["lon"]))
            else:
                cache[addr] = (np.nan, np.nan)

        logger.info(f"Loaded {len(cache)} geocodes from cache")
        return cache
    except Exception as e:
        # A corrupt cache silently returning {} would force a full re-geocode
        # (or, with geocode_missing=False, produce all-NaN coordinates). Fail
        # loud so the bad cache file is noticed instead of masked.
        logger.warning(f"Failed to load geocode cache: {e}")
        raise DataLoadError(
            f"Failed to load geocode cache from {cache_path}: {e}",
            context=exception_context("load_geocode_cache", cache_path=str(cache_path)),
        ) from e


def save_geocode_cache(cache: dict[str, tuple[float, float]], cache_path: Path | str) -> None:
    """Save geocode cache to CSV file.

    Args:
        cache: Dictionary mapping address strings to (lat, lon) tuples
        cache_path: Path to save the cache CSV file
    """
    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    records = []
    for addr, (lat, lon) in cache.items():
        records.append({"address": addr, "lat": lat, "lon": lon})

    df = pd.DataFrame(records)
    df.to_csv(cache_path, index=False)
    logger.info(f"Saved {len(cache)} geocodes to {cache_path}")


def batch_geocode(
    df: pd.DataFrame,
    cache_path: Path | str = DEFAULT_CACHE_PATH,
    sample_size: int | None = None,
    geocode_missing: bool = True,
) -> pd.DataFrame:
    """Geocode addresses in dataframe with caching.

    Args:
        df: DataFrame with 'address' and 'area' columns
        cache_path: Path to save/load geocoding cache
        sample_size: If set, only geocode this many addresses (for testing)
        geocode_missing: If True, geocode addresses not in cache (requires geopy)

    Returns:
        DataFrame with 'lat' and 'lon' columns added
    """
    df = df.copy()
    cache_path = Path(cache_path)

    # Load existing cache
    cache = load_geocode_cache(cache_path)

    # Create unique address key. Rows with an empty / whitespace-only address
    # get the empty-string sentinel so we never send a centroid-only query
    # ("", area, Stockholm, Sweden) to Nominatim.
    address_clean = df["address"].fillna("").astype(str).str.strip()
    area_clean = df["area"].fillna("").astype(str).str.strip()
    df["_full_address"] = np.where(
        address_clean.eq(""),
        "",  # sentinel — empty string means "do not geocode"
        address_clean + ", " + area_clean,
    )

    # Find addresses needing geocoding
    unique_addresses = df["_full_address"].unique()
    if sample_size:
        unique_addresses = unique_addresses[:sample_size]

    missing_addresses = [addr for addr in unique_addresses if addr not in cache]

    if missing_addresses and geocode_missing:
        try:
            from geopy.geocoders import Nominatim

            geolocator = Nominatim(user_agent="estate-value-index")

            logger.info(f"Geocoding {len(missing_addresses)} new addresses...")
            for i, addr in enumerate(missing_addresses):
                # Skip the empty-address sentinel without hitting Nominatim;
                # cache NaN so future runs don't re-attempt either.
                if not addr or not addr.strip():
                    cache[addr] = (np.nan, np.nan)
                    continue

                parts = addr.split(", ")
                address = parts[0] if len(parts) > 0 else ""
                area = parts[1] if len(parts) > 1 else ""

                coords = geocode_address(address, area, geolocator)
                if coords:
                    cache[addr] = coords
                else:
                    cache[addr] = (np.nan, np.nan)

                if (i + 1) % 50 == 0:
                    logger.info(f"Geocoded {i + 1}/{len(missing_addresses)} addresses")
                    save_geocode_cache(cache, cache_path)

            save_geocode_cache(cache, cache_path)

        except ImportError:
            logger.warning("geopy not installed. Install with: pip install geopy")
    elif missing_addresses:
        logger.info(f"{len(missing_addresses)} addresses not in cache (geocode_missing=False)")

    # Apply geocodes to dataframe
    df["lat"] = df["_full_address"].map(lambda x: cache.get(x, (np.nan, np.nan))[0])
    df["lon"] = df["_full_address"].map(lambda x: cache.get(x, (np.nan, np.nan))[1])
    df = df.drop(columns=["_full_address"])

    coverage = df["lat"].notna().mean()
    logger.info(f"Geocoding coverage: {coverage:.1%}")

    return df


def sync_cache_to_bigquery(
    cache_path: Path | str = DEFAULT_CACHE_PATH,
    project_id: str | None = None,
) -> int:
    """Merge the local CSV cache into the production BigQuery geocodes table.

    A staging table receives the CSV via WRITE_TRUNCATE; a MERGE then upserts
    into the production table on ``address`` (only updating rows whose
    ``geocoded_at`` is newer than the existing one). The staging table is
    dropped in a ``finally`` block.

    The previous implementation used WRITE_TRUNCATE against the production
    table directly, which silently nuked accumulated geocodes whenever the
    local CSV was partial.

    Args:
        cache_path: Path to the local CSV cache
        project_id: GCP project ID (defaults to env var)

    Returns:
        Number of rows uploaded
    """
    from uuid import uuid4

    from google.cloud import bigquery

    from estate_value_index.utils.clients import get_bq_client

    cache_path = Path(cache_path)
    if not cache_path.exists():
        logger.warning(f"Cache file not found: {cache_path}")
        return 0

    df = pd.read_csv(cache_path)
    df["geocoded_at"] = pd.Timestamp.now(tz="UTC")

    client = get_bq_client(project_id)
    project = project_id or client.project
    dataset, prod_table = BQ_GEOCODE_TABLE.split(".", 1)
    prod_ref = f"{project}.{dataset}.{prod_table}"
    staging_table = f"{prod_table}_staging_{uuid4().hex[:8]}"
    staging_ref = f"{project}.{dataset}.{staging_table}"

    schema = [
        bigquery.SchemaField("address", "STRING"),
        bigquery.SchemaField("lat", "FLOAT64"),
        bigquery.SchemaField("lon", "FLOAT64"),
        bigquery.SchemaField("geocoded_at", "TIMESTAMP"),
    ]

    try:
        job_config = bigquery.LoadJobConfig(
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            schema=schema,
        )
        client.load_table_from_dataframe(df, staging_ref, job_config=job_config).result()

        merge_sql = f"""
            MERGE `{prod_ref}` T
            USING `{staging_ref}` S
            ON T.address = S.address
            WHEN MATCHED AND S.geocoded_at > T.geocoded_at THEN
              UPDATE SET lat = S.lat, lon = S.lon, geocoded_at = S.geocoded_at
            WHEN NOT MATCHED THEN
              INSERT (address, lat, lon, geocoded_at)
              VALUES (S.address, S.lat, S.lon, S.geocoded_at)
        """
        client.query(merge_sql).result()
        logger.info(f"Merged {len(df)} geocodes into {prod_ref}")
        return len(df)
    finally:
        client.delete_table(staging_ref, not_found_ok=True)


def load_geocode_cache_from_bigquery(
    project_id: str | None = None,
) -> dict[str, tuple[float, float]]:
    """Load geocode cache from BigQuery table.

    Args:
        project_id: GCP project ID (defaults to env var)

    Returns:
        Dictionary mapping address strings to (lat, lon) tuples
    """
    from estate_value_index.utils.clients import get_bq_client

    client = get_bq_client(project_id)
    table_ref = f"{project_id or client.project}.{BQ_GEOCODE_TABLE}"

    query = f"SELECT address, lat, lon FROM `{table_ref}`"

    try:
        df = client.query(query).to_dataframe()
        cache = {}
        for _, row in df.iterrows():
            if pd.notna(row["lat"]) and pd.notna(row["lon"]):
                cache[row["address"]] = (float(row["lat"]), float(row["lon"]))

        logger.info(f"Loaded {len(cache)} geocodes from BigQuery")
        return cache
    except Exception as e:
        # Returning {} here would silently train/geocode with no cache hits.
        # Surface the BigQuery failure instead of masking it as an empty cache.
        logger.warning(f"Failed to load geocodes from BigQuery: {e}")
        raise BigQueryError(
            f"Failed to load geocodes from BigQuery table {table_ref}: {e}",
            context=exception_context("load_geocode_cache_from_bigquery", table=table_ref),
        ) from e
