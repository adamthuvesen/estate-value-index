"""Pipeline constants and defaults."""

from estate_value_index.model_artifacts import (
    DEFAULT_MODEL_PREFIX as MODEL_ARTIFACT_DEFAULT_MODEL_PREFIX,
)

# GCP/Cloud Run defaults
DEFAULT_REGION = "europe-north1"
DEFAULT_MACHINE_TYPE = "n1-standard-4"

# Model defaults
DEFAULT_MODEL_DIR = "web/models"
DEFAULT_MODEL_PREFIX = MODEL_ARTIFACT_DEFAULT_MODEL_PREFIX
# Single production quality bar, as MdAPE (median absolute % error) — the
# AVM-standard headline metric, scale-robust unlike an absolute-SEK MAE gate.
# .github/workflows/ml-pipeline.yml repeats this number inline (it cannot import
# Python), guarded by a test in tests/unit/pipelines/test_training_pipeline.py.
DEFAULT_MEDIAN_APE_THRESHOLD = 0.08

# Polling defaults
DEFAULT_POLL_INTERVAL = 30
