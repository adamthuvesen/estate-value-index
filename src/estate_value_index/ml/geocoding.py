"""Geocoding utilities for property address resolution.

This module provides geocoding functionality using OpenStreetMap/Nominatim,
with caching to avoid repeated API calls and rate limiting.

Dual cache strategy:
- Local dev: CSV at data/cache/geocodes.csv
- Production: BigQuery table booli_raw.geocodes
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from estate_value_index.exceptions import DataLoadError, exception_context

if TYPE_CHECKING:
    from geopy.geocoders import Nominatim

logger = logging.getLogger(__name__)


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
