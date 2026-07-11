"""Shared test fixtures and utilities for the Swedish real estate prediction system."""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import json
import shutil
import tempfile
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from src.estate_value_index.ml.features import FeatureEngineeringContext
from src.estate_value_index.ml.preprocessing import FeatureSpec


@pytest.fixture
def sample_swedish_properties():
    """Realistic Swedish property listings fixture."""
    base_date = datetime.now() - timedelta(days=30)

    properties = [
        {
            "listing_id": "SWE-001",
            "listing_price": 4500000,
            "sold_price": 4650000,
            "living_area": 65.0,
            "rooms": 2,
            "monthly_fee": 3200,
            "days_on_market": 15,
            "construction_year": 1958,
            "property_type": "Lägenhet",
            "municipality": "Stockholm",
            "area": "Södermalm",
            "scraped_at": base_date.isoformat(),
            "sold_date": (base_date + timedelta(days=15)).isoformat(),
            "floor": 3,
        },
        {
            "listing_id": "SWE-002",
            "listing_price": 6200000,
            "sold_price": 6100000,
            "living_area": 78.0,
            "rooms": 3,
            "monthly_fee": 4100,
            "days_on_market": 8,
            "construction_year": 1975,
            "property_type": "Lägenhet",
            "municipality": "Stockholm",
            "area": "Östermalm",
            "scraped_at": base_date.isoformat(),
            "sold_date": (base_date + timedelta(days=8)).isoformat(),
            "floor": 5,
        },
        {
            "listing_id": "SWE-003",
            "listing_price": 3800000,
            "sold_price": 3950000,
            "living_area": 52.0,
            "rooms": 2,
            "monthly_fee": 2800,
            "days_on_market": 22,
            "construction_year": 1930,
            "property_type": "Lägenhet",
            "municipality": "Stockholm",
            "area": "Gamla Stan",
            "scraped_at": base_date.isoformat(),
            "sold_date": (base_date + timedelta(days=22)).isoformat(),
            "floor": 2,
        },
        {
            "listing_id": "SWE-004",
            "listing_price": 7500000,
            "sold_price": 7400000,
            "living_area": 95.0,
            "rooms": 4,
            "monthly_fee": 5200,
            "days_on_market": 35,
            "construction_year": 2005,
            "property_type": "Lägenhet",
            "municipality": "Stockholm",
            "area": "Vasastan",
            "scraped_at": base_date.isoformat(),
            "sold_date": (base_date + timedelta(days=35)).isoformat(),
            "floor": 7,
        },
        {
            "listing_id": "SWE-005",
            "listing_price": 2800000,
            "sold_price": None,  # Active listing
            "living_area": 42.0,
            "rooms": 1,
            "monthly_fee": 2200,
            "days_on_market": 5,
            "construction_year": 1962,
            "property_type": "Lägenhet",
            "municipality": "Stockholm",
            "area": "Södermalm",
            "scraped_at": base_date.isoformat(),
            "sold_date": None,
            "floor": 1,
        },
    ]

    return pd.DataFrame(properties)


@pytest.fixture
def sample_feature_spec():
    """Standard feature specification for testing."""
    return FeatureSpec(
        numeric=[
            "listing_price",
            "living_area",
            "rooms",
            "monthly_fee",
            "days_on_market",
            "construction_year",
            "property_age",
            "price_per_sqm",
            "monthly_fee_per_sqm",
        ],
        categorical=["area", "property_type", "municipality"],
        target="sold_price",
    )


@pytest.fixture
def edge_case_properties():
    """Edge cases and boundary conditions for robust testing."""
    return pd.DataFrame(
        [
            {
                "listing_id": "EDGE-001",
                "listing_price": 500000,  # Very low price
                "sold_price": 520000,
                "living_area": 18.0,  # Very small
                "rooms": 1,
                "monthly_fee": 1500,
                "days_on_market": 180,  # Long time on market
                "construction_year": 1880,  # Very old
                "property_type": "Lägenhet",
                "municipality": "Stockholm",
                "area": "Unknown Area",
                "scraped_at": "2023-01-01T00:00:00",
                "sold_date": "2023-06-30T00:00:00",
            },
            {
                "listing_id": "EDGE-002",
                "listing_price": 15000000,  # Very high price
                "sold_price": 14500000,
                "living_area": 180.0,  # Very large
                "rooms": 6,
                "monthly_fee": 8500,
                "days_on_market": 1,  # Sold immediately
                "construction_year": 2023,  # Brand new
                "property_type": "Lägenhet",
                "municipality": "Stockholm",
                "area": "Premium District",
                "scraped_at": "2023-12-01T00:00:00",
                "sold_date": "2023-12-02T00:00:00",
            },
            {
                "listing_id": "EDGE-003",
                "listing_price": None,  # Missing price
                "sold_price": 4000000,
                "living_area": None,  # Missing area
                "rooms": 2,
                "monthly_fee": np.nan,  # NaN fee
                "days_on_market": 0,
                "construction_year": None,
                "property_type": "",  # Empty string
                "municipality": None,
                "area": None,
                "scraped_at": None,
                "sold_date": None,
            },
        ]
    )


@pytest.fixture
def mock_feature_context():
    """Mock FeatureEngineeringContext for testing."""
    return FeatureEngineeringContext(
        reference_date=pd.Timestamp("2023-12-01"),
        area_avg_price={
            "Södermalm": 4200000.0,
            "Östermalm": 6100000.0,
            "Gamla Stan": 3900000.0,
            "Vasastan": 5800000.0,
        },
        area_listing_count={
            "Södermalm": 150.0,
            "Östermalm": 85.0,
            "Gamla Stan": 45.0,
            "Vasastan": 120.0,
        },
        area_price_tier={
            "Södermalm": "mid",
            "Östermalm": "premium",
            "Gamla Stan": "budget",
            "Vasastan": "premium",
        },
        area_target_mean={
            "Södermalm": 4300000.0,
            "Östermalm": 6200000.0,
            "Gamla Stan": 3950000.0,
            "Vasastan": 5900000.0,
        },
        global_target_mean=4850000.0,
        global_listing_price_mean=4750000.0,
        area_median_price_1m={
            "Södermalm": 4150000.0,
            "Östermalm": 6050000.0,
            "Gamla Stan": 3850000.0,
            "Vasastan": 5750000.0,
        },
        area_median_price_3m={
            "Södermalm": 4100000.0,
            "Östermalm": 6000000.0,
            "Gamla Stan": 3800000.0,
            "Vasastan": 5700000.0,
        },
        area_median_price_6m={
            "Södermalm": 4050000.0,
            "Östermalm": 5950000.0,
            "Gamla Stan": 3750000.0,
            "Vasastan": 5650000.0,
        },
        area_median_price_12m={
            "Södermalm": 3950000.0,
            "Östermalm": 5800000.0,
            "Gamla Stan": 3650000.0,
            "Vasastan": 5500000.0,
        },
        area_sales_volume_1m={
            "Södermalm": 10.0,
            "Östermalm": 6.0,
            "Gamla Stan": 3.0,
            "Vasastan": 8.0,
        },
        area_sales_volume_3m={
            "Södermalm": 25.0,
            "Östermalm": 15.0,
            "Gamla Stan": 8.0,
            "Vasastan": 20.0,
        },
        area_sales_volume_6m={
            "Södermalm": 45.0,
            "Östermalm": 28.0,
            "Gamla Stan": 15.0,
            "Vasastan": 35.0,
        },
        area_sales_volume_12m={
            "Södermalm": 85.0,
            "Östermalm": 52.0,
            "Gamla Stan": 28.0,
            "Vasastan": 68.0,
        },
        global_area_median_price_1m=4500000.0,
        global_area_median_price_3m=4450000.0,
        global_area_median_price_6m=4350000.0,
        global_area_median_price_12m=4200000.0,
        numeric_fill_values={
            "listing_price": 4750000.0,
            "living_area": 65.0,
            "rooms": 2.0,
            "monthly_fee": 3200.0,
            "construction_year": 1970.0,
        },
        categorical_fill_values={
            "area": "Stockholm",
            "property_type": "Lägenhet",
            "municipality": "Stockholm",
        },
        area_market_stats={},
        micro_area_stats_res10={},
        micro_area_stats_res9={},
        area_ppsqm_stats={},
        same_size_stats_h3_res9={},
        same_size_stats_area={},
        same_size_stats_global={},
        street_area_ppsqm_stats={},
        street_size_ppsqm_stats={},
        address_ppsqm_stats={},
        global_ppsqm_median=None,
    )


@pytest.fixture
def temp_data_dir():
    """Empty temporary directory for creating test data files."""
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir)

    yield temp_path

    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def temp_data_dir_with_files():
    """Temporary directory with pre-populated test JSON data files."""
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir)

    # Create sample JSON files
    sample_data = [
        {"listing_id": "FIXTURE-001", "listing_price": 4000000, "living_area": 60},
        {"listing_id": "FIXTURE-002", "listing_price": 5000000, "living_area": 75},
    ]

    # Single JSON file
    json_file = temp_path / "test_listings.json"
    with open(json_file, "w") as f:
        json.dump(sample_data, f)

    # JSONL file (one JSON per line)
    jsonl_file = temp_path / "test_listings.jsonl"
    with open(jsonl_file, "w") as f:
        for record in sample_data:
            f.write(json.dumps(record) + "\n")

    yield temp_path

    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def temp_model_dir():
    """Temporary directory for saving/loading model artifacts."""
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir)

    yield temp_path

    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def prediction_input():
    """Sample input for prediction API testing."""
    return {
        "listing_price": 4500000,
        "living_area": 65.0,
        "rooms": 2,
        "monthly_fee": 3200,
        "days_on_market": 30,
        "construction_year": 1958,
        "municipality": "Stockholm",
        "property_type": "Lägenhet",
        "area": "Södermalm",
        "model": "auto",
    }


@pytest.fixture(scope="session")
def project_root():
    """Path to project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture
def invalid_properties():
    """Properties that should be filtered out by validation."""
    return pd.DataFrame(
        [
            {
                "listing_id": "INVALID-001",
                "listing_price": 100000,  # Below minimum valid price
                "sold_price": 120000,
                "living_area": 65.0,
                "rooms": 2,
            },
            {
                "listing_id": "INVALID-002",
                "listing_price": 4500000,
                "sold_price": None,  # No sold price
                "living_area": 65.0,
                "rooms": 2,
            },
        ]
    )


# Test utilities
def assert_valid_dataframe(df: pd.DataFrame, min_rows: int = 1):
    """Assert dataframe is valid and non-empty."""
    assert isinstance(df, pd.DataFrame)
    assert len(df) >= min_rows
    assert not df.empty


def assert_valid_features(features: pd.DataFrame, expected_cols: list[str] | None = None):
    """Assert feature dataframe has expected structure."""
    assert_valid_dataframe(features)
    if expected_cols:
        missing_cols = set(expected_cols) - set(features.columns)
        assert not missing_cols, f"Missing expected columns: {missing_cols}"


def assert_valid_predictions(
    predictions: np.ndarray, min_value: float = 100000, max_value: float = 50000000
):
    """Assert predictions are in reasonable range for Swedish properties."""
    assert isinstance(predictions, np.ndarray)
    assert len(predictions) > 0
    assert all(min_value <= pred <= max_value for pred in predictions), (
        f"Predictions outside expected range [{min_value}, {max_value}]: {predictions}"
    )
