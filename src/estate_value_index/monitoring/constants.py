"""Constants for ML monitoring and drift detection."""

PERFORMANCE_DEGRADATION_THRESHOLD = 0.10  # 10% MdAPE increase triggers alert

# GCS paths
BASELINE_DATA_PATH = "monitoring/baseline/baseline_data.parquet"
