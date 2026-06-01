"""Training evaluation reports."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, mean_squared_error


def generate_price_tier_analysis(
    y_test: pd.Series,
    predictions: dict[str, np.ndarray],
) -> pd.DataFrame:
    """Analyze performance across price tiers."""
    price_tiers = {
        "Budget": (0, 4_000_000),
        "Mid-range": (4_000_000, 6_000_000),
        "Premium": (6_000_000, 8_000_000),
        "Luxury": (8_000_000, float("inf")),
    }

    results = []
    for tier_name, (low, high) in price_tiers.items():
        mask = (y_test >= low) & (y_test < high)
        n_samples = mask.sum()

        if n_samples == 0:
            continue

        tier_result = {
            "tier": tier_name,
            "price_range": f"{low / 1e6:.0f}M-{high / 1e6:.0f}M"
            if high < float("inf")
            else f">{low / 1e6:.0f}M",
            "n_samples": int(n_samples),
        }

        for model_name, preds in predictions.items():
            mae = mean_absolute_error(y_test[mask], preds[mask])
            rmse = np.sqrt(mean_squared_error(y_test[mask], preds[mask]))
            mape = mean_absolute_percentage_error(y_test[mask], preds[mask])

            tier_result[f"{model_name}_MAE"] = float(mae)
            tier_result[f"{model_name}_RMSE"] = float(rmse)
            tier_result[f"{model_name}_MAPE"] = float(mape)

        results.append(tier_result)

    return pd.DataFrame(results)


def generate_area_performance_report(
    test_df: pd.DataFrame,
    y_test: pd.Series,
    predictions: dict[str, np.ndarray],
    min_samples: int = 5,
) -> pd.DataFrame:
    """Analyze performance by geographic area."""
    if "area" not in test_df.columns:
        return pd.DataFrame()

    test_df_reset = test_df.reset_index(drop=True)
    y_test_reset = y_test.reset_index(drop=True)

    results = []
    for area in test_df_reset["area"].unique():
        if pd.isna(area):
            continue

        mask = test_df_reset["area"] == area
        n_samples = mask.sum()

        if n_samples < min_samples:
            continue

        area_result = {
            "area": area,
            "n_samples": int(n_samples),
        }

        for model_name, preds in predictions.items():
            mae = mean_absolute_error(y_test_reset[mask], preds[mask])
            area_result[f"{model_name}_MAE"] = float(mae)

        results.append(area_result)

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results)
    if "LGBM_MAE" in df.columns:
        df = df.sort_values("LGBM_MAE")

    return df


def analyze_prediction_errors(
    y_test: pd.Series,
    test_df: pd.DataFrame,
    predictions: dict[str, np.ndarray],
    n_worst: int = 10,
) -> dict:
    """Analyze worst prediction errors for each model."""
    if "listing_id" in test_df.columns:
        listing_ids = test_df["listing_id"].values
    else:
        listing_ids = [f"sample_{i}" for i in range(len(y_test))]

    error_data = []
    for model_name, preds in predictions.items():
        for actual, predicted, listing_id in zip(y_test.values, preds, listing_ids, strict=True):
            error = predicted - actual
            abs_error = abs(error)
            error_data.append(
                {
                    "listing_id": str(listing_id),
                    "model": model_name,
                    "actual": float(actual),
                    "predicted": float(predicted),
                    "error": float(error),
                    "abs_error": float(abs_error),
                    "error_pct": float(abs_error / actual * 100),
                }
            )

    error_df = pd.DataFrame(error_data)
    under_predictions = error_df[error_df["error"] < 0].nlargest(n_worst, "abs_error")
    over_predictions = error_df[error_df["error"] > 0].nlargest(n_worst, "abs_error")

    return {
        "worst_under_predictions": under_predictions.to_dict("records"),
        "worst_over_predictions": over_predictions.to_dict("records"),
        "summary": {
            "total_predictions": len(y_test) * len(predictions),
            "models_analyzed": list(predictions.keys()),
            "n_worst_shown": n_worst,
        },
    }
