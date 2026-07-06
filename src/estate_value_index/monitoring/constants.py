"""Constants for ML monitoring and drift detection."""

# Drift thresholds
WASSERSTEIN_THRESHOLD = 0.1  # Data drift threshold for numeric features
CHI_SQUARE_ALPHA = 0.05  # Categorical drift significance level
PERFORMANCE_DEGRADATION_THRESHOLD = 0.10  # 10% MdAPE increase triggers alert

# Critical features for drift monitoring (high importance from feature engineering)
CRITICAL_NUMERIC_FEATURES = [
    "listing_price",
    "living_area",
    "price_per_sqm",
    "relative_area_price",
    "area_target_encoded",
    "area_price_median",
    "area_sold_price_median_3m",
]

CRITICAL_CATEGORICAL_FEATURES = [
    "area",
    "swedish_season",
    "area_price_tier",
    "architectural_era",
]

# GCS paths
BASELINE_DATA_PATH = "monitoring/baseline/baseline_data.parquet"
DRIFT_REPORTS_PATH = "monitoring/drift_reports/"
