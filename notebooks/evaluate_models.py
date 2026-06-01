#!/usr/bin/env python3
"""Evaluate trained price prediction models and generate comparison plots.

Not the production training/eval path: this script uses a random ``train_test_split``
after full feature engineering. For temporal, leakage-safe evaluation use
``train_model.py`` and the tests under ``tests/ml/``.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

# Repo root (parent of notebooks/)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import (
    mean_absolute_error,
    mean_absolute_percentage_error,
    mean_squared_error,
    r2_score,
)
from sklearn.model_selection import train_test_split

from estate_value_index.ml import (
    create_optimized_features,
    drop_outliers_quantile,
    filter_valid_listings,
    get_feature_lists,
)

DEFAULT_DATA_PATH = Path("data/raw/booli/booli_listings_prod.json")
DEFAULT_MODELS_DIR = Path("web/models")
DEFAULT_MODEL_PREFIX = "price_prediction_model"
OUTPUT_DIR = Path("reports/figures")
METRICS_PATH = Path("reports/model_evaluation_metrics.json")


def load_booli_records(data_path: Path) -> pd.DataFrame:
    if not data_path.exists():
        raise FileNotFoundError(f"Data file not found: {data_path}")

    try:
        with open(data_path) as f:
            return pd.DataFrame(json.load(f))
    except json.JSONDecodeError:
        records = []
        with open(data_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return pd.DataFrame(records)


def prepare_dataset(data_path: Path) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    raw = load_booli_records(data_path)
    filtered = filter_valid_listings(raw, min_price=3_000_000, drop_na_features=False)
    filtered = drop_outliers_quantile(filtered, lower=0.01, upper=0.99)
    engineered = create_optimized_features(filtered)

    _, _, all_features = get_feature_lists()
    X = engineered[all_features].copy()
    y = engineered["sold_price"].copy()
    # Also return listing_id for error analysis
    listing_ids = engineered["listing_id"].copy()
    return X, y, listing_ids


def load_pipeline(models_dir: Path, prefix: str, suffix: str):
    path = models_dir / f"{prefix}_{suffix}.joblib"
    if not path.exists():
        raise FileNotFoundError(f"Model artifact missing: {path}")
    return joblib.load(path)


def evaluate_models(
    data_path: Path = DEFAULT_DATA_PATH,
    models_dir: Path = DEFAULT_MODELS_DIR,
    model_prefix: str = DEFAULT_MODEL_PREFIX,
) -> None:
    X, y, listing_ids = prepare_dataset(data_path)
    X_train, X_test, y_train, y_test, train_ids, test_ids = train_test_split(
        X, y, listing_ids, test_size=0.2, random_state=42
    )

    model_suffixes = {
        "LightGBM": "lgbm",
    }

    predictions: dict[str, np.ndarray] = {}
    metrics: dict[str, dict[str, float]] = {}

    for label, suffix in model_suffixes.items():
        pipeline = load_pipeline(models_dir, model_prefix, suffix)
        preds = np.asarray(pipeline.predict(X_test), dtype=float)
        predictions[label] = preds

        mae = mean_absolute_error(y_test, preds)
        rmse = np.sqrt(mean_squared_error(y_test, preds))
        mape = mean_absolute_percentage_error(y_test, preds)
        r2 = r2_score(y_test, preds)

        metrics[label] = {
            "mae": float(mae),
            "rmse": float(rmse),
            "mape": float(mape),
            "r2": float(r2),
        }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Scatter plot (actual vs predicted)
    # Assign color to LightGBM model
    model_colors = {
        "LightGBM": "#ff7f0e",  # orange
    }

    fig, ax = plt.subplots(1, 1, figsize=(8, 6))
    min_val = min(y_test.min(), *(pred.min() for pred in predictions.values()))
    max_val = max(y_test.max(), *(pred.max() for pred in predictions.values()))

    # Since we only have one model now, just plot it
    label, preds = next(iter(predictions.items()))
    color = model_colors.get(label, "#ff7f0e")
    ax.scatter(y_test, preds, alpha=0.6, edgecolor="none", color=color)
    ax.plot([min_val, max_val], [min_val, max_val], "k--", linewidth=1)
    ax.set_title(f"{label} - Actual vs Predicted Prices")
    ax.set_xlabel("Actual Price (SEK)")
    ax.set_ylabel("Predicted Price (SEK)")
    ax.grid(True, alpha=0.2)

    fig.tight_layout()
    scatter_path = OUTPUT_DIR / "model_scatter_grid.png"
    fig.savefig(scatter_path, dpi=200)
    plt.close(fig)

    # Residual distribution
    fig, ax = plt.subplots(1, 1, figsize=(8, 6))
    residuals = {label: preds - y_test for label, preds in predictions.items()}

    # Since we only have one model now, just plot it
    label, res = next(iter(residuals.items()))
    color = model_colors.get(label, "#ff7f0e")
    ax.hist(res, bins=40, alpha=0.75, color=color)
    ax.axvline(0, color="black", linestyle="--", linewidth=1)
    ax.set_title(f"{label} - Residual Distribution")
    ax.set_xlabel("Residual (Predicted - Actual)")
    ax.set_ylabel("Frequency")
    ax.grid(True, alpha=0.2)

    fig.tight_layout()
    residual_path = OUTPUT_DIR / "model_residual_grid.png"
    fig.savefig(residual_path, dpi=200)
    plt.close(fig)

    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(METRICS_PATH, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)

    # Analyze prediction errors
    print("\n" + "=" * 80)
    print("TOP 10 HIGHEST PREDICTION ERRORS ANALYSIS")
    print("=" * 80)

    # Calculate errors and create comparison dataframe
    comparison_data = []
    for label, preds in predictions.items():
        for actual, predicted, listing_id in zip(y_test, preds, test_ids):
            error = predicted - actual
            abs_error = abs(error)
            comparison_data.append(
                {
                    "listing_id": listing_id,
                    "actual": actual,
                    "predicted": predicted,
                    "error": error,
                    "abs_error": abs_error,
                    "model": label,
                    "error_pct": abs_error / actual * 100,
                }
            )

    comparison_df = pd.DataFrame(comparison_data)

    # Top 10 UNDER-predictions (predicted too low)
    print("\n🔻 TOP 10 UNDER-PREDICTIONS (Predicted Too Low)")
    print("-" * 80)
    under_predictions = comparison_df[comparison_df["error"] < 0].nlargest(10, "abs_error")
    for rank, (_, row) in enumerate(under_predictions.iterrows(), start=1):
        print(
            f"#{rank:2d} | ID: {row['listing_id']:8s} | Model: {row['model']:15s} | "
            f"Actual: {row['actual']:8,.0f} | "
            f"Pred: {row['predicted']:8,.0f} | "
            f"Error: {row['error']:8,.0f} | "
            f"AbsErr: {row['abs_error']:8,.0f} | "
            f"Error%: {row['error_pct']:5.1f}%"
        )

    # Top 10 OVER-predictions (predicted too high)
    print("\n🔺 TOP 10 OVER-PREDICTIONS (Predicted Too High)")
    print("-" * 80)
    over_predictions = comparison_df[comparison_df["error"] > 0].nlargest(10, "abs_error")
    for rank, (_, row) in enumerate(over_predictions.iterrows(), start=1):
        print(
            f"#{rank:2d} | ID: {row['listing_id']:8s} | Model: {row['model']:15s} | "
            f"Actual: {row['actual']:8,.0f} | "
            f"Pred: {row['predicted']:8,.0f} | "
            f"Error: {row['error']:8,.0f} | "
            f"AbsErr: {row['abs_error']:8,.0f} | "
            f"Error%: {row['error_pct']:5.1f}%"
        )

    print(f"\n💾 Saved scatter plot to {scatter_path}")
    print(f"💾 Saved residual plot to {residual_path}")
    print(f"💾 Metrics written to {METRICS_PATH}")


if __name__ == "__main__":
    evaluate_models()
