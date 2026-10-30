"""Runtime settings: one typed model read from the environment and an optional ``.env``.

Precedence: environment variables, then ``.env``, then the field defaults below.
``extra="forbid"`` makes an unknown key in ``.env`` an error instead of a silent no-op.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from estate_value_index.exceptions import ConfigurationError
from estate_value_index.utils.bigquery_safety import safe_table_ref


class Settings(BaseSettings):
    """Field names match the environment variable names (case-insensitive)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="forbid",
        frozen=True,
    )

    gcp_project_id: str | None = None
    gcp_region: str = "europe-north1"
    bigquery_project_id: str | None = None
    bigquery_dataset_raw: str = "booli_raw"
    bigquery_table_listings: str = "listings"
    bigquery_dataset_features: str = "booli_features"
    bigquery_table_features: str = "engineered_features"
    gcs_enabled: bool = False
    gcs_bucket: str | None = None
    # Where the Vertex trainer uploads artifacts (a gs:// URI or a bucket prefix).
    model_artifacts_uri: str | None = None
    model_artifacts_prefix: str | None = None
    data_source: Literal["bigquery", "json"] = "bigquery"
    booli_train_data: str | None = None
    booli_api_caller_id: SecretStr | None = None
    booli_api_private_key: SecretStr | None = None
    # Production quality bar as MdAPE (median absolute % error), a fraction.
    max_median_ape_threshold: float = Field(default=0.08, gt=0, lt=1)
    ingestion_min_validation_rate: float = Field(default=0.5, ge=0, le=1)

    def require_gcp_project_id(self) -> str:
        if not self.gcp_project_id:
            raise ConfigurationError("GCP_PROJECT_ID is not set.")
        return self.gcp_project_id

    def require_bigquery_project_id(self) -> str:
        return self.bigquery_project_id or self.require_gcp_project_id()

    def require_gcs_bucket(self) -> str:
        if not self.gcs_bucket:
            raise ConfigurationError("GCS_BUCKET is not set; required when GCS is enabled.")
        return self.gcs_bucket

    def listings_table_ref(self) -> str:
        """Validated ``project.dataset.table`` for the raw listings table."""
        return safe_table_ref(
            self.require_bigquery_project_id(),
            self.bigquery_dataset_raw,
            self.bigquery_table_listings,
        )


def get_settings() -> Settings:
    """Read the settings now. Not cached, so a changed environment takes effect at once."""
    return Settings()


def is_gcs_enabled() -> bool:
    return get_settings().gcs_enabled
