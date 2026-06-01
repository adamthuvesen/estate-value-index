"""Tests for time series utilities module."""

import numpy as np
import pandas as pd
import pytest

from src.estate_value_index.ml.time_series_utils import (
    create_temporal_holdout_split,
    sort_by_temporal_order,
    validate_temporal_leakage,
)


@pytest.fixture
def sample_temporal_df():
    dates = pd.date_range(start="2024-01-01", periods=100, freq="D")
    return pd.DataFrame(
        {
            "sold_date": dates,
            "sold_price": np.random.randint(3_000_000, 8_000_000, 100),
            "living_area": np.random.randint(40, 80, 100),
            "rooms": np.random.randint(2, 4, 100),
        }
    )


@pytest.fixture
def unsorted_temporal_df():
    dates = pd.date_range(start="2024-01-01", periods=50, freq="D")
    np.random.shuffle(dates.values)
    return pd.DataFrame(
        {
            "sold_date": dates,
            "sold_price": np.random.randint(3_000_000, 8_000_000, 50),
            "living_area": np.random.randint(40, 80, 50),
        }
    )


def test_sort_by_temporal_order(unsorted_temporal_df):
    df_sorted = sort_by_temporal_order(unsorted_temporal_df, date_column="sold_date")

    assert df_sorted["sold_date"].is_monotonic_increasing
    assert len(df_sorted) == len(unsorted_temporal_df)
    assert df_sorted.index.tolist() == list(range(len(df_sorted)))


def test_sort_by_temporal_order_missing_column():
    df = pd.DataFrame({"price": [1, 2, 3]})

    with pytest.raises(ValueError, match="Date column 'sold_date' not found"):
        sort_by_temporal_order(df, date_column="sold_date")


def test_sort_by_temporal_order_wrong_dtype():
    df = pd.DataFrame({"sold_date": [1, 2, 3]})

    with pytest.raises(ValueError, match="must be datetime type"):
        sort_by_temporal_order(df, date_column="sold_date")


def test_sort_by_temporal_order_missing_dates():
    df = pd.DataFrame({"sold_date": pd.to_datetime(["2024-01-01", None, "2024-01-03"])})

    with pytest.raises(ValueError, match="Found 1 missing values"):
        sort_by_temporal_order(df, date_column="sold_date")


def test_validate_temporal_leakage_valid(sample_temporal_df):
    df_sorted = sort_by_temporal_order(sample_temporal_df)

    train_indices = np.arange(80)
    test_indices = np.arange(80, 100)

    assert validate_temporal_leakage(train_indices, test_indices, df_sorted, verbose=False) is True

    # Same-day boundary sales must be rejected: encoders cannot distinguish
    # same-day rows across the split, so they must not straddle it.
    dates = pd.date_range(start="2024-01-01", periods=100, freq="D")
    df_with_overlap = pd.DataFrame(
        {
            "sold_date": dates,
            "price": range(100),
        }
    )
    df_with_overlap.loc[80, "sold_date"] = df_with_overlap.loc[79, "sold_date"]
    df_sorted_overlap = sort_by_temporal_order(df_with_overlap)

    assert (
        validate_temporal_leakage(train_indices, test_indices, df_sorted_overlap, verbose=False)
        is False
    )


def test_validate_temporal_leakage_invalid(sample_temporal_df):
    df_sorted = sort_by_temporal_order(sample_temporal_df)

    # Mix old and new data — invalid split
    train_indices = np.concatenate([np.arange(40), np.arange(60, 100)])
    test_indices = np.arange(40, 60)

    assert validate_temporal_leakage(train_indices, test_indices, df_sorted, verbose=False) is False


def test_create_temporal_holdout_split(sample_temporal_df):
    train_df, test_df = create_temporal_holdout_split(
        sample_temporal_df, test_size=0.2, date_column="sold_date"
    )

    assert len(train_df) == 80
    assert len(test_df) == 20
    assert train_df["sold_date"].max() < test_df["sold_date"].min()
    assert len(train_df) + len(test_df) == len(sample_temporal_df)


def test_create_temporal_holdout_split_custom_size(sample_temporal_df):
    train_df, test_df = create_temporal_holdout_split(
        sample_temporal_df, test_size=0.3, date_column="sold_date"
    )

    assert len(test_df) == 30
    assert len(train_df) == 70


def test_temporal_split_with_small_dataset():
    dates = pd.date_range(start="2024-01-01", periods=20, freq="D")
    df = pd.DataFrame(
        {
            "sold_date": dates,
            "price": range(20),
        }
    )

    train_df, test_df = create_temporal_holdout_split(df, test_size=0.2)

    assert len(train_df) == 16
    assert len(test_df) == 4


def test_temporal_split_preserves_data_integrity(sample_temporal_df):
    train_df, test_df = create_temporal_holdout_split(sample_temporal_df)

    original_prices = set(sample_temporal_df["sold_price"])
    split_prices = set(train_df["sold_price"]) | set(test_df["sold_price"])

    assert original_prices == split_prices
    assert len(train_df) + len(test_df) == len(sample_temporal_df)


@pytest.mark.integration
def test_temporal_split_integration_with_features():
    """Production-style flow: temporal split, then map train-only stats onto holdout."""
    dates = pd.date_range(start="2024-01-01", periods=200, freq="D")
    df = pd.DataFrame(
        {
            "sold_date": dates,
            "sold_price": np.random.randint(3_000_000, 8_000_000, 200),
            "listing_price": np.random.randint(3_000_000, 8_000_000, 200),
            "living_area": np.random.randint(40, 80, 200),
            "rooms": np.random.randint(2, 4, 200),
            "area": ["Södermalm"] * 100 + ["Vasastan"] * 100,
        }
    )

    train_df, test_df = create_temporal_holdout_split(df, test_size=0.2)

    train_area_medians = train_df.groupby("area")["sold_price"].median()

    test_df_enriched = test_df.copy()
    test_df_enriched["area_median"] = test_df_enriched["area"].map(train_area_medians)

    assert test_df_enriched["area_median"].notna().all()
    assert train_df["sold_date"].max() < test_df["sold_date"].min()
