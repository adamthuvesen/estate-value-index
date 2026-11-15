"""Tests for geocoding utilities."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from estate_value_index.ml.geocoding import (
    haversine_distance,
    haversine_distance_vectorized,
    load_geocode_cache,
    save_geocode_cache,
)


class TestHaversineDistance:
    def test_same_point_returns_zero(self):
        lat, lon = 59.3326, 18.0649  # Sergels Torg
        assert haversine_distance(lat, lon, lat, lon) == pytest.approx(0.0, abs=0.001)

    def test_stockholm_to_uppsala(self):
        # Sergels Torg → Uppsala is ~65-70 km
        dist = haversine_distance(59.3326, 18.0649, 59.8585, 17.6469)
        assert 60000 < dist < 75000

    def test_short_distance(self):
        # T-Centralen → Östermalmstorg is ~1.2 km
        dist = haversine_distance(59.3308, 18.0594, 59.3353, 18.0742)
        assert 900 < dist < 1500

    def test_symmetric(self):
        lat1, lon1 = 59.3326, 18.0649
        lat2, lon2 = 59.8585, 17.6469

        dist_ab = haversine_distance(lat1, lon1, lat2, lon2)
        dist_ba = haversine_distance(lat2, lon2, lat1, lon1)
        assert dist_ab == pytest.approx(dist_ba, rel=1e-10)


class TestHaversineDistanceVectorized:
    def test_matches_scalar_version(self):
        origin_lat, origin_lon = 59.3326, 18.0649
        target_lats = np.array([59.8585, 59.3353, 59.3308])
        target_lons = np.array([17.6469, 18.0742, 18.0594])

        vectorized_result = haversine_distance_vectorized(
            origin_lat, origin_lon, target_lats, target_lons
        )
        scalar_results = np.array(
            [
                haversine_distance(origin_lat, origin_lon, lat, lon)
                for lat, lon in zip(target_lats, target_lons, strict=True)
            ]
        )

        np.testing.assert_allclose(vectorized_result, scalar_results, rtol=1e-10)

    def test_empty_arrays(self):
        result = haversine_distance_vectorized(59.3326, 18.0649, np.array([]), np.array([]))

        assert len(result) == 0
        assert isinstance(result, np.ndarray)

    def test_single_element(self):
        origin_lat, origin_lon = 59.3326, 18.0649
        target_lat, target_lon = 59.8585, 17.6469

        result = haversine_distance_vectorized(
            origin_lat, origin_lon, np.array([target_lat]), np.array([target_lon])
        )
        expected = haversine_distance(origin_lat, origin_lon, target_lat, target_lon)

        assert len(result) == 1
        assert result[0] == pytest.approx(expected, rel=1e-10)

    def test_same_point_returns_zero(self):
        lat, lon = 59.3326, 18.0649
        result = haversine_distance_vectorized(lat, lon, np.array([lat]), np.array([lon]))
        assert result[0] == pytest.approx(0.0, abs=0.001)

    def test_multiple_same_points(self):
        lat, lon = 59.3326, 18.0649
        result = haversine_distance_vectorized(
            lat, lon, np.array([lat, lat, lat]), np.array([lon, lon, lon])
        )
        np.testing.assert_allclose(result, [0.0, 0.0, 0.0], atol=0.001)


class TestGeocodeCache:
    def test_save_and_load_cache(self):
        cache = {
            "Storgatan 1, Södermalm": (59.318920, 18.034502),
            "Kungsgatan 5, Norrmalm": (59.3340, 18.0680),
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "geocodes.csv"

            save_geocode_cache(cache, cache_path)
            loaded = load_geocode_cache(cache_path)

            assert len(loaded) == 2
            assert "Storgatan 1, Södermalm" in loaded
            assert loaded["Storgatan 1, Södermalm"][0] == pytest.approx(59.318920, rel=1e-6)
            assert loaded["Storgatan 1, Södermalm"][1] == pytest.approx(18.034502, rel=1e-6)

    def test_load_nonexistent_cache(self):
        assert load_geocode_cache("/nonexistent/path/cache.csv") == {}

    def test_cache_with_nan_values(self):
        cache = {
            "Valid Address, Stockholm": (59.3326, 18.0649),
            "Invalid Address, Unknown": (np.nan, np.nan),
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "geocodes.csv"

            save_geocode_cache(cache, cache_path)
            loaded = load_geocode_cache(cache_path)

            assert len(loaded) == 2
            assert "Valid Address, Stockholm" in loaded
            assert "Invalid Address, Unknown" in loaded
