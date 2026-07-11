"""Per-bucket estimate-range factors: bucketing, fallback, recent slice, payload."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

from estate_value_index.ml.estimate_range_factors import (
    MIN_BUCKET_SAMPLES,
    compute_estimate_range_factors,
)
from estate_value_index.ml.production_models import _metrics_payload


def _frame(predicted, ratios, dates):
    predicted = np.asarray(predicted, dtype=float)
    actual = predicted * np.asarray(ratios, dtype=float)
    frame = pd.DataFrame({"sold_date": pd.to_datetime(dates), "sold_price": actual})
    return frame, predicted


def test_predictions_land_in_the_expected_buckets() -> None:
    n = 150
    predicted = [3_500_000.0] * n + [7_000_000.0] * n
    ratios = list(np.linspace(0.9, 1.1, n)) * 2
    dates = ["2026-07-01"] * (2 * n)
    frame, preds = _frame(predicted, ratios, dates)

    result = compute_estimate_range_factors(frame, preds)
    buckets = result["buckets"]

    assert buckets[0]["upper_edge"] == 4_000_000  # 3-4M
    assert buckets[0]["sample_size"] == n
    assert buckets[0]["fallback"] is False
    assert buckets[3]["lower_edge"] == 6_000_000  # 6-8M
    assert buckets[3]["sample_size"] == n
    # The last bucket runs to infinity.
    assert buckets[-1]["upper_edge"] is None
    # Empty buckets fall back to the pooled quantiles.
    assert buckets[1]["sample_size"] == 0
    assert buckets[1]["fallback"] is True
    assert buckets[1]["lower"] == result["pooled"]["lower"]


def test_thin_bucket_falls_back_to_pooled() -> None:
    thin = MIN_BUCKET_SAMPLES - 1
    full = MIN_BUCKET_SAMPLES + 20
    predicted = [3_500_000.0] * thin + [7_000_000.0] * full
    ratios = list(np.linspace(0.7, 1.3, thin)) + list(np.linspace(0.9, 1.1, full))
    dates = ["2026-07-01"] * (thin + full)
    frame, preds = _frame(predicted, ratios, dates)

    result = compute_estimate_range_factors(frame, preds)
    low_bucket = result["buckets"][0]

    assert low_bucket["sample_size"] == thin
    assert low_bucket["fallback"] is True
    assert low_bucket["lower"] == result["pooled"]["lower"]
    assert low_bucket["upper"] == result["pooled"]["upper"]


def test_recent_slice_excludes_old_rows() -> None:
    n = 150
    recent_ratios = list(np.linspace(0.95, 1.05, n))
    frame_recent, preds_recent = _frame([3_500_000.0] * n, recent_ratios, ["2026-07-01"] * n)
    baseline = compute_estimate_range_factors(frame_recent, preds_recent)

    # Add a pile of old rows with wild ratios; they predate the 3-month cutoff.
    predicted = [3_500_000.0] * n + [3_500_000.0] * n
    ratios = recent_ratios + [3.0] * n
    dates = ["2026-07-01"] * n + ["2026-01-01"] * n
    frame, preds = _frame(predicted, ratios, dates)
    with_old = compute_estimate_range_factors(frame, preds)

    assert with_old["buckets"][0]["lower"] == baseline["buckets"][0]["lower"]
    assert with_old["buckets"][0]["upper"] == baseline["buckets"][0]["upper"]
    assert with_old["sample_size"] == n
    assert with_old["slice_start"] == "2026-07-01"


def test_bands_are_asymmetric_for_skewed_ratios() -> None:
    n = 300
    # Right-skewed ratios: long upper tail, tight lower side.
    rng = np.random.default_rng(0)
    ratios = 1.0 + np.abs(rng.normal(0, 0.15, n))
    frame, preds = _frame([3_500_000.0] * n, ratios, ["2026-07-01"] * n)

    bucket = compute_estimate_range_factors(frame, preds)["buckets"][0]
    lower_gap = 1.0 - bucket["lower"]
    upper_gap = bucket["upper"] - 1.0

    assert bucket["lower"] < bucket["upper"]
    assert not np.isclose(lower_gap, upper_gap, atol=0.02)


def test_factors_rounded_to_four_decimals() -> None:
    n = 150
    ratios = list(np.linspace(0.912345, 1.087654, n))
    frame, preds = _frame([3_500_000.0] * n, ratios, ["2026-07-01"] * n)

    bucket = compute_estimate_range_factors(frame, preds)["buckets"][0]
    assert bucket["lower"] == round(bucket["lower"], 4)
    assert bucket["upper"] == round(bucket["upper"], 4)


def test_factors_land_in_metrics_payload() -> None:
    factors = {"buckets": [], "pooled": {"lower": 0.94, "upper": 1.04}, "interval_pct": 30}
    model = SimpleNamespace(
        model_id="no_list_price_v1",
        model_type="tiered",
        feature_set="no_list_price",
        requires_listing_price=False,
        numeric_features=["living_area"],
        categorical_features=["area"],
        market_blend_weight=0.0,
        overall_weights={},
        gated_weights_by_gate={},
        gate_low_max=5_000_000.0,
        gate_high_min=8_000_000.0,
    )
    heldout = {
        "mae": 1.0,
        "rmse": 1.0,
        "mape": 1.0,
        "median_ape": 1.0,
        "within_10_pct": 1.0,
        "within_20_pct": 1.0,
    }

    payload = _metrics_payload(
        model,
        heldout_metrics=heldout,
        calibration={"served": "uncalibrated"},
        estimate_range_factors=factors,
        train_rows=10,
        test_rows=5,
        production_rows=15,
        test_start="2026-01-01",
        test_end="2026-07-01",
        lgbm_params={"num_leaves": 20},
        tuned=True,
    )

    assert payload["estimate_range_factors"] is factors
    assert payload["training_parameters"] == {
        "source": "optuna",
        "lightgbm": {"num_leaves": 20},
    }
