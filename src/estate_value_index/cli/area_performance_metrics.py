#!/usr/bin/env python3
"""
Area-stratified performance analysis.

Analyzes model accuracy across different areas and price tiers to identify
systematic biases in predictions (e.g., underperforming in premium areas).
"""

import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, r2_score

from estate_value_index.ml.data_loader import load_features_from_bigquery

# Threshold (in SEK) above which the predicted median is treated as already
# being in linear price space. ~100K cleanly separates raw log targets
# (median ~15) from any plausible Stockholm sale price.
_LINEAR_SPACE_MEDIAN_THRESHOLD = 100_000.0


def _maybe_inverse_log(y_pred_log: np.ndarray) -> np.ndarray:
    """Return predictions in linear price space.

    If the model already emits linear-space predictions (median above the
    SEK threshold), pass them through unchanged and emit a stderr note.
    Otherwise apply ``np.expm1`` to invert the log target transform.
    """
    pred_median = float(np.nanmedian(y_pred_log))
    if pred_median > _LINEAR_SPACE_MEDIAN_THRESHOLD:
        print(
            "[area-metrics] predictions already in linear space; skipping expm1",
            file=sys.stderr,
        )
        return np.asarray(y_pred_log)
    return np.expm1(y_pred_log)


def analyze_area_performance():
    """Analyze model performance stratified by area."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    print("\n" + "=" * 80)
    print("AREA-STRATIFIED PERFORMANCE ANALYSIS")
    print("=" * 80)

    # Load model pipeline
    model_path = Path("web/models/price_prediction_model_lgbm.joblib")
    print(f"\nLoading model from {model_path}...")
    model_pipeline = joblib.load(model_path)

    # Extract the LightGBM model
    lgbm_model = model_pipeline.model

    # Load pre-engineered features from BigQuery
    print("Loading engineered features from BigQuery...")
    df = load_features_from_bigquery()
    print(f"Loaded {len(df)} samples")

    # Ensure we have target and area
    if "sold_price" not in df.columns or "area" not in df.columns:
        print("Missing sold_price or area column. Cannot perform analysis.")
        return

    # Get feature lists from pipeline
    numeric_features = model_pipeline.numeric_features
    categorical_features = model_pipeline.categorical_features
    all_features = numeric_features + categorical_features

    # Prepare features
    X = df[all_features].copy()

    # Fill missing values using model's context
    for col in numeric_features:
        if col in X.columns:
            fill_value = model_pipeline.context.numeric_fill_values.get(col)
            if fill_value is None or pd.isna(fill_value):
                X[col] = X[col].fillna(0)
            else:
                X[col] = X[col].fillna(float(fill_value))

    for col in categorical_features:
        if col in X.columns:
            mode_val = model_pipeline.context.categorical_fill_values.get(col, "unknown")
            if mode_val is None:
                mode_val = "unknown"
            X[col] = X[col].fillna(mode_val).astype("category")

    # Make predictions directly with LightGBM (output is in log space)
    print("Generating predictions...")
    y_true = df["sold_price"].values
    y_pred_log = lgbm_model.predict(X)

    # Transform back from log space (skips expm1 if predictions are already linear)
    y_pred = _maybe_inverse_log(y_pred_log)

    df["prediction"] = y_pred
    df["error"] = y_pred - y_true
    df["abs_error"] = np.abs(df["error"])
    df["pct_error"] = (df["error"] / y_true) * 100

    # Overall metrics
    mae = mean_absolute_error(y_true, y_pred)
    mape = mean_absolute_percentage_error(y_true, y_pred) * 100
    r2 = r2_score(y_true, y_pred)

    print("\n" + "-" * 80)
    print("OVERALL PERFORMANCE")
    print("-" * 80)
    print(f"MAE:   {mae:,.0f} SEK")
    print(f"MAPE:  {mape:.1f}%")
    print(f"R²:    {r2:.3f}")

    # Performance by area
    print("\n" + "-" * 80)
    print("PERFORMANCE BY AREA")
    print("-" * 80)

    area_metrics = (
        df.groupby("area")
        .agg(
            {
                "sold_price": ["count", "mean"],
                "abs_error": "mean",
                "pct_error": lambda x: np.abs(x).mean(),
                "prediction": "mean",
            }
        )
        .round(0)
    )

    area_metrics.columns = ["count", "avg_price", "mae", "mape", "avg_prediction"]
    area_metrics = area_metrics.sort_values("avg_price", ascending=False)

    print("\nTop 20 areas by average price:")
    print(area_metrics.head(20).to_string())

    # Performance by price tier
    print("\n" + "-" * 80)
    print("PERFORMANCE BY AREA PRICE TIER")
    print("-" * 80)

    if "area_price_tier" in df.columns:
        tier_metrics = (
            df.groupby("area_price_tier")
            .agg(
                {
                    "sold_price": ["count", "mean"],
                    "abs_error": "mean",
                    "pct_error": lambda x: np.abs(x).mean(),
                }
            )
            .round(0)
        )

        tier_metrics.columns = ["count", "avg_price", "mae", "mape"]
        tier_metrics = tier_metrics.sort_values("avg_price", ascending=False)

        print(tier_metrics.to_string())

        # Check if premium areas underperform
        if "premium" in tier_metrics.index:
            premium_mae = tier_metrics.loc["premium", "mae"]
            overall_mae_val = mae

            print(f"\nPremium areas MAE: {premium_mae:,.0f} SEK")
            print(f"Overall MAE:       {overall_mae_val:,.0f} SEK")

            if premium_mae > overall_mae_val * 1.2:
                print("Premium areas have 20%+ higher error than overall!")

    # Prediction bias by area
    print("\n" + "-" * 80)
    print("PREDICTION BIAS (over/under prediction)")
    print("-" * 80)

    bias_metrics = df.groupby("area").agg({"error": "mean", "sold_price": "count"}).round(0)
    bias_metrics.columns = ["mean_error", "count"]
    bias_metrics = bias_metrics[bias_metrics["count"] >= 10]  # Only areas with 10+ samples

    # Identify areas with systematic bias
    over_predicted = bias_metrics[bias_metrics["mean_error"] > 100000].sort_values(
        "mean_error", ascending=False
    )
    under_predicted = bias_metrics[bias_metrics["mean_error"] < -100000].sort_values("mean_error")

    if len(over_predicted) > 0:
        print("\nAreas with systematic OVER-prediction (>100K SEK):")
        for area, row in over_predicted.head(10).iterrows():
            print(f"  {area:30s}  +{row['mean_error']:>10,.0f} SEK  (n={row['count']:.0f})")

    if len(under_predicted) > 0:
        print("\nAreas with systematic UNDER-prediction (<-100K SEK):")
        for area, row in under_predicted.head(10).iterrows():
            print(f"  {area:30s}  {row['mean_error']:>10,.0f} SEK  (n={row['count']:.0f})")

    # Visualizations
    print("\n" + "-" * 80)
    print("GENERATING VISUALIZATIONS")
    print("-" * 80)

    output_dir = Path("reports/area_performance")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. MAE by area (top 20)
    plt.figure(figsize=(12, 8))
    top_areas = area_metrics.head(20)

    colors = [
        "red" if tier == "premium" else "orange" if tier == "upper" else "blue"
        for tier in df[df["area"].isin(top_areas.index)].groupby("area")["area_price_tier"].first()
    ]

    plt.barh(range(len(top_areas)), top_areas["mae"], color=colors)
    plt.yticks(range(len(top_areas)), top_areas.index)
    plt.xlabel("Mean Absolute Error (SEK)", fontsize=12)
    plt.title(
        "MAE by Area (Top 20 by Avg Price)\nRed=Premium, Orange=Upper, Blue=Medium/Other",
        fontsize=14,
        fontweight="bold",
    )
    plt.axvline(mae, color="black", linestyle="--", label=f"Overall MAE: {mae:,.0f}")
    plt.legend()
    plt.gca().invert_yaxis()
    plt.tight_layout()

    mae_path = output_dir / "mae_by_area.png"
    plt.savefig(mae_path, dpi=150, bbox_inches="tight")
    print(f"Saved MAE by area plot: {mae_path}")
    plt.close()

    # 2. Error distribution by price tier
    if "area_price_tier" in df.columns:
        plt.figure(figsize=(12, 6))

        tier_order = ["premium", "upper", "medium", "affordable"]
        available_tiers = [t for t in tier_order if t in df["area_price_tier"].unique()]

        df_filtered = df[df["area_price_tier"].isin(available_tiers)]

        sns.boxplot(
            data=df_filtered,
            x="area_price_tier",
            y="abs_error",
            order=available_tiers,
            palette="Set2",
        )
        plt.xlabel("Area Price Tier", fontsize=12)
        plt.ylabel("Absolute Error (SEK)", fontsize=12)
        plt.title("Error Distribution by Area Price Tier", fontsize=14, fontweight="bold")
        plt.xticks(rotation=45)
        plt.tight_layout()

        box_path = output_dir / "error_distribution_by_tier.png"
        plt.savefig(box_path, dpi=150, bbox_inches="tight")
        print(f"Saved error distribution plot: {box_path}")
        plt.close()

    # 3. Prediction bias scatter
    plt.figure(figsize=(10, 10))

    # Sample for visualization
    sample_size = min(2000, len(df))
    df_sample = df.sample(n=sample_size, random_state=42)

    plt.scatter(df_sample["sold_price"], df_sample["prediction"], alpha=0.3, s=10)
    plt.plot(
        [df["sold_price"].min(), df["sold_price"].max()],
        [df["sold_price"].min(), df["sold_price"].max()],
        "r--",
        label="Perfect prediction",
    )
    plt.xlabel("Actual Sold Price (SEK)", fontsize=12)
    plt.ylabel("Predicted Price (SEK)", fontsize=12)
    plt.title("Predicted vs Actual Price", fontsize=14, fontweight="bold")
    plt.legend()
    plt.tight_layout()

    scatter_path = output_dir / "predicted_vs_actual.png"
    plt.savefig(scatter_path, dpi=150, bbox_inches="tight")
    print(f"Saved prediction scatter plot: {scatter_path}")
    plt.close()

    # 4. Premium vs non-premium comparison
    if "area_price_tier" in df.columns:
        df["is_premium"] = df["area_price_tier"].isin(["premium", "ultra_premium"])

        print("\n" + "-" * 80)
        print("PREMIUM vs NON-PREMIUM COMPARISON")
        print("-" * 80)

        for is_prem, label in [(True, "Premium"), (False, "Non-Premium")]:
            subset = df[df["is_premium"] == is_prem]
            if len(subset) > 0:
                mae_sub = subset["abs_error"].mean()
                mape_sub = subset["pct_error"].abs().mean()
                count_sub = len(subset)

                print(f"\n{label} areas:")
                print(f"  Count:  {count_sub}")
                print(f"  MAE:    {mae_sub:,.0f} SEK")
                print(f"  MAPE:   {mape_sub:.1f}%")

    # Save detailed results
    area_metrics.to_csv(output_dir / "area_metrics.csv")
    bias_metrics.to_csv(output_dir / "area_bias.csv")

    print(f"\nResults saved to: {output_dir}/")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    print("\n1. OVERALL PERFORMANCE:")
    print(f"   MAE: {mae:,.0f} SEK | MAPE: {mape:.1f}% | R²: {r2:.3f}")

    if "area_price_tier" in df.columns and "premium" in tier_metrics.index:
        premium_mae_val = tier_metrics.loc["premium", "mae"]
        premium_count = tier_metrics.loc["premium", "count"]
        print(f"\n2. PREMIUM AREAS (n={premium_count:.0f}):")
        print(f"   MAE: {premium_mae_val:,.0f} SEK")

        if premium_mae_val > mae * 1.1:
            print(f"   {((premium_mae_val / mae - 1) * 100):.0f}% higher error than overall!")

    if len(over_predicted) > 0 or len(under_predicted) > 0:
        print("\n3. SYSTEMATIC BIAS:")
        if len(over_predicted) > 0:
            print(f"   {len(over_predicted)} areas over-predicted by >100K SEK")
        if len(under_predicted) > 0:
            print(f"   {len(under_predicted)} areas under-predicted by >100K SEK")

    print("\n4. KEY FINDING:")
    print("   If model shows similar MAE across all areas despite listing_price dominance,")
    print("   it suggests the model memorizes area-adjusted listing prices rather than")
    print("   learning true location value.")


def main(argv: list[str] | None = None, *, args=None) -> int:
    analyze_area_performance()
    return 0


if __name__ == "__main__":
    main()
