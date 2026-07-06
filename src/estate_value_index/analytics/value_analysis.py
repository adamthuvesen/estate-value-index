"""Generate value analysis data by running predictions on all production listings.

Loads the best LGBM model and generates predictions for all properties in the
production dataset, then calculates value metrics to identify undervalued
properties (where the model over-predicted the sold price).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import norm

# Import preprocessing functions to match training pipeline
from estate_value_index.ml import drop_outliers_quantile, filter_valid_listings

logger = logging.getLogger(__name__)

# Fields that must be real (not feature-filled) for a value score to be
# trustworthy. price_per_sqm is derived from living_area, so the two go missing
# together; see docs/internal/value-finder-missingness-analysis.md.
CORE_RANK_FIELDS = ("living_area", "price_per_sqm")


def load_production_data(data_path: Path, apply_training_filters: bool = True) -> pd.DataFrame:
    """Load production listing data from JSON or JSONL file.

    Args:
        data_path: Path to the data file
        apply_training_filters: If True, apply the same filters used during training
                               (min_price=3M, outlier removal at 1st-99th percentile)
    """
    logger.info("Loading data from: %s", data_path)

    # Support both a JSON array (single- or multi-line) and JSONL. Sniff the
    # first non-whitespace char: a single-line array parses as one "line", so
    # trying JSONL first would silently wrap the whole array in one row.
    with open(data_path, encoding="utf-8") as f:
        content = f.read()
    if content.lstrip().startswith("["):
        data = json.loads(content)
        logger.info("Loaded %s listings (JSON array)", f"{len(data):,}")
    else:
        data = [json.loads(line) for line in content.splitlines() if line.strip()]
        logger.info("Loaded %s listings (JSONL)", f"{len(data):,}")

    df = pd.DataFrame(data)

    # Filter to only properties with sold_price (needed for comparison)
    df_with_price = df[df["sold_price"].notna()].copy()
    logger.info("%s listings with sold_price", f"{len(df_with_price):,}")

    # Apply the same preprocessing filters used during training
    if apply_training_filters:
        logger.info("Applying training filters")
        logger.info("Before filtering: %s listings", f"{len(df_with_price):,}")

        # Step 1: Filter valid listings (min_price=3M, same as training)
        df_filtered = filter_valid_listings(
            df_with_price,
            min_price=3000000,
            drop_na_features=False,
            require_listing_price=False,
        )
        logger.info("After min_price filter (>= 3M SEK): %s listings", f"{len(df_filtered):,}")

        # Step 2: Remove outliers using quantile filtering (1st-99th percentile, same as training)
        df_filtered = drop_outliers_quantile(df_filtered, lower=0.01, upper=0.99)
        logger.info(
            "After outlier removal (1st-99th percentile): %s listings", f"{len(df_filtered):,}"
        )

        return df_filtered

    return df_with_price


def load_model(models_dir: Path, model_type: str, prefix: str = "price_prediction_model") -> tuple:
    """Load trained model and its metrics."""
    model_path = models_dir / f"{prefix}_{model_type}.joblib"
    metrics_path = models_dir / f"{prefix}_{model_type}_metrics.json"
    if not metrics_path.exists():
        metrics_path = models_dir / f"{prefix}_metrics_{model_type}.json"

    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")

    logger.info("Loading model: %s", model_path)
    model = joblib.load(model_path)

    metrics = {}
    if metrics_path.exists():
        with open(metrics_path, encoding="utf-8") as f:
            metrics = json.load(f)
        logger.info("Model MAE: %s SEK", f"{metrics.get('mae', 'N/A'):,.0f}")
        logger.info("Model RMSE: %s SEK", f"{metrics.get('rmse', 'N/A'):,.0f}")

    return model, metrics


def calculate_value_metrics(
    df: pd.DataFrame,
    undervalue_threshold_pct: float = 5.0,
    undervalue_threshold_abs: float = 200000,
) -> pd.DataFrame:
    """Calculate value metrics for each property.

    Value metrics:
    - prediction_delta_absolute: predicted_price - sold_price
      (positive = over-predicted = potential undervalued property)
    - prediction_delta_percentage: (predicted_price - sold_price) / sold_price * 100
    - is_undervalued: True if delta exceeds threshold (5% OR 200K SEK by default)
    - value_score: Custom score to rank properties (1-100)
      Higher score = better value

    Args:
        df: DataFrame with predictions
        undervalue_threshold_pct: Minimum percentage below prediction to be "undervalued" (default 5%)
        undervalue_threshold_abs: Minimum absolute amount below prediction (default 200K SEK)
    """
    df = df.copy()

    # Calculate deltas
    df["prediction_delta_absolute"] = df["predicted_price"] - df["sold_price"]
    df["prediction_delta_percentage"] = (
        (df["predicted_price"] - df["sold_price"]) / df["sold_price"] * 100
    )

    # Rankability gate. A value score is only trustworthy when the size-derived
    # features the model leans on are real rather than feature-filled. When
    # living_area (and its derived price_per_sqm) is missing, fill lets the model
    # treat a tiny flat as a normal-sized one, inflating predicted price and
    # manufacturing fake "excellent value". Such rows still get a prediction but
    # are held out of the ranking and marked, so they sort below rankable rows.
    present = pd.DataFrame(index=df.index)
    for field in CORE_RANK_FIELDS:
        column = (
            pd.to_numeric(df[field], errors="coerce")
            if field in df.columns
            else pd.Series(np.nan, index=df.index)
        )
        present[field] = column.gt(0)
    is_rankable = present.all(axis=1)
    df["is_rankable"] = is_rankable
    df["missing_core_fields"] = [
        [field for field in CORE_RANK_FIELDS if not row[field]]
        for row in present.to_dict("records")
    ]
    df["rank_suppressed_reason"] = [
        None if ok else f"missing_{missing[0]}"
        for ok, missing in zip(is_rankable, df["missing_core_fields"])
    ]

    # Mark as undervalued only for rankable rows that clear the threshold
    # (EITHER percentage OR absolute).
    df["is_undervalued"] = is_rankable & (
        (df["prediction_delta_percentage"] >= undervalue_threshold_pct)
        | (df["prediction_delta_absolute"] >= undervalue_threshold_abs)
    )

    # Value score (1-100): quantile-normalize undervaluation into a bell curve
    # centered at 50. Rank properties by percentage delta (higher delta = sold
    # further below the model = better value), map the rank through the inverse
    # normal CDF to get a standard-normal spread, then scale. This uses the full
    # 1-100 range — unlike a raw z-score clipped at ±3, which collapses every
    # extreme into a spike at 95. Ranked over rankable rows only, so suppressed
    # rows can neither claim a score nor distort the percentile spread.
    rankable_delta = df.loc[is_rankable, "prediction_delta_percentage"]
    n = len(rankable_delta)
    value_score = pd.Series(np.nan, index=df.index)
    if n > 1:
        # Ranks -> (0, 1) open interval; the +1 denominator keeps the extremes
        # finite, and norm.ppf turns the uniform ranks into a standard normal.
        percentile = rankable_delta.rank(method="average") / (n + 1)
        z_norm = pd.Series(norm.ppf(percentile.to_numpy()), index=rankable_delta.index)
        # z*15 + 50: z=0 -> 50, z=±1 -> 35/65, z=±2 -> 20/80, z=±3.3 -> 1/100.
        value_score.loc[rankable_delta.index] = (z_norm * 15 + 50).clip(1, 100).round(1)
    elif n == 1:
        value_score.loc[rankable_delta.index] = 50.0
    df["value_score"] = value_score

    # Add value tier labels (aligned with z-score distribution)
    def get_value_tier(score: float) -> str:
        if score >= 80:  # z >= +2 (top ~2.5%)
            return "Excellent Value"
        elif score >= 65:  # z >= +1 (top ~16%)
            return "Great Value"
        elif score >= 55:  # z >= +0.33 (top ~37%)
            return "Good Value"
        elif score >= 45:  # z >= -0.33 (around mean)
            return "Fair Value"
        elif score >= 30:  # z >= -1.33 (bottom ~16%)
            return "Overvalued"
        else:  # z < -1.33 (bottom ~9%)
            return "Highly Overvalued"

    df["value_tier"] = [
        get_value_tier(score) if pd.notna(score) else None for score in df["value_score"]
    ]

    return df


def prepare_output_records(df: pd.DataFrame) -> list[dict]:
    """Prepare property records for JSON output."""
    # Select and order columns for output
    output_columns = [
        "listing_id",
        "url",
        "address",
        "area",
        "municipality",
        "living_area",
        "rooms",
        "property_type",
        "construction_year",
        "monthly_fee",
        "floor",
        "elevator",
        "balcony",
        "sold_price",
        "predicted_price",
        "prediction_delta_absolute",
        "prediction_delta_percentage",
        "is_undervalued",
        "value_score",
        "value_tier",
        "is_rankable",
        "rank_suppressed_reason",
        "missing_core_fields",
        "sold_date",
        "days_on_market",
        "listing_price",
        "price_per_sqm",
        "latitude",
        "longitude",
    ]

    # Filter to columns that exist in the dataframe
    available_columns = [col for col in output_columns if col in df.columns]

    df_output = df[available_columns].copy()

    # Convert to records and clean up
    records = df_output.to_dict("records")

    # Clean up NaN values and format numbers
    cleaned_records = []
    for record in records:
        cleaned = {}
        for key, value in record.items():
            if isinstance(value, list):
                cleaned[key] = value
            elif pd.isna(value):
                cleaned[key] = None
            elif isinstance(value, (np.integer, np.int64)):
                cleaned[key] = int(value)
            elif isinstance(value, (np.floating, np.float64)):
                cleaned[key] = round(float(value), 2)
            else:
                cleaned[key] = value
        cleaned_records.append(cleaned)

    return cleaned_records


def generate_summary_statistics(df: pd.DataFrame, metrics: dict) -> dict:
    """Generate summary statistics for the analysis."""
    # Value statistics describe the ranked population only. Rows missing core
    # fields are held out of the ranking (value_score is NaN), so folding them
    # in would skew the distribution and the undervalued rate.
    rankable = df[df["is_rankable"]]
    undervalued = df[df["is_undervalued"]]
    overvalued = rankable[~rankable["is_undervalued"]]
    rankable_n = len(rankable)

    stats = {
        "total_properties": len(df),
        "rankable_count": rankable_n,
        "unrankable_count": len(df) - rankable_n,
        "undervalued_count": len(undervalued),
        "overvalued_count": len(overvalued),
        "undervalued_percentage": round(len(undervalued) / rankable_n * 100, 1)
        if rankable_n
        else 0.0,
        "value_score": {
            "mean": round(float(rankable["value_score"].mean()), 1),
            "median": round(float(rankable["value_score"].median()), 1),
            "min": round(float(rankable["value_score"].min()), 1),
            "max": round(float(rankable["value_score"].max()), 1),
            "std": round(float(rankable["value_score"].std()), 1),
        },
        "prediction_delta_absolute": {
            "mean": round(float(rankable["prediction_delta_absolute"].mean()), 0),
            "median": round(float(rankable["prediction_delta_absolute"].median()), 0),
            "min": round(float(rankable["prediction_delta_absolute"].min()), 0),
            "max": round(float(rankable["prediction_delta_absolute"].max()), 0),
        },
        "prediction_delta_percentage": {
            "mean": round(float(rankable["prediction_delta_percentage"].mean()), 2),
            "median": round(float(rankable["prediction_delta_percentage"].median()), 2),
            "min": round(float(rankable["prediction_delta_percentage"].min()), 2),
            "max": round(float(rankable["prediction_delta_percentage"].max()), 2),
        },
        "value_tier_distribution": rankable["value_tier"].value_counts().to_dict(),
        "area_statistics": {
            "total_areas": int(df["area"].nunique()),
            "top_undervalued_areas": (undervalued["area"].value_counts().head(10).to_dict()),
        },
        "model_performance": {
            "mae": metrics.get("mae"),
            "rmse": metrics.get("rmse"),
            "mape": metrics.get("mape"),
            "n_train": metrics.get("n_train"),
            "n_test": metrics.get("n_test"),
        },
    }

    return stats


def generate_value_analysis(
    data_file: Path,
    model_type: str = "no_list",
    output_file: Path | None = None,
    models_dir: Path | None = None,
    model_prefix: str = "price_prediction_model",
    apply_training_filters: bool = True,
    undervalue_threshold_pct: float = 5.0,
    undervalue_threshold_abs: float = 200000,
    only_undervalued: bool = False,
    min_value_score: float | None = None,
) -> dict:
    """Generate value analysis by running predictions on production data.

    Args:
        data_file: Path to production data JSON file
        model_type: Model type (no_list, listing)
        output_file: Output path for value analysis JSON
        models_dir: Directory containing trained models
        model_prefix: Model file prefix
        apply_training_filters: Apply same filters as training
        undervalue_threshold_pct: Percentage threshold for undervalued
        undervalue_threshold_abs: Absolute SEK threshold for undervalued
        only_undervalued: Only include undervalued properties
        min_value_score: Only include properties with score >= this threshold

    Returns:
        Dict with metadata, statistics, and properties
    """
    if output_file is None:
        output_file = Path("data/derived/value_analysis.json")
    if models_dir is None:
        models_dir = Path("web/models")

    df = load_production_data(data_file, apply_training_filters=apply_training_filters)
    model, metrics = load_model(models_dir, model_type, model_prefix)

    predictions = model.predict(df)
    df["predicted_price"] = predictions

    df = calculate_value_metrics(
        df,
        undervalue_threshold_pct=undervalue_threshold_pct,
        undervalue_threshold_abs=undervalue_threshold_abs,
    )

    if only_undervalued:
        df = df[df["is_undervalued"]].copy()

    if min_value_score:
        df = df[df["value_score"] >= min_value_score].copy()

    stats = generate_summary_statistics(df, metrics)
    properties = prepare_output_records(df)
    # Suppressed rows carry a null value_score; sort them last, not crash.
    properties_sorted = sorted(
        properties,
        key=lambda x: x["value_score"] if x["value_score"] is not None else float("-inf"),
        reverse=True,
    )

    output = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "model_type": model_type,
            "model_path": str(models_dir / f"{model_prefix}_{model_type}.joblib"),
            "data_source": str(data_file),
            "filters": {
                "only_undervalued": only_undervalued,
                "min_value_score": min_value_score,
                "training_filters_applied": apply_training_filters,
            },
            "thresholds": {
                "undervalue_threshold_pct": undervalue_threshold_pct,
                "undervalue_threshold_abs": undervalue_threshold_abs,
            },
        },
        "statistics": stats,
        "properties": properties_sorted,
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    return output
