"""Settings: environment first, then defaults; unknown ``.env`` keys fail loudly."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from estate_value_index.exceptions import ConfigurationError
from estate_value_index.utils.settings import Settings, get_settings, is_gcs_enabled


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> pytest.MonkeyPatch:
    """No settings variables in the environment and no ``.env`` in the working directory."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    monkeypatch.chdir(tmp_path)
    return monkeypatch


def test_defaults_apply_without_environment(clean_env: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    assert settings.bigquery_dataset_raw == "booli_raw"
    assert settings.bigquery_table_listings == "listings"
    assert settings.gcs_enabled is False
    assert settings.max_median_ape_threshold == 0.08
    assert settings.ingestion_min_validation_rate == 0.5
    assert settings.data_source == "bigquery"


def test_environment_overrides_defaults(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("BIGQUERY_DATASET_RAW", "raw_test")
    clean_env.setenv("GCS_ENABLED", "true")
    clean_env.setenv("MAX_MEDIAN_APE_THRESHOLD", "0.07")

    settings = get_settings()
    assert settings.bigquery_dataset_raw == "raw_test"
    assert settings.gcs_enabled is True
    assert is_gcs_enabled() is True
    assert settings.max_median_ape_threshold == 0.07


def test_environment_wins_over_dotenv(clean_env: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("GCS_BUCKET=from-file\nGCP_PROJECT_ID=file-project\n")
    clean_env.setenv("GCS_BUCKET", "from-env")

    settings = get_settings()
    assert settings.gcs_bucket == "from-env"
    assert settings.gcp_project_id == "file-project"


def test_unknown_dotenv_key_is_rejected(clean_env: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("NOT_A_SETTING=1\n")
    with pytest.raises(ValidationError, match="not_a_setting"):
        get_settings()


def test_invalid_values_are_rejected(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("GCS_ENABLED", "maybe")
    with pytest.raises(ValidationError):
        get_settings()
    clean_env.setenv("GCS_ENABLED", "false")
    clean_env.setenv("MAX_MEDIAN_APE_THRESHOLD", "8")
    with pytest.raises(ValidationError):
        get_settings()


def test_bigquery_project_falls_back_to_gcp_project(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("GCP_PROJECT_ID", "gcp-project")
    assert get_settings().require_bigquery_project_id() == "gcp-project"
    clean_env.setenv("BIGQUERY_PROJECT_ID", "bq-project")
    assert get_settings().require_bigquery_project_id() == "bq-project"
    assert get_settings().listings_table_ref() == "bq-project.booli_raw.listings"


def test_required_values_raise_when_missing(clean_env: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    with pytest.raises(ConfigurationError, match="GCP_PROJECT_ID"):
        settings.require_bigquery_project_id()
    with pytest.raises(ConfigurationError, match="GCS_BUCKET"):
        settings.require_gcs_bucket()


def test_env_example_holds_only_settings_keys(clean_env: pytest.MonkeyPatch) -> None:
    example = Path(__file__).resolve().parents[1] / ".env.example"
    settings = Settings(_env_file=example)  # pyright: ignore[reportCallIssue]  # BaseSettings accepts _env_file, but its generated __init__ signature omits it
    assert settings.gcp_project_id == "your-gcp-project-id"
