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
_BIAS_THRESHOLD_SEK = 100_000
_MIN_BIAS_SAMPLE_COUNT = 10
_OUTPUT_DIR = Path("reports/area_performance")


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


def _prepare_feature_matrix(df: pd.DataFrame, model_pipeline) -> pd.DataFrame:
    """Select and fill the feature matrix using the model pipeline context."""
    numeric_features = model_pipeline.numeric_features
    categorical_features = model_pipeline.categorical_features
    feature_matrix = df[numeric_features + categorical_features].copy()

    _fill_numeric_features(feature_matrix, numeric_features, model_pipeline.context)
    _fill_categorical_features(feature_matrix, categorical_features, model_pipeline.context)
    return feature_matrix


def _fill_numeric_features(
    feature_matrix: pd.DataFrame,
    numeric_features: list[str],
    context,
) -> None:
    for col in numeric_features:
        if col not in feature_matrix.columns:
            continue

        fill_value = context.numeric_fill_values.get(col)
        if fill_value is None or pd.isna(fill_value):
            feature_matrix[col] = feature_matrix[col].fillna(0)
        else:
            feature_matrix[col] = feature_matrix[col].fillna(float(fill_value))


def _fill_categorical_features(
    feature_matrix: pd.DataFrame,
    categorical_features: list[str],
    context,
) -> None:
    for col in categorical_features:
        if col not in feature_matrix.columns:
            continue

        mode_val = context.categorical_fill_values.get(col, "unknown")
        if mode_val is None:
            mode_val = "unknown"
        feature_matrix[col] = feature_matrix[col].fillna(mode_val).astype("category")


def _add_prediction_columns(
    df: pd.DataFrame,
    model_pipeline,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Return a copy of df with prediction/error columns and overall metrics."""
    feature_matrix = _prepare_feature_matrix(df, model_pipeline)
    y_true = df["sold_price"].values
    y_pred = _maybe_inverse_log(model_pipeline.model.predict(feature_matrix))

    result = df.copy()
    result["prediction"] = y_pred
    result["error"] = y_pred - y_true
    result["abs_error"] = np.abs(result["error"])
    result["pct_error"] = (result["error"] / y_true) * 100

    return result, {
        "mae": mean_absolute_error(y_true, y_pred),
        "mape": mean_absolute_percentage_error(y_true, y_pred) * 100,
        "r2": r2_score(y_true, y_pred),
    }


def _area_metrics(df: pd.DataFrame) -> pd.DataFrame:
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
    return area_metrics.sort_values("avg_price", ascending=False)


def _tier_metrics(df: pd.DataFrame) -> pd.DataFrame | None:
    if "area_price_tier" not in df.columns:
        return None

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
    return tier_metrics.sort_values("avg_price", ascending=False)


def _bias_metrics(
    df: pd.DataFrame,
    *,
    min_count: int = _MIN_BIAS_SAMPLE_COUNT,
    threshold: int = _BIAS_THRESHOLD_SEK,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    bias_metrics = df.groupby("area").agg({"error": "mean", "sold_price": "count"}).round(0)
    bias_metrics.columns = ["mean_error", "count"]
    bias_metrics = bias_metrics[bias_metrics["count"] >= min_count]
    over_predicted = bias_metrics[bias_metrics["mean_error"] > threshold].sort_values(
        "mean_error", ascending=False
    )
    under_predicted = bias_metrics[bias_metrics["mean_error"] < -threshold].sort_values(
        "mean_error"
    )
    return bias_metrics, over_predicted, under_predicted


def _print_section(title: str, char: str = "-") -> None:
    print("\n" + char * 80)
    print(title)
    print(char * 80)


def _print_overall_metrics(metrics: dict[str, float]) -> None:
    _print_section("OVERALL PERFORMANCE")
    print(f"MAE:   {metrics['mae']:,.0f} SEK")
    print(f"MAPE:  {metrics['mape']:.1f}%")
    print(f"R²:    {metrics['r2']:.3f}")


def _print_area_metrics(area_metrics: pd.DataFrame) -> None:
    _print_section("PERFORMANCE BY AREA")
    print("\nTop 20 areas by average price:")
    print(area_metrics.head(20).to_string())


def _print_tier_metrics(tier_metrics: pd.DataFrame | None, overall_mae: float) -> None:
    _print_section("PERFORMANCE BY AREA PRICE TIER")
    if tier_metrics is None:
        return

    print(tier_metrics.to_string())
    if "premium" not in tier_metrics.index:
        return

    premium_mae = tier_metrics.loc["premium", "mae"]
    print(f"\nPremium areas MAE: {premium_mae:,.0f} SEK")
    print(f"Overall MAE:       {overall_mae:,.0f} SEK")

    if premium_mae > overall_mae * 1.2:
        print("Premium areas have 20%+ higher error than overall!")


def _print_bias_metrics(over_predicted: pd.DataFrame, under_predicted: pd.DataFrame) -> None:
    _print_section("PREDICTION BIAS (over/under prediction)")

    if len(over_predicted) > 0:
        print("\nAreas with systematic OVER-prediction (>100K SEK):")
        for area, row in over_predicted.head(10).iterrows():
            print(f"  {area:30s}  +{row['mean_error']:>10,.0f} SEK  (n={row['count']:.0f})")

    if len(under_predicted) > 0:
        print("\nAreas with systematic UNDER-prediction (<-100K SEK):")
        for area, row in under_predicted.head(10).iterrows():
            print(f"  {area:30s}  {row['mean_error']:>10,.0f} SEK  (n={row['count']:.0f})")


def _plot_area_mae(plt, df: pd.DataFrame, area_metrics: pd.DataFrame, mae: float, output_dir: Path):
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


def _plot_tier_errors(plt, sns, df: pd.DataFrame, output_dir: Path) -> None:
    if "area_price_tier" not in df.columns:
        return

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


def _plot_prediction_scatter(plt, df: pd.DataFrame, output_dir: Path) -> None:
    plt.figure(figsize=(10, 10))
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


def _print_premium_comparison(df: pd.DataFrame) -> None:
    if "area_price_tier" not in df.columns:
        return

    df["is_premium"] = df["area_price_tier"].isin(["premium", "ultra_premium"])
    _print_section("PREMIUM vs NON-PREMIUM COMPARISON")

    for is_prem, label in [(True, "Premium"), (False, "Non-Premium")]:
        subset = df[df["is_premium"] == is_prem]
        if len(subset) == 0:
            continue

        print(f"\n{label} areas:")
        print(f"  Count:  {len(subset)}")
        print(f"  MAE:    {subset['abs_error'].mean():,.0f} SEK")
        print(f"  MAPE:   {subset['pct_error'].abs().mean():.1f}%")


def _generate_visualizations(
    df: pd.DataFrame,
    area_metrics: pd.DataFrame,
    metrics: dict[str, float],
    output_dir: Path = _OUTPUT_DIR,
) -> None:
    import matplotlib.pyplot as plt
    import seaborn as sns

    _print_section("GENERATING VISUALIZATIONS")
    output_dir.mkdir(parents=True, exist_ok=True)
    _plot_area_mae(plt, df, area_metrics, metrics["mae"], output_dir)
    _plot_tier_errors(plt, sns, df, output_dir)
    _plot_prediction_scatter(plt, df, output_dir)


def _save_results(area_metrics: pd.DataFrame, bias_metrics: pd.DataFrame, output_dir: Path) -> None:
    area_metrics.to_csv(output_dir / "area_metrics.csv")
    bias_metrics.to_csv(output_dir / "area_bias.csv")
    print(f"\nResults saved to: {output_dir}/")


def _print_summary(
    metrics: dict[str, float],
    tier_metrics: pd.DataFrame | None,
    over_predicted: pd.DataFrame,
    under_predicted: pd.DataFrame,
) -> None:
    _print_section("SUMMARY", char="=")
    print("\n1. OVERALL PERFORMANCE:")
    print(
        f"   MAE: {metrics['mae']:,.0f} SEK | MAPE: {metrics['mape']:.1f}% | R²: {metrics['r2']:.3f}"
    )

    if tier_metrics is not None and "premium" in tier_metrics.index:
        premium_mae_val = tier_metrics.loc["premium", "mae"]
        premium_count = tier_metrics.loc["premium", "count"]
        print(f"\n2. PREMIUM AREAS (n={premium_count:.0f}):")
        print(f"   MAE: {premium_mae_val:,.0f} SEK")
        if premium_mae_val > metrics["mae"] * 1.1:
            print(
                f"   {((premium_mae_val / metrics['mae'] - 1) * 100):.0f}% higher error than overall!"
            )

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


def analyze_area_performance():
    """Analyze model performance stratified by area."""
    _print_section("AREA-STRATIFIED PERFORMANCE ANALYSIS", char="=")

    model_path = Path("web/models/price_prediction_model_no_list.joblib")
    print(f"\nLoading model from {model_path}...")
    model_pipeline = joblib.load(model_path)

    print("Loading engineered features from BigQuery...")
    df = load_features_from_bigquery()
    print(f"Loaded {len(df)} samples")

    if "sold_price" not in df.columns or "area" not in df.columns:
        print("Missing sold_price or area column. Cannot perform analysis.")
        return

    print("Generating predictions...")
    df, metrics = _add_prediction_columns(df, model_pipeline)
    area_metrics = _area_metrics(df)
    tier_metrics = _tier_metrics(df)
    bias_metrics, over_predicted, under_predicted = _bias_metrics(df)

    _print_overall_metrics(metrics)
    _print_area_metrics(area_metrics)
    _print_tier_metrics(tier_metrics, metrics["mae"])
    _print_bias_metrics(over_predicted, under_predicted)
    _generate_visualizations(df, area_metrics, metrics)
    _print_premium_comparison(df)
    _save_results(area_metrics, bias_metrics, _OUTPUT_DIR)
    _print_summary(metrics, tier_metrics, over_predicted, under_predicted)


def main(argv: list[str] | None = None, *, args=None) -> int:
    analyze_area_performance()
    return 0


if __name__ == "__main__":
    main()
