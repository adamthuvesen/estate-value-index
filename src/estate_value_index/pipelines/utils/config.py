"""Pipeline configuration utilities.

Provides pipeline-specific config objects that build on the central settings module.
"""

from dataclasses import dataclass

from google.cloud import bigquery

from estate_value_index.pipelines.constants import (
    DEFAULT_MACHINE_TYPE,
    DEFAULT_MAE_THRESHOLD,
    DEFAULT_MODEL_DIR,
    DEFAULT_MODEL_PREFIX,
)
from estate_value_index.utils.clients import get_bq_client
from estate_value_index.utils.settings import load_env_config


@dataclass
class BigQueryConfig:
    """BigQuery client and table configuration."""

    project_id: str
    dataset_id: str
    table_id: str
    client: bigquery.Client

    @property
    def full_table_id(self) -> str:
        """Return fully qualified table ID."""
        return f"{self.project_id}.{self.dataset_id}.{self.table_id}"


def get_bq_config(
    project_id: str | None = None,
    dataset_id: str | None = None,
    table_id: str | None = None,
    *,
    use_features_table: bool = False,
) -> BigQueryConfig:
    """Get BigQuery configuration with environment defaults.

    Args:
        project_id: Override project ID (default: from env)
        dataset_id: Override dataset ID (default: from env)
        table_id: Override table ID (default: from env)
        use_features_table: If True, use features dataset/table defaults
                            instead of raw listings defaults

    Returns:
        BigQueryConfig with client and table identifiers
    """
    env = load_env_config()
    proj = project_id or env.bigquery_project_id

    if use_features_table:
        default_dataset = env.bq_dataset_features
        default_table = env.bq_table_features
    else:
        default_dataset = env.bq_dataset_raw
        default_table = env.bq_table_listings

    return BigQueryConfig(
        project_id=proj,
        dataset_id=dataset_id or default_dataset,
        table_id=table_id or default_table,
        client=get_bq_client(proj),
    )


@dataclass
class TrainingFlowConfig:
    """Configuration for training flows."""

    # Training configuration
    tune: bool = False
    machine_type: str = DEFAULT_MACHINE_TYPE
    importance_threshold: float | None = None
    production_mode: bool = True

    # Pipeline toggles
    rebuild_container: bool = False
    skip_materialization: bool = False
    register_to_vertex: bool = False
    stream_logs: bool = True

    # Validation thresholds
    max_mae: float = DEFAULT_MAE_THRESHOLD
    max_rmse: float | None = None

    # Fallback options
    use_vertex: bool = True

    # Advanced options
    custom_display_name: str | None = None
    model_prefix: str = DEFAULT_MODEL_PREFIX
    local_model_dir: str = DEFAULT_MODEL_DIR

    # Dry run mode
    dry_run: bool = False


@dataclass
class DeploymentFlowConfig:
    """Configuration for deployment flows."""

    # GCS URIs (None = resolve from environment)
    model_artifacts_gcs_uri: str | None = None
    enrichment_gcs_uri: str | None = None

    # Cloud Run settings
    service_name: str | None = None
    region: str | None = None

    # Behavior
    validate: bool = True
    auto_rollback_on_failure: bool = False
    dry_run: bool = False
