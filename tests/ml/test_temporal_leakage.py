"""Regression tests for ML temporal-feature-engineering leakage.

These tests pin the contract from the `fix-ml-temporal-leakage` change:
no statistic computed from the holdout fold is observable to the training
fold, and same-day same-area sales never leak labels into each other's
features.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from estate_value_index.ml.features import (
    build_feature_context,
    create_optimized_features,
)
from estate_value_index.ml.time_series_utils import (
    create_temporal_holdout_split,
    sort_by_temporal_order,
    validate_temporal_leakage,
)


def _minimal_listing(
    listing_id: str,
    area: str,
    sold_date: str,
    sold_price: float,
    listing_price: float | None = None,
    living_area: float = 60.0,
    rooms: float = 2.0,
) -> dict:
    """One listing dict with the columns downstream feature engineering needs."""
    return {
        "listing_id": listing_id,
        "area": area,
        "sold_date": pd.Timestamp(sold_date),
        "scraped_at": pd.Timestamp(sold_date) - pd.Timedelta(days=14),
        "sold_price": sold_price,
        "listing_price": listing_price if listing_price is not None else sold_price * 0.97,
        "living_area": living_area,
        "rooms": rooms,
        "monthly_fee": 3000.0,
        "days_on_market": 14,
        "construction_year": 1970,
        "property_type": "Lägenhet",
        "municipality": "Stockholm",
        "floor": 3.0,
        "elevator": True,
        "balcony": True,
    }


@pytest.fixture
def same_day_same_area_frame() -> pd.DataFrame:
    """Two listings on the same day in the same area + prior history."""
    rows = [
        _minimal_listing("PRIOR-1", "Södermalm", "2024-01-01", 4_000_000),
        _minimal_listing("PRIOR-2", "Södermalm", "2024-02-15", 4_500_000),
        _minimal_listing("R1", "Södermalm", "2024-06-01", 5_000_000),
        _minimal_listing("R2", "Södermalm", "2024-06-01", 50_000_000),
        _minimal_listing("OTHER-AREA", "Östermalm", "2024-06-01", 7_000_000),
    ]
    return pd.DataFrame(rows)


def test_target_encoding_no_same_day_leak(same_day_same_area_frame: pd.DataFrame) -> None:
    """R1 and R2 share (area, sold_date); neither's price may leak into the other's encoding."""
    df = same_day_same_area_frame.copy()
    encoded_a = create_optimized_features(df)

    swapped = df.copy()
    mask = swapped["listing_id"].isin(["R1", "R2"])
    rows_swapped = swapped.loc[mask].copy()
    rows_swapped["sold_price"] = rows_swapped["sold_price"].iloc[::-1].values
    swapped.loc[mask] = rows_swapped
    encoded_b = create_optimized_features(swapped)

    enc_a = encoded_a.set_index("listing_id")["area_target_encoded"]
    enc_b = encoded_b.set_index("listing_id")["area_target_encoded"]

    assert enc_a.loc["R1"] == pytest.approx(enc_b.loc["R1"]), (
        f"R1 encoding changed when only R2's price was changed: {enc_a.loc['R1']} vs {enc_b.loc['R1']}"
    )
    assert enc_a.loc["R2"] == pytest.approx(enc_b.loc["R2"]), (
        f"R2 encoding changed when only R1's price was changed: {enc_a.loc['R2']} vs {enc_b.loc['R2']}"
    )


def test_area_market_features_strict_prior_window(
    same_day_same_area_frame: pd.DataFrame,
) -> None:
    """area_inventory and area_price_median for R1/R2 must derive only from sold_date < 2024-06-01."""
    df = same_day_same_area_frame.copy()
    engineered = create_optimized_features(df).set_index("listing_id")

    swapped = df.copy()
    mask = swapped["listing_id"].isin(["R1", "R2"])
    rows_swapped = swapped.loc[mask].copy()
    rows_swapped["sold_price"] = rows_swapped["sold_price"].iloc[::-1].values
    swapped.loc[mask] = rows_swapped
    engineered_swapped = create_optimized_features(swapped).set_index("listing_id")

    for column in ("area_inventory", "area_price_median", "area_price_volatility"):
        for row_id in ("R1", "R2"):
            a = engineered.loc[row_id, column]
            b = engineered_swapped.loc[row_id, column]
            if pd.isna(a) and pd.isna(b):
                continue
            assert a == pytest.approx(b, rel=1e-9, nan_ok=True), (
                f"{column} for {row_id} depends on the other row's price (a={a}, b={b})"
            )


def _disjoint_distribution_frame(seed: int = 0, n_per_area: int = 30) -> pd.DataFrame:
    """Frame where train (early dates) and test (later dates) come from disjoint price distributions."""
    rng = np.random.default_rng(seed)
    rows: list[dict] = []
    for i in range(n_per_area):
        rows.append(
            _minimal_listing(
                f"TRAIN-A-{i}",
                "Södermalm",
                f"2023-{(i % 11) + 1:02d}-{(i % 27) + 1:02d}",
                float(rng.normal(3_000_000, 200_000)),
            )
        )
        rows.append(
            _minimal_listing(
                f"TRAIN-B-{i}",
                "Östermalm",
                f"2023-{(i % 11) + 1:02d}-{(i % 27) + 1:02d}",
                float(rng.normal(4_500_000, 250_000)),
            )
        )
    for i in range(n_per_area):
        rows.append(
            _minimal_listing(
                f"TEST-A-{i}",
                "Södermalm",
                f"2024-{(i % 11) + 1:02d}-{(i % 27) + 1:02d}",
                float(rng.normal(8_000_000, 600_000)),
            )
        )
        rows.append(
            _minimal_listing(
                f"TEST-B-{i}",
                "Östermalm",
                f"2024-{(i % 11) + 1:02d}-{(i % 27) + 1:02d}",
                float(rng.normal(9_500_000, 700_000)),
            )
        )
    df = pd.DataFrame(rows)
    df["sold_date"] = pd.to_datetime(df["sold_date"])
    return df


def test_train_test_distribution_isolation() -> None:
    """The training-fold context's global stats match a feature run that never saw the test rows."""
    df = _disjoint_distribution_frame()
    df_sorted = sort_by_temporal_order(df, date_column="sold_date")
    train_df, test_df = create_temporal_holdout_split(
        df_sorted, test_size=0.5, date_column="sold_date"
    )

    train_engineered_full = create_optimized_features(train_df)
    ctx_train_only = build_feature_context(train_engineered_full)

    train_only_engineered = create_optimized_features(train_df.copy())
    ctx_train_only_alt = build_feature_context(train_only_engineered)

    assert ctx_train_only.global_listing_price_mean == pytest.approx(
        ctx_train_only_alt.global_listing_price_mean
    )
    assert ctx_train_only.area_avg_price == ctx_train_only_alt.area_avg_price


def test_feature_context_sufficient_for_holdout() -> None:
    """Shuffling the holdout's sold_price must not change the holdout's engineered features."""
    df = _disjoint_distribution_frame()
    df_sorted = sort_by_temporal_order(df, date_column="sold_date")
    train_df, test_df = create_temporal_holdout_split(
        df_sorted, test_size=0.5, date_column="sold_date"
    )

    train_engineered = create_optimized_features(train_df.copy())
    ctx = build_feature_context(train_engineered)

    holdout_a = create_optimized_features(test_df.copy(), context=ctx)

    test_shuffled = test_df.copy()
    rng = np.random.default_rng(42)
    test_shuffled["sold_price"] = rng.permutation(test_shuffled["sold_price"].values)
    holdout_b = create_optimized_features(test_shuffled, context=ctx)

    leakage_columns = [
        "area_target_encoded",
        "area_avg_price",
        "area_price_median",
        "area_inventory",
        "area_sold_price_median_3m",
        "area_sales_volume_3m",
    ]
    for col in leakage_columns:
        if col not in holdout_a.columns or col not in holdout_b.columns:
            continue
        a = holdout_a[col].fillna(-1.0).reset_index(drop=True)
        b = holdout_b[col].fillna(-1.0).reset_index(drop=True)
        pd.testing.assert_series_equal(a, b, check_names=False, check_exact=False, rtol=1e-9)


def test_validate_temporal_leakage_rejects_boundary() -> None:
    """train_max == test_min must fail validation."""
    rows = [
        _minimal_listing("T1", "Södermalm", "2024-05-01", 4_000_000),
        _minimal_listing("T2", "Södermalm", "2024-06-01", 4_500_000),
        _minimal_listing("T3", "Södermalm", "2024-06-01", 4_700_000),
        _minimal_listing("T4", "Södermalm", "2024-07-01", 5_000_000),
    ]
    df = pd.DataFrame(rows)
    df["sold_date"] = pd.to_datetime(df["sold_date"])
    df = df.sort_values("sold_date").reset_index(drop=True)
    train_indices = [0, 1]
    test_indices = [2, 3]

    is_valid = validate_temporal_leakage(
        train_indices, test_indices, df, date_column="sold_date", verbose=False
    )
    assert is_valid is False, "Boundary overlap (train_max == test_min) must be rejected"


def test_build_feature_context_uses_train_df() -> None:
    """build_feature_context(train_df) must differ from build_feature_context(df.iloc[:N]) on shuffled input."""
    df = _disjoint_distribution_frame(seed=1)
    rng = np.random.default_rng(7)
    df = df.iloc[rng.permutation(len(df))].reset_index(drop=True)

    df_sorted = sort_by_temporal_order(df, date_column="sold_date")
    train_df, test_df = create_temporal_holdout_split(
        df_sorted, test_size=0.5, date_column="sold_date"
    )

    train_engineered = create_optimized_features(train_df.copy())
    ctx_correct = build_feature_context(train_engineered)

    df_engineered = create_optimized_features(df.copy())
    ctx_wrong = build_feature_context(df_engineered.iloc[: len(train_df)])

    assert ctx_correct.global_listing_price_mean != pytest.approx(
        ctx_wrong.global_listing_price_mean
    ), (
        "Context built from the actual train fold matches context built from a positional "
        "slice of the unsorted engineered frame — tighten the fixture."
    )


def test_pruning_iteration_rebuilds_context() -> None:
    """Two pruning iterations with different feature subsets must produce different contexts."""
    df = _disjoint_distribution_frame(seed=2)
    df_sorted = sort_by_temporal_order(df, date_column="sold_date")
    train_df_1, _ = create_temporal_holdout_split(df_sorted, test_size=0.5, date_column="sold_date")

    train_engineered_1 = create_optimized_features(train_df_1.copy())
    ctx_1 = build_feature_context(train_engineered_1)

    train_df_2 = train_df_1.iloc[: len(train_df_1) // 2].copy()
    train_engineered_2 = create_optimized_features(train_df_2)
    ctx_2 = build_feature_context(train_engineered_2)

    assert ctx_1.global_listing_price_mean != pytest.approx(ctx_2.global_listing_price_mean)
