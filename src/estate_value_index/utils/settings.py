"""Central configuration layer: env vars (with optional .env) and YAML overrides.

This module is the single source for raw environment and YAML-backed settings —
the ``EnvConfig`` dataclass, ``load_env_config()``, and the ``get_*``/``is_*``
accessors. Higher-level, pipeline-shaped config objects (``BigQueryConfig``,
``TrainingFlowConfig``) live in :mod:`estate_value_index.pipelines.utils.config`
and are built on top of this layer.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


@dataclass(frozen=True)
class EnvConfig:
    """Environment-specific configuration."""

    gcp_project_id: str
    bigquery_project_id: str
    bq_dataset_raw: str
    bq_table_listings: str
    bq_dataset_features: str
    bq_table_features: str
    # Optional at load time: only required when GCS is actually used. Enforced
    # then by ``utils.gcs.get_gcs_bucket`` rather than failing every non-GCS path.
    gcs_bucket: str | None


def load_env_config() -> EnvConfig:
    """Load environment configuration."""
    return EnvConfig(
        gcp_project_id=os.environ["GCP_PROJECT_ID"],
        bigquery_project_id=os.getenv("BIGQUERY_PROJECT_ID", os.environ["GCP_PROJECT_ID"]),
        bq_dataset_raw=os.getenv("BIGQUERY_DATASET_RAW", "booli_raw"),
        bq_table_listings=os.getenv("BIGQUERY_TABLE_LISTINGS", "listings"),
        bq_dataset_features=os.getenv("BIGQUERY_DATASET_FEATURES", "booli_features"),
        bq_table_features=os.getenv("BIGQUERY_TABLE_FEATURES", "engineered_features"),
        gcs_bucket=os.getenv("GCS_BUCKET"),
    )


_TRUTHY = ("true", "1", "yes", "on")


def load_yaml_config(path: str | None = None) -> dict[str, Any]:
    """Load YAML config file (returns ``{}`` if missing)."""
    path = path or os.getenv("EVI_CONFIG_FILE", "config/pipeline_config.yaml")
    config_path = Path(path)
    if not config_path.exists():
        return {}
    with open(config_path) as f:
        return yaml.safe_load(f) or {}


def bq_table(project: str, dataset: str, table: str) -> str:
    return f"{project}.{dataset}.{table}"


def get_training_config() -> dict[str, Any]:
    return load_yaml_config().get("training", {})


def get_bigquery_config() -> dict[str, Any]:
    return load_yaml_config().get("bigquery", {})


def get_scraping_config() -> dict[str, Any]:
    return load_yaml_config().get("scraping", {})


# env → YAML → default
def get_mae_threshold() -> int:
    env_threshold = os.getenv("MAX_MAE_THRESHOLD")
    if env_threshold:
        return int(env_threshold)
    return get_training_config().get("mae_threshold", 260000)


def get_random_state() -> int:
    return get_training_config().get("random_state", 42)


def get_cv_folds() -> int:
    return get_training_config().get("cv_folds", 5)


def get_test_size() -> float:
    return get_training_config().get("test_size", 0.2)


def get_batch_size() -> int:
    env_batch = os.getenv("BIGQUERY_BATCH_SIZE")
    if env_batch:
        return int(env_batch)
    return get_bigquery_config().get("batch_size", 1000)


def get_max_pages() -> int:
    env_pages = os.getenv("SCRAPER_MAX_PAGES")
    if env_pages:
        return int(env_pages)
    return get_scraping_config().get("default_max_pages", 10)


def is_debug() -> bool:
    return os.getenv("DEBUG", "false").lower() in _TRUTHY


def is_dry_run() -> bool:
    return os.getenv("DRY_RUN", "false").lower() in _TRUTHY


def is_verbose_logging() -> bool:
    return os.getenv("VERBOSE_LOGGING", "true").lower() in _TRUTHY


def is_gcs_enabled() -> bool:
    return os.getenv("GCS_ENABLED", "false").lower() in _TRUTHY


def is_trust_proxy_headers() -> bool:
    """Whether to trust ``X-Forwarded-For`` (only behind a known reverse proxy)."""
    return os.getenv("TRUST_PROXY_HEADERS", "false").lower() in _TRUTHY


def get_rate_limit_max_ips() -> int:
    return int(os.getenv("RATE_LIMIT_MAX_IPS", "10000"))


def get_rate_limit_requests() -> int:
    return int(os.getenv("RATE_LIMIT_REQUESTS", "100"))


def get_rate_limit_window_seconds() -> int:
    return int(os.getenv("RATE_LIMIT_WINDOW", "60"))


def get_web_concurrency() -> int:
    """FastAPI worker count from ``WEB_CONCURRENCY``; falls back to 1 on bad input."""
    raw = os.getenv("WEB_CONCURRENCY", "1")
    try:
        return int(raw)
    except ValueError:
        return 1


def get_data_source() -> str:
    return os.getenv("DATA_SOURCE", "bigquery")


def get_model_prefix() -> str:
    return os.getenv("MODEL_PREFIX", "price_prediction_model")


def get_model_output_dir() -> Path:
    return Path(os.getenv("MODEL_OUTPUT_DIR", "web/models"))


def get_cloud_run_service_name() -> str:
    return os.getenv("CLOUD_RUN_SERVICE_NAME", "estate-value-index-app")


def get_cloud_run_region() -> str:
    return os.getenv("CLOUD_RUN_REGION", "europe-north1")


def print_config_summary():
    """Print a summary of the current configuration."""
    print("=" * 80)
    print("ESTATE VALUE INDEX CONFIGURATION SUMMARY")
    print("=" * 80)

    try:
        env_config = load_env_config()
    except KeyError as e:
        print(f"Missing required environment variable: {e}")
        return

    print(f"GCP Project: {env_config.gcp_project_id}")
    print(f"BigQuery Project: {env_config.bigquery_project_id}")
    print(f"Raw Dataset: {env_config.bq_dataset_raw}")
    print(f"Raw Table: {env_config.bq_table_listings}")
    print(f"Features Dataset: {env_config.bq_dataset_features}")
    print(f"Features Table: {env_config.bq_table_features}")
    print(f"GCS Bucket: {env_config.gcs_bucket}")

    print("\n" + "-" * 80)
    print("PIPELINE CONFIGURATION")
    print("-" * 80)

    yaml_config = load_yaml_config()
    if yaml_config:
        print(f"YAML Config: {len(yaml_config)} sections loaded")
        for section in yaml_config:
            print(f"   - {section}")
    else:
        print("No YAML configuration found")

    print(f"MAE Threshold: {get_mae_threshold():,} SEK")
    print(f"Random State: {get_random_state()}")
    print(f"CV Folds: {get_cv_folds()}")
    print(f"Test Size: {get_test_size()}")
    print(f"Batch Size: {get_batch_size()}")

    print("\n" + "-" * 80)
    print("FLAGS")
    print("-" * 80)
    print(f"Debug: {is_debug()}")
    print(f"Dry Run: {is_dry_run()}")
    print(f"Verbose Logging: {is_verbose_logging()}")
    print(f"GCS Enabled: {is_gcs_enabled()}")

    print("=" * 80)


if __name__ == "__main__":
    print_config_summary()
