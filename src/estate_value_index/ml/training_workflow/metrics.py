"""Training metrics and model fitting."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, mean_squared_error


def regression_metrics(y_true: pd.Series, y_pred: np.ndarray) -> dict[str, float]:
    """Compute common regression metrics for a prediction."""
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    mape = mean_absolute_percentage_error(y_true, y_pred)
    true_values = y_true.to_numpy(dtype=float)
    pred_values = np.asarray(y_pred, dtype=float)
    valid_pct_mask = np.isfinite(true_values) & (true_values != 0)
    absolute_pct_error = np.full_like(true_values, np.nan, dtype=float)
    absolute_pct_error[valid_pct_mask] = np.abs(
        (pred_values[valid_pct_mask] - true_values[valid_pct_mask]) / true_values[valid_pct_mask]
    )
    # A zero (or missing) sold_price divides to inf; drop those rows from the
    # population instead of letting one bad row poison median_ape, which now
    # gates model acceptance and drift. Mirrors residual_calibration.py's
    # _prediction_metrics so both metrics paths agree on edge cases.
    absolute_pct_error = np.where(np.isinf(absolute_pct_error), np.nan, absolute_pct_error)
    valid_pct_errors = absolute_pct_error[np.isfinite(absolute_pct_error)]
    within_10_pct = np.mean(valid_pct_errors <= 0.10) * 100 if len(valid_pct_errors) else np.nan
    within_20_pct = np.mean(valid_pct_errors <= 0.20) * 100 if len(valid_pct_errors) else np.nan
    return {
        "mae": float(mae),
        "rmse": float(rmse),
        "mape": float(mape),
        # Median absolute % error — the AVM-standard headline metric (what Zillow
        # reports). Robust to the fat right tail that inflates the mean-based mape.
        "median_ape": float(np.nanmedian(absolute_pct_error)),
        # PPE10 / PPE20 — hit-rate within 10% / 20%, reported alongside MdAPE.
        "within_10_pct": float(within_10_pct),
        "within_20_pct": float(within_20_pct),
    }
