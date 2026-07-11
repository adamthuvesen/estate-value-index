from __future__ import annotations

import pandas as pd

from estate_value_index.ml.features import build_feature_context, create_optimized_features
from estate_value_index.ml.features.micro_area import create_h3_cell


def _listing(
    listing_id: str,
    sold_date: str,
    price_per_sqm: float,
    *,
    area: str = "Södermalm",
    lat: float = 59.315,
    lon: float = 18.07,
) -> dict:
    return {
        "listing_id": listing_id,
        "area": area,
        "sold_date": pd.Timestamp(sold_date),
        "scraped_at": pd.Timestamp(sold_date) - pd.Timedelta(days=10),
        "sold_price": price_per_sqm * 50,
        "listing_price": price_per_sqm * 50 * 0.97,
        "living_area": 50.0,
        "rooms": 2.0,
        "monthly_fee": 3000.0,
        "days_on_market": 12,
        "construction_year": 1970,
        "property_type": "Lägenhet",
        "latitude": lat,
        "longitude": lon,
    }


def test_h3_cell_assignment_is_deterministic() -> None:
    assert create_h3_cell(59.315, 18.07, 10) == create_h3_cell(59.315, 18.07, 10)


def test_coordinate_aliases_create_h3_cells() -> None:
    df = pd.DataFrame([_listing("A", "2024-01-01", 80_000)])
    engineered = create_optimized_features(df)

    assert engineered["lat"].iloc[0] == 59.315
    assert engineered["lon"].iloc[0] == 18.07
    assert isinstance(engineered["h3_res10"].iloc[0], str)
    assert isinstance(engineered["h3_res9"].iloc[0], str)


def test_micro_area_uses_res10_after_min_prior_count() -> None:
    rows = [_listing(f"P{i}", f"2024-01-{i + 1:02d}", 80_000 + i) for i in range(20)]
    rows.append(_listing("TARGET", "2024-02-01", 95_000))

    engineered = create_optimized_features(pd.DataFrame(rows)).set_index("listing_id")

    assert engineered.loc["TARGET", "micro_area_resolution_used"] == "h3_res10"
    assert engineered.loc["TARGET", "micro_area_ppsqm_count"] == 20
    assert engineered.loc["TARGET", "micro_area_ppsqm_median"] > 0
    assert (
        engineered.loc["TARGET", "micro_area_ppsqm_p75"]
        >= engineered.loc["TARGET", "micro_area_ppsqm_median"]
    )
    assert (
        engineered.loc["TARGET", "micro_area_ppsqm_p90"]
        >= engineered.loc["TARGET", "micro_area_ppsqm_p75"]
    )
    assert engineered.loc["TARGET", "micro_area_upper_tail_ratio"] >= 1.0


def test_sparse_micro_area_falls_back_to_area() -> None:
    rows = [
        _listing(f"P{i}", f"2024-01-{i + 1:02d}", 70_000 + i, lat=59.31 + i * 0.001)
        for i in range(3)
    ]
    rows.append(_listing("TARGET", "2024-02-01", 75_000, lat=59.36, lon=18.11))

    engineered = create_optimized_features(pd.DataFrame(rows)).set_index("listing_id")

    assert engineered.loc["TARGET", "micro_area_resolution_used"] == "area"
    assert engineered.loc["TARGET", "micro_area_ppsqm_count"] == 3


def test_context_micro_area_features_do_not_use_holdout_labels() -> None:
    train = pd.DataFrame(
        [_listing(f"TRAIN-{i}", f"2024-01-{i + 1:02d}", 80_000 + i) for i in range(20)]
    )
    test = pd.DataFrame([_listing("TEST", "2024-03-01", 250_000)])

    train_engineered = create_optimized_features(train)
    context = build_feature_context(train_engineered)
    holdout_a = create_optimized_features(test.copy(), context=context)

    shuffled = test.copy()
    shuffled["sold_price"] = 1_000_000
    shuffled["price_per_sqm"] = 20_000
    holdout_b = create_optimized_features(shuffled, context=context)

    for column in (
        "micro_area_ppsqm_median",
        "micro_area_ppsqm_p75",
        "micro_area_ppsqm_p90",
        "micro_area_ppsqm_count",
        "micro_area_ppsqm_premium_vs_area",
        "micro_area_upper_tail_ratio",
        "micro_area_resolution_used",
        "h3_neighbor_ppsqm",
        "h3_neighbor_ppsqm_p75",
        "h3_neighbor_ppsqm_p90",
        "h3_neighbor_ppsqm_count",
        "h3_neighbor_premium_vs_micro",
        "h3_neighbor_upper_tail_ratio",
        "same_size_ppsqm_median",
        "same_size_ppsqm_p75",
        "same_size_ppsqm_p90",
        "same_size_ppsqm_count",
        "same_size_premium_vs_area",
        "same_size_upper_tail_ratio",
        "same_size_scope_used",
        "h3_market_ppsqm_ratio",
        "same_size_market_ppsqm_ratio",
        "neighbor_market_ppsqm_ratio",
        "micro_luxury_score",
        "luxury_location_flag",
        "luxury_location_tier",
    ):
        assert holdout_a[column].iloc[0] == holdout_b[column].iloc[0]


def test_same_size_comp_uses_prior_h3_size_history() -> None:
    rows = [
        _listing(
            f"P{i}",
            f"2024-01-{i + 1:02d}",
            80_000 + i,
            lat=59.315 + i * 0.00001,
        )
        for i in range(5)
    ]
    rows.append(_listing("TARGET", "2024-02-01", 95_000, lat=59.3152))

    engineered = create_optimized_features(pd.DataFrame(rows)).set_index("listing_id")

    assert engineered.loc["TARGET", "same_size_scope_used"] == "h3_res9_size"
    assert engineered.loc["TARGET", "same_size_ppsqm_count"] == 5
    assert engineered.loc["TARGET", "same_size_ppsqm_median"] > 0
    assert (
        engineered.loc["TARGET", "same_size_ppsqm_p75"]
        >= engineered.loc["TARGET", "same_size_ppsqm_median"]
    )
    assert (
        engineered.loc["TARGET", "same_size_ppsqm_p90"]
        >= engineered.loc["TARGET", "same_size_ppsqm_p75"]
    )
    assert engineered.loc["TARGET", "same_size_upper_tail_ratio"] >= 1.0


def test_h3_neighbor_features_use_prior_adjacent_cells() -> None:
    target_cell = create_h3_cell(59.315, 18.07, 10)
    assert target_cell is not None

    import h3

    neighbor = next(cell for cell in h3.grid_disk(target_cell, 1) if cell != target_cell)
    lat, lon = h3.cell_to_latlng(neighbor)
    rows = [
        _listing(f"P{i}", f"2024-01-{i + 1:02d}", 82_000 + i, lat=lat, lon=lon) for i in range(3)
    ]
    rows.append(_listing("TARGET", "2024-02-01", 95_000, lat=59.315, lon=18.07))

    engineered = create_optimized_features(pd.DataFrame(rows)).set_index("listing_id")

    assert engineered.loc["TARGET", "h3_neighbor_ppsqm_count"] == 3
    assert engineered.loc["TARGET", "h3_neighbor_ppsqm"] > 0
    assert (
        engineered.loc["TARGET", "h3_neighbor_ppsqm_p75"]
        >= engineered.loc["TARGET", "h3_neighbor_ppsqm"]
    )
    assert (
        engineered.loc["TARGET", "h3_neighbor_ppsqm_p90"]
        >= engineered.loc["TARGET", "h3_neighbor_ppsqm_p75"]
    )
    assert engineered.loc["TARGET", "h3_neighbor_upper_tail_ratio"] >= 1.0
