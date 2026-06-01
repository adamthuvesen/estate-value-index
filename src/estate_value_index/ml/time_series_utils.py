"""
Time Series Utilities for Real Estate Price Prediction

Provides temporal validation and train/test split utilities to ensure
proper splits that respect chronological ordering and prevent temporal
data leakage.
"""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def sort_by_temporal_order(df: pd.DataFrame, date_column: str = "sold_date") -> pd.DataFrame:
    """
    Sort dataframe by temporal order (chronological).

    Args:
        df: Input dataframe
        date_column: Column name containing temporal information (default: 'sold_date')

    Returns:
        Dataframe sorted by date in ascending order (oldest first)

    Raises:
        ValueError: If date_column is not in dataframe or not datetime type
    """
    if date_column not in df.columns:
        raise ValueError(
            f"Date column '{date_column}' not found in dataframe. Available columns: {df.columns.tolist()}"
        )

    if not pd.api.types.is_datetime64_any_dtype(df[date_column]):
        raise ValueError(
            f"Column '{date_column}' must be datetime type, got {df[date_column].dtype}"
        )

    missing_dates = df[date_column].isna().sum()
    if missing_dates > 0:
        raise ValueError(
            f"Found {missing_dates} missing values in '{date_column}'. Cannot sort with missing dates."
        )

    return df.sort_values(by=date_column, ascending=True).reset_index(drop=True)


def validate_temporal_leakage(
    train_indices: np.ndarray,
    test_indices: np.ndarray,
    df: pd.DataFrame,
    date_column: str = "sold_date",
    verbose: bool = True,
) -> bool:
    """
    Validate that all training dates come before all test dates.

    Args:
        train_indices: Indices for training set
        test_indices: Indices for test set
        df: Full dataframe (must be temporally sorted)
        date_column: Column containing dates
        verbose: Print validation details

    Returns:
        True if no temporal leakage detected, False otherwise
    """
    if date_column not in df.columns:
        raise ValueError(f"Date column '{date_column}' not found in dataframe")

    train_dates = df.iloc[train_indices][date_column]
    test_dates = df.iloc[test_indices][date_column]

    train_max = train_dates.max()
    test_min = test_dates.min()

    # Strict inequality: same-day rows on the boundary would force the leakage-free
    # encoders to look across the boundary to compute statistics for the latest
    # training row. Equal boundary dates are rejected so callers must place the
    # boundary deterministically.
    is_valid = train_max < test_min

    if verbose:
        gap_days = (test_min - train_max).days
        status = "PASS" if is_valid else "FAIL - TEMPORAL LEAKAGE"
        logger.info(
            "Temporal split: train=%d (%s to %s), test=%d (%s to %s), gap=%d days [%s]",
            len(train_indices),
            train_dates.min().date(),
            train_max.date(),
            len(test_indices),
            test_min.date(),
            test_dates.max().date(),
            gap_days,
            status,
        )

    return is_valid


def create_temporal_holdout_split(
    df: pd.DataFrame, test_size: float = 0.2, date_column: str = "sold_date"
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Create a single temporal train/test split.

    Unlike random split, this ensures all training data comes from dates
    before the test data, simulating real-world deployment scenario.

    Args:
        df: Input dataframe
        test_size: Fraction of data to use for test set (most recent)
        date_column: Column containing temporal information

    Returns:
        Tuple of (train_df, test_df)

    Example:
        >>> df = pd.DataFrame({'sold_date': pd.date_range('2024-01-01', periods=100),
        ...                    'price': range(100)})
        >>> train_df, test_df = create_temporal_holdout_split(df, test_size=0.2)
        >>> len(train_df), len(test_df)
        (80, 20)
    """
    df_sorted = sort_by_temporal_order(df, date_column)

    n = len(df_sorted)
    split_idx = int(n * (1 - test_size))
    if split_idx <= 0 or split_idx >= n:
        raise ValueError(f"test_size={test_size} produces an empty fold for n={n} rows")

    # Push all rows on the boundary date to the test side so the validator's
    # strict `train_max < test_min` always holds. Without this, same-day
    # boundary rows would split arbitrarily by position and force the
    # leakage-free encoders to look across the boundary.
    boundary_date = df_sorted.iloc[split_idx][date_column]
    train_mask = df_sorted[date_column] < boundary_date
    train_df = df_sorted.loc[train_mask].copy()
    test_df = df_sorted.loc[~train_mask].copy()
    if train_df.empty or test_df.empty:
        raise ValueError(
            "Boundary nudge produced an empty fold; the dataset has too few distinct dates"
        )

    # Validate split — the dataframes have been re-derived via boolean mask
    # above, so we recompose a sorted dataframe for the validator.
    df_validation = pd.concat([train_df, test_df]).reset_index(drop=True)
    train_indices = np.arange(len(train_df))
    test_indices = np.arange(len(train_df), len(df_validation))

    is_valid = validate_temporal_leakage(
        train_indices, test_indices, df_validation, date_column, verbose=True
    )

    if not is_valid:
        raise ValueError("Temporal leakage detected in holdout split!")

    return train_df, test_df
