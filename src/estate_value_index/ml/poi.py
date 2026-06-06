"""Point of Interest (POI) distance calculations for property features.

This module provides utilities for calculating distances from properties
to various points of interest, primarily Stockholm city center.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from estate_value_index.ml.geocoding import haversine_distance, haversine_distance_vectorized

logger = logging.getLogger(__name__)

# Stockholm city center coordinates (Sergels Torg)
STOCKHOLM_CENTER_LAT = 59.3326
STOCKHOLM_CENTER_LON = 18.0649
STOCKHOLM_CENTER = (STOCKHOLM_CENTER_LAT, STOCKHOLM_CENTER_LON)

# Default POI data paths
GEO_DATA_DIR = Path("data/reference/geo")
METRO_STATIONS_PATH = GEO_DATA_DIR / "stockholm_metro_stations.csv"
TRAIN_STATIONS_PATH = GEO_DATA_DIR / "stockholm_train_stations.csv"


def compute_distance_to_city_center(lat: float, lon: float) -> float:
    """Calculate distance from a point to Stockholm city center.

    Args:
        lat: Property latitude (degrees)
        lon: Property longitude (degrees)

    Returns:
        Distance in meters to Sergels Torg (59.3326, 18.0649).
        Returns np.nan if lat or lon is missing.
    """
    if pd.isna(lat) or pd.isna(lon):
        return np.nan
    return haversine_distance(lat, lon, STOCKHOLM_CENTER_LAT, STOCKHOLM_CENTER_LON)


def compute_distance_to_city_center_series(
    lat_series: pd.Series, lon_series: pd.Series
) -> pd.Series:
    """Vectorized distance calculation for a Series of coordinates.

    Args:
        lat_series: Series of latitudes
        lon_series: Series of longitudes

    Returns:
        Series of distances in meters to Stockholm city center
    """
    distances = haversine_distance_vectorized(
        STOCKHOLM_CENTER_LAT,
        STOCKHOLM_CENTER_LON,
        lat_series.values,
        lon_series.values,
    )
    return pd.Series(distances, index=lat_series.index)


def load_metro_stations(path: Path | str | None = None) -> np.ndarray:
    """Load metro station coordinates.

    Args:
        path: Path to metro stations CSV (default: data/reference/geo/stockholm_metro_stations.csv)

    Returns:
        NumPy array of shape (N, 2) with [lat, lon] for each station
    """
    path = Path(path) if path else METRO_STATIONS_PATH
    if not path.exists():
        logger.warning(f"Metro stations file not found: {path}")
        return np.array([])

    df = pd.read_csv(path)
    coords = df[["lat", "lon"]].values
    logger.debug(f"Loaded {len(coords)} metro stations")
    return coords


def load_train_stations(path: Path | str | None = None) -> np.ndarray:
    """Load train station coordinates.

    Args:
        path: Path to train stations CSV (default: data/reference/geo/stockholm_train_stations.csv)

    Returns:
        NumPy array of shape (N, 2) with [lat, lon] for each station
    """
    path = Path(path) if path else TRAIN_STATIONS_PATH
    if not path.exists():
        logger.warning(f"Train stations file not found: {path}")
        return np.array([])

    df = pd.read_csv(path)
    coords = df[["lat", "lon"]].values
    logger.debug(f"Loaded {len(coords)} train stations")
    return coords


def distance_to_nearest_poi(lat: float, lon: float, poi_coords: np.ndarray) -> float:
    """Calculate distance to nearest POI in meters.

    Args:
        lat: Property latitude
        lon: Property longitude
        poi_coords: Array of POI coordinates with shape (N, 2) as [lat, lon]

    Returns:
        Distance in meters to nearest POI, or np.nan if invalid input
    """
    if pd.isna(lat) or pd.isna(lon) or len(poi_coords) == 0:
        return np.nan

    distances = haversine_distance_vectorized(lat, lon, poi_coords[:, 0], poi_coords[:, 1])
    return float(distances.min())


def count_pois_within_radius(
    lat: float, lon: float, poi_coords: np.ndarray, radius_m: float
) -> int:
    """Count POIs within a given radius.

    Args:
        lat: Property latitude
        lon: Property longitude
        poi_coords: Array of POI coordinates with shape (N, 2) as [lat, lon]
        radius_m: Search radius in meters

    Returns:
        Number of POIs within radius, or 0 if invalid input
    """
    if pd.isna(lat) or pd.isna(lon) or len(poi_coords) == 0:
        return 0

    distances = haversine_distance_vectorized(lat, lon, poi_coords[:, 0], poi_coords[:, 1])
    return int((distances <= radius_m).sum())


def create_poi_features(
    df: pd.DataFrame,
    metro_coords: np.ndarray | None = None,
    train_coords: np.ndarray | None = None,
) -> pd.DataFrame:
    """Create POI proximity features from geocoded data.

    Args:
        df: DataFrame with 'lat' and 'lon' columns
        metro_coords: Metro station coordinates (loads from file if None)
        train_coords: Train station coordinates (loads from file if None)

    Returns:
        DataFrame with POI features added:
        - distance_to_city_center: Distance to Sergels Torg (meters)
        - distance_to_nearest_metro: Distance to nearest metro (meters)
        - distance_to_nearest_train: Distance to nearest train station (meters)
        - metro_stations_within_500m: Count of metros within 500m
        - metro_stations_within_1km: Count of metros within 1km
        - transit_accessibility_score: Normalized composite transit score
    """
    df = df.copy()

    # Load POI data if not provided
    if metro_coords is None:
        metro_coords = load_metro_stations()
    if train_coords is None:
        train_coords = load_train_stations()

    # Distance to city center (vectorized)
    df["distance_to_city_center"] = compute_distance_to_city_center_series(df["lat"], df["lon"])

    # Distance to nearest metro
    if len(metro_coords) > 0:
        df["distance_to_nearest_metro"] = df.apply(
            lambda row: distance_to_nearest_poi(row["lat"], row["lon"], metro_coords),
            axis=1,
        )
        df["metro_stations_within_500m"] = df.apply(
            lambda row: count_pois_within_radius(row["lat"], row["lon"], metro_coords, 500),
            axis=1,
        )
        df["metro_stations_within_1km"] = df.apply(
            lambda row: count_pois_within_radius(row["lat"], row["lon"], metro_coords, 1000),
            axis=1,
        )
    else:
        df["distance_to_nearest_metro"] = np.nan
        df["metro_stations_within_500m"] = 0
        df["metro_stations_within_1km"] = 0

    # Distance to nearest train station
    if len(train_coords) > 0:
        df["distance_to_nearest_train"] = df.apply(
            lambda row: distance_to_nearest_poi(row["lat"], row["lon"], train_coords),
            axis=1,
        )
    else:
        df["distance_to_nearest_train"] = np.nan

    # Transit accessibility score (normalized composite)
    max_metro_dist = 3000  # 3km max for normalization
    max_train_dist = 5000  # 5km max
    max_center_dist = 15000  # 15km max

    df["transit_accessibility_score"] = (
        (1 - df["distance_to_nearest_metro"].clip(upper=max_metro_dist) / max_metro_dist) * 0.4
        + (1 - df["distance_to_nearest_train"].clip(upper=max_train_dist) / max_train_dist) * 0.3
        + (1 - df["distance_to_city_center"].clip(upper=max_center_dist) / max_center_dist) * 0.2
        + (df["metro_stations_within_1km"].clip(upper=5) / 5) * 0.1
    )

    return df
