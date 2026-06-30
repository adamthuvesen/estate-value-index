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

_OUTPUT_DIR = Path("reports/correlation_analysis")


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


def _load_engineered_features() -> pd.DataFrame:
    print("\nLoading pre-engineered features from BigQuery...")
    try:
        df_eng = load_features_from_bigquery()
        print(f"Loaded {len(df_eng)} samples with engineered features")
        return df_eng
    except Exception as e:
        print(f"Error loading from BigQuery: {e}")
        print("Attempting to load from JSON files instead...")
        from estate_value_index.ml.data_loader import load_from_bigquery

        df = load_from_bigquery()
        print(f"Loaded {len(df)} raw samples")
        print("Engineering features...")
        return create_optimized_features(df)


def _feature_sets(df_eng: pd.DataFrame) -> tuple[list[str], list[str], list[str]]:
    numeric_features, _, _ = get_feature_lists()
    numeric_features = [feature for feature in numeric_features if feature in df_eng.columns]
    area_features = _area_feature_names(numeric_features)
    key_features = _key_feature_names(df_eng, area_features)
    return numeric_features, area_features, key_features


def _area_feature_names(numeric_features: list[str]) -> list[str]:
    return [
        feature
        for feature in numeric_features
        if "area" in feature.lower()
        and feature not in {"living_area", "living_area_squared"}
    ]


def _key_feature_names(df_eng: pd.DataFrame, area_features: list[str]) -> list[str]:
    return [
        feature
        for feature in ["listing_price", "sold_price", *area_features]
        if feature in df_eng.columns
    ]


def _listing_correlation_report(
    df_eng: pd.DataFrame, key_features: list[str], area_features: list[str]
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    print(f"\nCalculating correlations for {len(key_features)} features...")
    corr_matrix = df_eng[key_features].corr()

    print("\n" + "-" * 80)
    print("CORRELATIONS WITH LISTING_PRICE")
    print("-" * 80)

    listing_corr = corr_matrix["listing_price"].sort_values(ascending=False)
    print(listing_corr.to_string())

    high_corr_area = _high_corr_area_features(listing_corr, area_features)
    if len(high_corr_area) > 0:
        print(
            f"\nWARNING: {len(high_corr_area)} area features highly correlated (|r| > 0.5) with listing_price:"
        )
        for feat, corr_val in high_corr_area.items():
            print(f"   {feat:40s}  r={corr_val:.3f}")

    return corr_matrix, listing_corr, high_corr_area


def _high_corr_area_features(
    listing_corr: pd.Series,
    area_features: list[str],
    threshold: float = 0.5,
) -> pd.Series:
    return listing_corr[listing_corr.index.isin(area_features) & (listing_corr.abs() > threshold)]


def _mutual_information_report(
    df_eng: pd.DataFrame,
    numeric_features: list[str],
    area_features: list[str],
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    print("\n" + "-" * 80)
    print("MUTUAL INFORMATION (with sold_price target)")
    print("-" * 80)

    if "sold_price" not in df_eng.columns:
        return pd.DataFrame(), pd.Series(dtype=float), pd.Series(dtype=float)

    y = df_eng["sold_price"]
    x_numeric = df_eng[numeric_features].fillna(0)
    print("Calculating mutual information scores...")
    mi_scores = mutual_info_regression(x_numeric, y, random_state=42)
    mi_df = pd.DataFrame({"feature": numeric_features, "MI_score": mi_scores}).sort_values(
        "MI_score", ascending=False
    )

    print("\nTop 20 features by Mutual Information:")
    print(mi_df.head(20).to_string(index=False))

    listing_mi = mi_df[mi_df["feature"] == "listing_price"]["MI_score"]
    area_mi = mi_df[mi_df["feature"].isin(area_features)]["MI_score"]
    _print_mi_comparison(listing_mi, area_mi)
    return mi_df, listing_mi, area_mi


def _print_mi_comparison(listing_mi: pd.Series, area_mi: pd.Series) -> None:
    if len(listing_mi) == 0 or len(area_mi) == 0:
        return

    listing_score = listing_mi.iloc[0]
    area_mean = area_mi.mean()
    print("\nMI comparison:")
    print(f"  listing_price MI:     {listing_score:.3f}")
    print(f"  Area features avg MI: {area_mean:.3f}")
    print(f"  Ratio:                {listing_score / (area_mean + 1e-10):.1f}x")

    if listing_score > area_mean * 5:
        print("\nCRITICAL: listing_price has >5x more predictive power than area features!")


def _vif_report(df_eng: pd.DataFrame, area_features: list[str]) -> pd.DataFrame:
    print("\n" + "-" * 80)
    print("VARIANCE INFLATION FACTOR (Multicollinearity Detection)")
    print("-" * 80)

    vif_features = ["listing_price"] + area_features[:15]
    vif_df = calculate_vif(df_eng, vif_features)
    if vif_df.empty:
        return vif_df

    print("\nVIF scores (>10 indicates multicollinearity):")
    print(vif_df.head(20).to_string(index=False))

    high_vif = vif_df[vif_df["VIF"] > 10]
    if len(high_vif) > 0:
        print(f"\nWARNING: {len(high_vif)} features with VIF > 10 (multicollinear):")
        for _, row in high_vif.head(10).iterrows():
            print(f"   {row['feature']:40s}  VIF={row['VIF']:.1f}")

    return vif_df


def _plot_correlation_heatmap(
    df_eng: pd.DataFrame,
    area_features: list[str],
    output_dir: Path,
) -> None:
    plt.figure(figsize=(14, 12))
    viz_features = _key_feature_names(df_eng, area_features[:15])
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


def _plot_listing_vs_area_price(df_eng: pd.DataFrame, output_dir: Path) -> None:
    if "area_avg_price" not in df_eng.columns:
        return

    plt.figure(figsize=(10, 6))
    plt.scatter(df_eng["area_avg_price"], df_eng["listing_price"], alpha=0.3, s=10)
    plt.xlabel("Area Average Price (SEK)", fontsize=12)
    plt.ylabel("Listing Price (SEK)", fontsize=12)
    plt.title("Listing Price vs Area Average Price", fontsize=14, fontweight="bold")

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


def _plot_mi_scores(mi_df: pd.DataFrame, area_features: list[str], output_dir: Path) -> None:
    if mi_df.empty:
        return

    plt.figure(figsize=(12, 8))
    top_features = mi_df.head(20)
    colors = [
        "red" if feature == "listing_price" else "blue" if feature in area_features else "gray"
        for feature in top_features["feature"]
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


def _generate_visualizations(
    df_eng: pd.DataFrame,
    area_features: list[str],
    mi_df: pd.DataFrame,
    output_dir: Path,
) -> None:
    print("\n" + "-" * 80)
    print("GENERATING VISUALIZATIONS")
    print("-" * 80)
    output_dir.mkdir(parents=True, exist_ok=True)
    _plot_correlation_heatmap(df_eng, area_features, output_dir)
    _plot_listing_vs_area_price(df_eng, output_dir)
    _plot_mi_scores(mi_df, area_features, output_dir)


def _print_summary_report(
    *,
    high_corr_area: pd.Series,
    listing_corr: pd.Series,
    area_features: list[str],
    listing_mi: pd.Series,
    area_mi: pd.Series,
    vif_df: pd.DataFrame,
    output_dir: Path,
) -> None:
    print("\n" + "=" * 80)
    print("SUMMARY REPORT")
    print("=" * 80)

    print("\n1. CORRELATION FINDINGS:")
    print(f"   - {len(high_corr_area)} area features highly correlated with listing_price")
    area_listing_corr = listing_corr[listing_corr.index.isin(area_features)]
    if not area_listing_corr.empty:
        print(f"   - Strongest area correlation: {area_listing_corr.iloc[0]:.3f}")

    print("\n2. PREDICTIVE POWER:")
    if len(listing_mi) > 0 and len(area_mi) > 0:
        listing_score = listing_mi.iloc[0]
        area_mean = area_mi.mean()
        print(f"   - listing_price MI: {listing_score:.3f}")
        print(f"   - Area features avg MI: {area_mean:.3f}")
        print(f"   - Listing price is {listing_score / (area_mean + 1e-10):.1f}x more predictive")

    print("\n3. MULTICOLLINEARITY:")
    if not vif_df.empty:
        high_vif_count = len(vif_df[vif_df["VIF"] > 10])
        print(f"   - {high_vif_count} features with VIF > 10")
        if "listing_price" in vif_df["feature"].values:
            listing_vif = vif_df[vif_df["feature"] == "listing_price"]["VIF"].values[0]
            print(f"   - listing_price VIF: {listing_vif:.1f}")

    print("\n4. RECOMMENDATION:")
    if _listing_price_dominates_area_features(listing_mi, area_mi):
        print("   WARNING: listing_price dominates and likely suppresses area features")
        print("   → Consider removing listing_price or creating derived features")
        print("   → Model should predict value from characteristics, not from asking price")
    else:
        print("   Feature redundancy appears manageable")

    print(f"\nAll visualizations saved to: {output_dir}/")


def _listing_price_dominates_area_features(
    listing_mi: pd.Series,
    area_mi: pd.Series,
    ratio: float = 3.0,
) -> bool:
    return len(listing_mi) > 0 and len(area_mi) > 0 and listing_mi.iloc[0] > area_mi.mean() * ratio


def _save_results(
    output_dir: Path,
    listing_corr: pd.Series,
    mi_df: pd.DataFrame,
    vif_df: pd.DataFrame,
) -> None:
    import json

    results = {
        "correlation_with_listing_price": listing_corr.to_dict(),
        "mutual_information": mi_df.to_dict("records"),
        "variance_inflation": vif_df.to_dict("records") if not vif_df.empty else [],
    }

    results_path = output_dir / "correlation_analysis_results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to: {results_path}")


def analyze_correlations():
    """Analyze feature correlations with focus on listing_price vs area features."""
    print("\n" + "=" * 80)
    print("FEATURE CORRELATION ANALYSIS")
    print("=" * 80)

    df_eng = _load_engineered_features()
    numeric_features, area_features, key_features = _feature_sets(df_eng)
    _, listing_corr, high_corr_area = _listing_correlation_report(
        df_eng, key_features, area_features
    )
    mi_df, listing_mi, area_mi = _mutual_information_report(
        df_eng, numeric_features, area_features
    )
    vif_df = _vif_report(df_eng, area_features)
    _generate_visualizations(df_eng, area_features, mi_df, _OUTPUT_DIR)
    _print_summary_report(
        high_corr_area=high_corr_area,
        listing_corr=listing_corr,
        area_features=area_features,
        listing_mi=listing_mi,
        area_mi=area_mi,
        vif_df=vif_df,
        output_dir=_OUTPUT_DIR,
    )
    _save_results(_OUTPUT_DIR, listing_corr, mi_df, vif_df)


if __name__ == "__main__":
    analyze_correlations()
