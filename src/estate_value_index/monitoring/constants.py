"""Constants for ML monitoring and drift detection."""

# Drift thresholds
WASSERSTEIN_THRESHOLD = 0.1  # Data drift threshold for numeric features
CHI_SQUARE_ALPHA = 0.05  # Categorical drift significance level
PERFORMANCE_DEGRADATION_THRESHOLD = 0.10  # 10% MdAPE increase triggers alert

# GCS paths
BASELINE_DATA_PATH = "monitoring/baseline/baseline_data.parquet"
DRIFT_REPORTS_PATH = "monitoring/drift_reports/"
