from __future__ import annotations

import pandas as pd

from estate_value_index.ml.features import build_feature_context, create_optimized_features
from estate_value_index.ml.features.address_comps import normalize_street_name


def _listing(
    listing_id: str,
    sold_date: str,
    price_per_sqm: float,
    *,
    address: str = "Grev Magnigatan 17A",
    area: str = "Östermalm",
    living_area: float = 100.0,
) -> dict:
    return {
        "listing_id": listing_id,
        "area": area,
        "address": address,
        "sold_date": pd.Timestamp(sold_date),
        "scraped_at": pd.Timestamp(sold_date) - pd.Timedelta(days=10),
        "sold_price": price_per_sqm * living_area,
        "listing_price": price_per_sqm * living_area * 0.97,
        "living_area": living_area,
        "rooms": 4.0,
        "monthly_fee": 5000.0,
        "days_on_market": 12,
        "construction_year": 1910,
        "property_type": "Lägenhet",
        "latitude": 59.335,
        "longitude": 18.085,
    }


def test_normalize_street_name_removes_house_number() -> None:
    assert normalize_street_name("Grev Magnigatan 17A") == "grev magnigatan"
    assert normalize_street_name("Norr Mälarstrand 62 / 4 tr") == "norr mälarstrand"
    assert normalize_street_name(None) == "unknown"


def test_street_area_comp_uses_prior_street_history() -> None:
    rows = [_listing(f"P{i}", f"2024-01-{i + 1:02d}", 150_000 + i * 1000) for i in range(5)]
    rows.append(_listing("TARGET", "2024-02-01", 190_000))

    engineered = create_optimized_features(pd.DataFrame(rows)).set_index("listing_id")

    assert engineered.loc["TARGET", "street_name"] == "grev magnigatan"
    assert engineered.loc["TARGET", "street_area_scope_used"] == "street_area"
    assert engineered.loc["TARGET", "street_area_ppsqm_count"] == 5
    assert (
        engineered.loc["TARGET", "street_area_ppsqm_p90"]
        >= engineered.loc["TARGET", "street_area_ppsqm_median"]
    )


def test_address_comp_uses_prior_exact_address_history() -> None:
    rows = [_listing(f"A{i}", f"2024-01-{i + 1:02d}", 155_000 + i * 1000) for i in range(3)]
    rows.extend(
        [
            _listing(
                f"S{i}",
                f"2024-01-{i + 4:02d}",
                145_000 + i * 1000,
                address="Grev Magnigatan 19",
            )
            for i in range(2)
        ]
    )
    rows.append(_listing("TARGET", "2024-02-01", 190_000))

    engineered = create_optimized_features(pd.DataFrame(rows)).set_index("listing_id")

    assert engineered.loc["TARGET", "address_comp_scope_used"] == "address"
    assert engineered.loc["TARGET", "address_ppsqm_count"] == 3
    assert engineered.loc["TARGET", "address_ppsqm_median"] > 0


def test_address_comp_features_do_not_use_same_day_labels() -> None:
    rows = [_listing(f"P{i}", f"2024-01-{i + 1:02d}", 150_000 + i * 1000) for i in range(5)]
    rows.extend(
        [
            _listing("R1", "2024-06-01", 160_000),
            _listing("R2", "2024-06-01", 300_000),
        ]
    )
    df = pd.DataFrame(rows)
    engineered = create_optimized_features(df).set_index("listing_id")

    swapped = df.copy()
    mask = swapped["listing_id"].isin(["R1", "R2"])
    swapped.loc[mask, "sold_price"] = swapped.loc[mask, "sold_price"].iloc[::-1].values
    engineered_swapped = create_optimized_features(swapped).set_index("listing_id")

    for column in (
        "street_area_ppsqm_median",
        "street_area_ppsqm_p90",
        "street_area_ppsqm_count",
        "street_size_ppsqm_median",
        "street_size_ppsqm_p90",
        "address_ppsqm_median",
        "address_ppsqm_p90",
        "address_ppsqm_count",
        "address_comp_scope_used",
    ):
        for row_id in ("R1", "R2"):
            assert engineered.loc[row_id, column] == engineered_swapped.loc[row_id, column]


def test_context_address_comp_features_do_not_use_holdout_labels() -> None:
    train = pd.DataFrame(
        [_listing(f"TRAIN-{i}", f"2024-01-{i + 1:02d}", 150_000 + i * 1000) for i in range(5)]
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
        "street_area_ppsqm_median",
        "street_area_ppsqm_p90",
        "street_area_ppsqm_count",
        "street_size_ppsqm_median",
        "street_size_ppsqm_p90",
        "address_ppsqm_median",
        "address_ppsqm_p90",
        "address_ppsqm_count",
        "street_name",
        "address_comp_scope_used",
    ):
        assert holdout_a[column].iloc[0] == holdout_b[column].iloc[0]
