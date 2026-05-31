"""Tests for POI (Point of Interest) distance calculations."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from estate_value_index.ml.poi import (
    STOCKHOLM_CENTER,
    STOCKHOLM_CENTER_LAT,
    STOCKHOLM_CENTER_LON,
    compute_distance_to_city_center,
    compute_distance_to_city_center_series,
    count_pois_within_radius,
    distance_to_nearest_poi,
)


class TestStockholmCenterConstants:
    def test_stockholm_center_is_sergels_torg(self):
        # Sergels Torg ≈ 59.3326, 18.0649
        assert STOCKHOLM_CENTER_LAT == pytest.approx(59.3326, abs=0.001)
        assert STOCKHOLM_CENTER_LON == pytest.approx(18.0649, abs=0.001)

    def test_stockholm_center_tuple(self):
        assert isinstance(STOCKHOLM_CENTER, tuple)
        assert len(STOCKHOLM_CENTER) == 2
        assert STOCKHOLM_CENTER == (STOCKHOLM_CENTER_LAT, STOCKHOLM_CENTER_LON)


class TestDistanceToCityCenter:
    def test_center_has_zero_distance(self):
        dist = compute_distance_to_city_center(STOCKHOLM_CENTER_LAT, STOCKHOLM_CENTER_LON)
        assert dist == pytest.approx(0.0, abs=1.0)

    def test_sodermalm_distance(self):
        # Mariatorget → Sergels Torg ≈ 1.5-2 km
        dist = compute_distance_to_city_center(59.3186, 18.0626)
        assert 1000 < dist < 3000

    def test_danderyd_distance(self):
        # Danderyd → Sergels Torg ≈ 7-10 km
        dist = compute_distance_to_city_center(59.3943, 18.0406)
        assert 6000 < dist < 12000

    def test_nan_input_returns_nan(self):
        assert np.isnan(compute_distance_to_city_center(np.nan, 18.0649))
        assert np.isnan(compute_distance_to_city_center(59.3326, np.nan))
        assert np.isnan(compute_distance_to_city_center(np.nan, np.nan))


class TestDistanceToCityCenterSeries:
    def test_series_calculation(self):
        # Center, Södermalm, Danderyd
        lats = pd.Series([59.3326, 59.3186, 59.3943])
        lons = pd.Series([18.0649, 18.0626, 18.0406])

        distances = compute_distance_to_city_center_series(lats, lons)

        assert len(distances) == 3
        assert distances.iloc[0] == pytest.approx(0.0, abs=1.0)
        assert 1000 < distances.iloc[1] < 3000
        assert 6000 < distances.iloc[2] < 12000

    def test_handles_nan_in_series(self):
        lats = pd.Series([59.3326, np.nan, 59.3186])
        lons = pd.Series([18.0649, 18.0626, np.nan])

        distances = compute_distance_to_city_center_series(lats, lons)

        assert len(distances) == 3
        assert not np.isnan(distances.iloc[0])
        assert np.isnan(distances.iloc[1])
        assert np.isnan(distances.iloc[2])


class TestDistanceToNearestPoi:
    def test_finds_nearest_poi(self):
        # Property in Södermalm; nearest POI is Medborgarplatsen (~500m)
        poi_coords = np.array(
            [
                [59.3196, 18.0717],  # Slussen
                [59.3141, 18.0737],  # Medborgarplatsen
                [59.3308, 18.0594],  # T-Centralen
            ]
        )
        dist = distance_to_nearest_poi(59.3186, 18.0626, poi_coords)
        assert 400 < dist < 900

    def test_empty_poi_array_returns_nan(self):
        assert np.isnan(distance_to_nearest_poi(59.3326, 18.0649, np.array([])))

    def test_nan_coordinates_return_nan(self):
        poi_coords = np.array([[59.3196, 18.0717]])
        assert np.isnan(distance_to_nearest_poi(np.nan, 18.0649, poi_coords))
        assert np.isnan(distance_to_nearest_poi(59.3326, np.nan, poi_coords))


class TestCountPoisWithinRadius:
    def test_counts_pois_within_radius(self):
        # Property near T-Centralen
        lat, lon = 59.3308, 18.0594
        poi_coords = np.array(
            [
                [59.3308, 18.0594],  # T-Centralen (0m)
                [59.3311, 18.0719],  # Kungsträdgården (~900m)
                [59.3347, 18.0624],  # Hötorget (~500m)
                [59.3412, 18.0525],  # Rådmansgatan (~1.2km)
                [59.3573, 18.1018],  # Ropsten (~3.5km)
            ]
        )

        assert count_pois_within_radius(lat, lon, poi_coords, 500) == 2
        assert count_pois_within_radius(lat, lon, poi_coords, 1000) >= 3

    def test_empty_poi_array_returns_zero(self):
        assert count_pois_within_radius(59.3326, 18.0649, np.array([]), 1000) == 0

    def test_nan_coordinates_return_zero(self):
        poi_coords = np.array([[59.3196, 18.0717]])
        assert count_pois_within_radius(np.nan, 18.0649, poi_coords, 1000) == 0
        assert count_pois_within_radius(59.3326, np.nan, poi_coords, 1000) == 0
