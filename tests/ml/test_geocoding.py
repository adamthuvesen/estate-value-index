"""Tests for geocoding utilities."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from estate_value_index.ml.geocoding import (
    batch_geocode,
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


class TestBatchGeocode:
    def test_applies_cached_geocodes(self):
        df = pd.DataFrame(
            {
                "address": ["Storgatan 1", "Kungsgatan 5"],
                "area": ["Södermalm", "Norrmalm"],
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "geocodes.csv"
            save_geocode_cache(
                {
                    "Storgatan 1, Södermalm": (59.318920, 18.034502),
                    "Kungsgatan 5, Norrmalm": (59.3340, 18.0680),
                },
                cache_path,
            )

            result = batch_geocode(df, cache_path, geocode_missing=False)

            assert "lat" in result.columns
            assert "lon" in result.columns
            assert result["lat"].iloc[0] == pytest.approx(59.318920, rel=1e-6)
            assert result["lon"].iloc[0] == pytest.approx(18.034502, rel=1e-6)

    def test_handles_missing_addresses(self):
        df = pd.DataFrame(
            {
                "address": ["Unknown Street 999"],
                "area": ["NowhereVille"],
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "geocodes.csv"

            result = batch_geocode(df, cache_path, geocode_missing=False)

            assert "lat" in result.columns
            assert "lon" in result.columns
            assert pd.isna(result["lat"].iloc[0])
            assert pd.isna(result["lon"].iloc[0])

    def test_preserves_original_columns(self):
        df = pd.DataFrame(
            {
                "listing_id": [123, 456],
                "address": ["Street A", "Street B"],
                "area": ["Area A", "Area B"],
                "price": [5000000, 6000000],
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "geocodes.csv"
            result = batch_geocode(df, cache_path, geocode_missing=False)

            assert "listing_id" in result.columns
            assert "price" in result.columns
            assert len(result) == 2

    def test_empty_addresses_are_not_geocoded(self, monkeypatch):
        """Rows with None / whitespace-only addresses must not hit Nominatim."""
        df = pd.DataFrame(
            {
                "address": ["Storgatan 5", None, "   "],
                "area": ["Vasastan", "Vasastan", "Södermalm"],
            }
        )

        fake_location = MagicMock()
        fake_location.latitude = 59.3400
        fake_location.longitude = 18.0500
        fake_geocoder = MagicMock()
        fake_geocoder.geocode = MagicMock(return_value=fake_location)

        import geopy.geocoders as geo_mod

        monkeypatch.setattr(geo_mod, "Nominatim", MagicMock(return_value=fake_geocoder))

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "geocodes.csv"
            result = batch_geocode(df, cache_path, geocode_missing=True)

        # Only the real address hits Nominatim
        assert fake_geocoder.geocode.call_count == 1

        assert result["lat"].iloc[0] == pytest.approx(59.3400)
        assert result["lon"].iloc[0] == pytest.approx(18.0500)
        # Empty-address rows are NaN, not the Stockholm centroid
        assert pd.isna(result["lat"].iloc[1])
        assert pd.isna(result["lon"].iloc[1])
        assert pd.isna(result["lat"].iloc[2])
        assert pd.isna(result["lon"].iloc[2])


class TestSyncCacheToBigQuery:
    """Production geocodes table must be merged into, never truncated."""

    def _make_fake_client(self, project: str = "estate-value-index"):
        client = MagicMock()
        client.project = project

        load_job = MagicMock()
        load_job.result.return_value = None
        client.load_table_from_dataframe.return_value = load_job

        query_job = MagicMock()
        query_job.result.return_value = None
        client.query.return_value = query_job

        client.delete_table.return_value = None
        return client

    def _patch_bigquery(self, monkeypatch, fake_client):
        monkeypatch.setattr(
            "estate_value_index.utils.clients.get_bq_client",
            MagicMock(return_value=fake_client),
        )

    def test_uses_merge_not_truncate_against_production_table(self, monkeypatch):
        from estate_value_index.ml.geocoding import sync_cache_to_bigquery

        client = self._make_fake_client()
        self._patch_bigquery(monkeypatch, client)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "geocodes.csv"
            pd.DataFrame(
                {
                    "address": ["A", "B"],
                    "lat": [59.3, 59.4],
                    "lon": [18.0, 18.1],
                }
            ).to_csv(cache_path, index=False)

            count = sync_cache_to_bigquery(cache_path=cache_path, project_id="estate-value-index")

        assert count == 2

        # Production table received the load? No — only staging should.
        load_call = client.load_table_from_dataframe.call_args
        assert load_call is not None
        target = load_call.args[1]
        assert "_staging_" in target
        assert "estate-value-index.booli_raw.geocodes_staging_" in target

        # The MERGE was issued against the production table, never WRITE_TRUNCATE.
        assert client.query.called
        merge_sql = client.query.call_args.args[0]
        assert "MERGE" in merge_sql.upper()
        assert "booli_raw.geocodes" in merge_sql
        assert "WRITE_TRUNCATE" not in merge_sql.upper()
        assert "TRUNCATE TABLE" not in merge_sql.upper()

        # Staging cleaned up.
        assert client.delete_table.called
        deleted = client.delete_table.call_args.args[0]
        assert "_staging_" in deleted
        assert client.delete_table.call_args.kwargs.get("not_found_ok") is True

    def test_staging_deleted_on_merge_failure(self, monkeypatch):
        from estate_value_index.ml.geocoding import sync_cache_to_bigquery

        client = self._make_fake_client()
        client.query.side_effect = RuntimeError("boom")
        self._patch_bigquery(monkeypatch, client)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "geocodes.csv"
            pd.DataFrame({"address": ["A"], "lat": [59.3], "lon": [18.0]}).to_csv(
                cache_path, index=False
            )

            with pytest.raises(RuntimeError, match="boom"):
                sync_cache_to_bigquery(cache_path=cache_path, project_id="estate-value-index")

        assert client.delete_table.called
        assert client.delete_table.call_args.kwargs.get("not_found_ok") is True
