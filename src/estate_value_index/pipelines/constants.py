"""Pipeline constants and defaults."""

# GCP/Cloud Run defaults
DEFAULT_REGION = "europe-north1"
DEFAULT_MACHINE_TYPE = "n1-standard-4"

# Model defaults
DEFAULT_MODEL_PREFIX = "price_prediction_model"
DEFAULT_MODEL_DIR = "web/models"
# Single production quality bar; .github/workflows/ml-pipeline.yml repeats this
# number inline (it cannot import Python), guarded by a test in
# tests/unit/pipelines/test_training_pipeline.py.
DEFAULT_MAE_THRESHOLD = 350_000

# Polling defaults
DEFAULT_POLL_INTERVAL = 30
