"""Empirical per-bucket estimate-range factors (split-conformal style).

Measured on the most recent slice of the temporal holdout: per predicted-price
bucket, the q35/q65 quantiles of ``actual / predicted``. That 30% interval is
deliberately tight; the asymmetric bands it yields are intentional and must not
be symmetrized. The factors ship in the model metrics artifact and drive the
value window the web app shows in place of the raw point estimate.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Bucket edges by predicted price; the final bucket runs to infinity.
BUCKET_EDGES: tuple[float, ...] = (
    3_000_000.0,
    4_000_000.0,
    5_000_000.0,
    6_000_000.0,
    8_000_000.0,
    10_000_000.0,
    13_000_000.0,
    float("inf"),
)
# 30% interval via q35/q65 (design decision — do not widen or symmetrize).
LOWER_PERCENTILE = 35
UPPER_PERCENTILE = 65
INTERVAL_PCT = UPPER_PERCENTILE - LOWER_PERCENTILE
# The recent slice approximates the drift a frequently-retrained model faces.
RECENT_SLICE_MONTHS = 3
# Below this a bucket is too thin to trust; fall back to the pooled quantiles.
MIN_BUCKET_SAMPLES = 100


def compute_estimate_range_factors(
    eval_test: pd.DataFrame,
    predictions: np.ndarray,
) -> dict[str, object]:
    """Compute per-bucket ``actual / predicted`` quantile factors.

    Args:
        eval_test: Temporal holdout rows; needs ``sold_price`` and ``sold_date``.
        predictions: Held-out predictions aligned row-for-row with ``eval_test``.

    Returns:
        A JSON-serializable payload with the slice window, the interval
        percentiles, per-bucket ``{lower, upper, sample_size, fallback}`` factors
        rounded to 4 decimals, and the pooled fallback quantiles.
    """
    if len(predictions) != len(eval_test):
        raise ValueError(
            f"predictions ({len(predictions)}) and eval_test ({len(eval_test)}) length mismatch"
        )

    frame = eval_test.reset_index(drop=True)
    sold_date = pd.to_datetime(frame["sold_date"], errors="coerce")
    actual = frame["sold_price"].to_numpy(dtype=float)
    predicted = np.asarray(predictions, dtype=float)

    cutoff = sold_date.max() - pd.DateOffset(months=RECENT_SLICE_MONTHS)
    recent = (sold_date >= cutoff).to_numpy()
    # Guard against zero/NaN predictions producing non-finite ratios.
    valid = recent & np.isfinite(predicted) & np.isfinite(actual) & (predicted > 0)

    predicted = predicted[valid]
    actual = actual[valid]
    ratio = actual / predicted
    recent_dates = sold_date[valid]

    if ratio.size == 0:
        raise ValueError("no valid rows in the recent holdout slice for estimate-range factors")

    pooled_lower = round(float(np.percentile(ratio, LOWER_PERCENTILE)), 4)
    pooled_upper = round(float(np.percentile(ratio, UPPER_PERCENTILE)), 4)

    buckets: list[dict[str, object]] = []
    for lower_edge, upper_edge in zip(BUCKET_EDGES[:-1], BUCKET_EDGES[1:], strict=True):
        mask = (predicted >= lower_edge) & (predicted < upper_edge)
        n = int(mask.sum())
        if n >= MIN_BUCKET_SAMPLES:
            bucket_ratio = ratio[mask]
            lower = round(float(np.percentile(bucket_ratio, LOWER_PERCENTILE)), 4)
            upper = round(float(np.percentile(bucket_ratio, UPPER_PERCENTILE)), 4)
            fallback = False
        else:
            lower, upper = pooled_lower, pooled_upper
            fallback = True
        buckets.append(
            {
                "lower_edge": None if lower_edge == float("inf") else int(lower_edge),
                "upper_edge": None if upper_edge == float("inf") else int(upper_edge),
                "lower": lower,
                "upper": upper,
                "sample_size": n,
                "fallback": fallback,
            }
        )

    return {
        "interval_pct": INTERVAL_PCT,
        "lower_percentile": LOWER_PERCENTILE,
        "upper_percentile": UPPER_PERCENTILE,
        "recent_slice_months": RECENT_SLICE_MONTHS,
        "min_bucket_samples": MIN_BUCKET_SAMPLES,
        "slice_start": str(recent_dates.min().date()),
        "slice_end": str(recent_dates.max().date()),
        "sample_size": int(ratio.size),
        "pooled": {"lower": pooled_lower, "upper": pooled_upper},
        "buckets": buckets,
    }
