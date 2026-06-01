#!/usr/bin/env python3
"""
Feature correlation analysis to identify multicollinearity issues.

Analyzes correlations between listing_price and area features to determine
if area-based signals are redundant with the dominant listing_price feature.
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from sklearn.feature_selection import mutual_info_regression
from statsmodels.stats.outliers_influence import variance_inflation_factor

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from estate_value_index.ml.data_loader import load_features_from_bigquery
from estate_value_index.ml.features import create_optimized_features, get_feature_lists


def calculate_vif(df: pd.DataFrame, numeric_features: list) -> pd.DataFrame:
    """Calculate Variance Inflation Factor for numeric features."""
    vif_data = []

    # Only use numeric features that exist in df
    valid_features = [
        f for f in numeric_features if f in df.columns and df[f].dtype in ["float64", "int64"]
    ]

    if len(valid_features) < 2:
        print("Not enough numeric features for VIF calculation")
        return pd.DataFrame()

    X = df[valid_features].fillna(0)

    for i, feature in enumerate(valid_features):
        try:
            vif = variance_inflation_factor(X.values, i)
            vif_data.append({"feature": feature, "VIF": vif})
        except Exception as e:
            print(f"Could not calculate VIF for {feature}: {e}")

    vif_df = pd.DataFrame(vif_data)
    return vif_df.sort_values("VIF", ascending=False)


def analyze_correlations():
    """Analyze feature correlations with focus on listing_price vs area features."""
    print("\n" + "=" * 80)
    print("FEATURE CORRELATION ANALYSIS")
    print("=" * 80)

    # Load pre-engineered features from BigQuery
    print("\nLoading pre-engineered features from BigQuery...")
    try:
        df_eng = load_features_from_bigquery()
        print(f"Loaded {len(df_eng)} samples with engineered features")
    except Exception as e:
        print(f"Error loading from BigQuery: {e}")
        print("Attempting to load from JSON files instead...")
        from estate_value_index.ml.data_loader import load_from_bigquery

        df = load_from_bigquery()
        print(f"Loaded {len(df)} raw samples")
        print("Engineering features...")
        df_eng = create_optimized_features(df)

    # Get feature lists
    numeric_features, categorical_features, all_features = get_feature_lists()

    # Filter to available features
    numeric_features = [f for f in numeric_features if f in df_eng.columns]

    # Identify area-related features
    area_features = [
        f
        for f in numeric_features
        if "area" in f.lower() and f != "living_area" and f != "living_area_squared"
    ]

    # Calculate correlation matrix for key features
    key_features = ["listing_price", "sold_price"] + area_features
    key_features = [f for f in key_features if f in df_eng.columns]

    print(f"\nCalculating correlations for {len(key_features)} features...")
    corr_matrix = df_eng[key_features].corr()

    # Focus on listing_price correlations
    print("\n" + "-" * 80)
    print("CORRELATIONS WITH LISTING_PRICE")
    print("-" * 80)

    listing_corr = corr_matrix["listing_price"].sort_values(ascending=False)
    print(listing_corr.to_string())

    # Identify highly correlated area features
    high_corr_area = listing_corr[
        listing_corr.index.isin(area_features) & (listing_corr.abs() > 0.5)
    ]

    if len(high_corr_area) > 0:
        print(
            f"\nWARNING: {len(high_corr_area)} area features highly correlated (|r| > 0.5) with listing_price:"
        )
        for feat, corr_val in high_corr_area.items():
            print(f"   {feat:40s}  r={corr_val:.3f}")

    # Mutual Information Analysis
    print("\n" + "-" * 80)
    print("MUTUAL INFORMATION (with sold_price target)")
    print("-" * 80)

    if "sold_price" in df_eng.columns:
        # Prepare data
        y = df_eng["sold_price"]
        X_numeric = df_eng[numeric_features].fillna(0)

        # Calculate MI scores
        print("Calculating mutual information scores...")
        mi_scores = mutual_info_regression(X_numeric, y, random_state=42)

        mi_df = pd.DataFrame({"feature": numeric_features, "MI_score": mi_scores}).sort_values(
            "MI_score", ascending=False
        )

        print("\nTop 20 features by Mutual Information:")
        print(mi_df.head(20).to_string(index=False))

        # Compare listing_price vs area features
        listing_mi = mi_df[mi_df["feature"] == "listing_price"]["MI_score"].values
        area_mi = mi_df[mi_df["feature"].isin(area_features)]["MI_score"].values

        if len(listing_mi) > 0 and len(area_mi) > 0:
            print("\nMI comparison:")
            print(f"  listing_price MI:     {listing_mi[0]:.3f}")
            print(f"  Area features avg MI: {area_mi.mean():.3f}")
            print(f"  Ratio:                {listing_mi[0] / (area_mi.mean() + 1e-10):.1f}x")

            if listing_mi[0] > area_mi.mean() * 5:
                print("\nCRITICAL: listing_price has >5x more predictive power than area features!")

    # Variance Inflation Factor (VIF)
    print("\n" + "-" * 80)
    print("VARIANCE INFLATION FACTOR (Multicollinearity Detection)")
    print("-" * 80)

    # Focus on listing_price and area features
    vif_features = ["listing_price"] + area_features[:15]  # Limit to avoid computational issues
    vif_df = calculate_vif(df_eng, vif_features)

    if not vif_df.empty:
        print("\nVIF scores (>10 indicates multicollinearity):")
        print(vif_df.head(20).to_string(index=False))

        high_vif = vif_df[vif_df["VIF"] > 10]
        if len(high_vif) > 0:
            print(f"\nWARNING: {len(high_vif)} features with VIF > 10 (multicollinear):")
            for _, row in high_vif.head(10).iterrows():
                print(f"   {row['feature']:40s}  VIF={row['VIF']:.1f}")

    # Visualizations
    print("\n" + "-" * 80)
    print("GENERATING VISUALIZATIONS")
    print("-" * 80)

    # Create output directory
    output_dir = Path("reports/correlation_analysis")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Correlation heatmap
    plt.figure(figsize=(14, 12))

    # Select subset of features for readable heatmap
    viz_features = ["listing_price", "sold_price"] + area_features[:15]
    viz_features = [f for f in viz_features if f in df_eng.columns]

    corr_viz = df_eng[viz_features].corr()

    sns.heatmap(
        corr_viz,
        annot=True,
        fmt=".2f",
        cmap="RdBu_r",
        center=0,
        square=True,
        linewidths=0.5,
        cbar_kws={"shrink": 0.8},
    )
    plt.title(
        "Feature Correlation Matrix\n(listing_price vs area features)",
        fontsize=14,
        fontweight="bold",
    )
    plt.tight_layout()

    heatmap_path = output_dir / "correlation_heatmap.png"
    plt.savefig(heatmap_path, dpi=150, bbox_inches="tight")
    print(f"Saved correlation heatmap: {heatmap_path}")
    plt.close()

    # 2. Listing price vs area_avg_price scatter
    if "area_avg_price" in df_eng.columns:
        plt.figure(figsize=(10, 6))
        plt.scatter(df_eng["area_avg_price"], df_eng["listing_price"], alpha=0.3, s=10)
        plt.xlabel("Area Average Price (SEK)", fontsize=12)
        plt.ylabel("Listing Price (SEK)", fontsize=12)
        plt.title("Listing Price vs Area Average Price", fontsize=14, fontweight="bold")

        # Add correlation coefficient
        corr_val = df_eng[["area_avg_price", "listing_price"]].corr().iloc[0, 1]
        plt.text(
            0.05,
            0.95,
            f"Correlation: {corr_val:.3f}",
            transform=plt.gca().transAxes,
            fontsize=12,
            bbox={"boxstyle": "round", "facecolor": "wheat", "alpha": 0.5},
        )

        scatter_path = output_dir / "listing_vs_area_price.png"
        plt.savefig(scatter_path, dpi=150, bbox_inches="tight")
        print(f"Saved scatter plot: {scatter_path}")
        plt.close()

    # 3. MI scores bar chart
    plt.figure(figsize=(12, 8))
    top_features = mi_df.head(20)

    colors = [
        "red" if f == "listing_price" else "blue" if f in area_features else "gray"
        for f in top_features["feature"]
    ]

    plt.barh(range(len(top_features)), top_features["MI_score"], color=colors)
    plt.yticks(range(len(top_features)), top_features["feature"])
    plt.xlabel("Mutual Information Score", fontsize=12)
    plt.title(
        "Feature Importance by Mutual Information\n(Red=listing_price, Blue=area features)",
        fontsize=14,
        fontweight="bold",
    )
    plt.gca().invert_yaxis()

    mi_path = output_dir / "mutual_information_scores.png"
    plt.savefig(mi_path, dpi=150, bbox_inches="tight")
    print(f"Saved MI chart: {mi_path}")
    plt.close()

    # Summary report
    print("\n" + "=" * 80)
    print("SUMMARY REPORT")
    print("=" * 80)

    print("\n1. CORRELATION FINDINGS:")
    print(f"   - {len(high_corr_area)} area features highly correlated with listing_price")
    print(
        f"   - Strongest area correlation: {listing_corr[listing_corr.index.isin(area_features)].iloc[0]:.3f}"
    )

    print("\n2. PREDICTIVE POWER:")
    if len(listing_mi) > 0 and len(area_mi) > 0:
        print(f"   - listing_price MI: {listing_mi[0]:.3f}")
        print(f"   - Area features avg MI: {area_mi.mean():.3f}")
        print(
            f"   - Listing price is {listing_mi[0] / (area_mi.mean() + 1e-10):.1f}x more predictive"
        )

    print("\n3. MULTICOLLINEARITY:")
    if not vif_df.empty:
        high_vif_count = len(vif_df[vif_df["VIF"] > 10])
        print(f"   - {high_vif_count} features with VIF > 10")
        if "listing_price" in vif_df["feature"].values:
            listing_vif = vif_df[vif_df["feature"] == "listing_price"]["VIF"].values[0]
            print(f"   - listing_price VIF: {listing_vif:.1f}")

    print("\n4. RECOMMENDATION:")
    if len(listing_mi) > 0 and len(area_mi) > 0 and listing_mi[0] > area_mi.mean() * 3:
        print("   WARNING: listing_price dominates and likely suppresses area features")
        print("   → Consider removing listing_price or creating derived features")
        print("   → Model should predict value from characteristics, not from asking price")
    else:
        print("   Feature redundancy appears manageable")

    print(f"\nAll visualizations saved to: {output_dir}/")

    # Save detailed results
    results = {
        "correlation_with_listing_price": listing_corr.to_dict(),
        "mutual_information": mi_df.to_dict("records"),
        "variance_inflation": vif_df.to_dict("records") if not vif_df.empty else [],
    }

    import json

    results_path = output_dir / "correlation_analysis_results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to: {results_path}")


if __name__ == "__main__":
    analyze_correlations()
