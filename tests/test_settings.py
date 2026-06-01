"""Tests for utils.settings module."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.estate_value_index.utils.settings import (
    bq_table,
    get_batch_size,
    get_cloud_run_region,
    get_cloud_run_service_name,
    get_cv_folds,
    get_data_source,
    get_mae_threshold,
    get_max_pages,
    get_model_output_dir,
    get_model_prefix,
    get_random_state,
    get_test_size,
    is_debug,
    is_dry_run,
    is_gcs_enabled,
    is_verbose_logging,
    load_env_config,
    load_yaml_config,
    print_config_summary,
)


class TestEnvConfig:
    def test_load_env_config_with_required_vars(self):
        env_vars = {
            "GCP_PROJECT_ID": "test-project",
            "GCP_REGION": "europe-north1",
            "BIGQUERY_PROJECT_ID": "test-project",
            "BIGQUERY_DATASET_RAW": "test_raw",
            "BIGQUERY_TABLE_LISTINGS": "test_listings",
            "BIGQUERY_DATASET_FEATURES": "test_features",
            "BIGQUERY_TABLE_FEATURES": "test_engineered_features",
            "GCS_BUCKET": "test-bucket",
        }

        with patch.dict(os.environ, env_vars):
            config = load_env_config()

            assert config.gcp_project_id == "test-project"
            assert config.bigquery_project_id == "test-project"
            assert config.bq_dataset_raw == "test_raw"
            assert config.bq_table_listings == "test_listings"
            assert config.bq_dataset_features == "test_features"
            assert config.bq_table_features == "test_engineered_features"
            assert config.gcs_bucket == "test-bucket"

    def test_load_env_config_missing_required_var(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(KeyError):
                load_env_config()

    def test_load_env_config_with_defaults(self):
        env_vars = {
            "GCP_PROJECT_ID": "test-project",
            "GCP_REGION": "europe-north1",
            "BIGQUERY_PROJECT_ID": "test-project",
            "BIGQUERY_DATASET_RAW": "test_raw",
            "BIGQUERY_TABLE_LISTINGS": "test_listings",
            "GCS_BUCKET": "test-bucket",
        }

        with patch.dict(os.environ, env_vars):
            config = load_env_config()

            assert config.bq_dataset_features == "booli_features"
            assert config.bq_table_features == "engineered_features"


class TestYamlConfig:
    def test_load_yaml_config_existing_file(self):
        yaml_content = """
training:
  mae_threshold: 300000
  random_state: 123
  cv_folds: 3
  test_size: 0.3

bigquery:
  batch_size: 2000

scraping:
  default_max_pages: 20
  max_concurrent_requests: 8
  download_delay: 0.2
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            try:
                config = load_yaml_config(f.name)

                assert config["training"]["mae_threshold"] == 300000
                assert config["training"]["random_state"] == 123
                assert config["training"]["cv_folds"] == 3
                assert config["training"]["test_size"] == 0.3
                assert config["bigquery"]["batch_size"] == 2000
                assert config["scraping"]["default_max_pages"] == 20
                assert config["scraping"]["max_concurrent_requests"] == 8
                assert config["scraping"]["download_delay"] == 0.2
            finally:
                os.unlink(f.name)

    def test_load_yaml_config_nonexistent_file(self):
        assert load_yaml_config("nonexistent.yaml") == {}

    def test_load_yaml_config_default_path(self):
        with patch("src.estate_value_index.utils.settings.Path.exists", return_value=False):
            assert load_yaml_config() == {}


class TestHelperFunctions:
    def test_bq_table(self):
        assert bq_table("project", "dataset", "table") == "project.dataset.table"

    def test_get_mae_threshold_from_env(self):
        with patch.dict(os.environ, {"MAX_MAE_THRESHOLD": "300000"}):
            assert get_mae_threshold() == 300000

    def test_get_mae_threshold_from_yaml(self):
        with patch.dict(os.environ, {"MAX_MAE_THRESHOLD": ""}):
            with patch("src.estate_value_index.utils.settings.load_yaml_config") as mock_load:
                mock_load.return_value = {"training": {"mae_threshold": 350000}}
                assert get_mae_threshold() == 350000

    def test_get_mae_threshold_default(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("src.estate_value_index.utils.settings.load_yaml_config", return_value={}):
                assert get_mae_threshold() == 260000

    def test_get_random_state_from_yaml(self):
        with patch("src.estate_value_index.utils.settings.load_yaml_config") as mock_load:
            mock_load.return_value = {"training": {"random_state": 123}}
            assert get_random_state() == 123

    def test_get_random_state_default(self):
        with patch("src.estate_value_index.utils.settings.load_yaml_config", return_value={}):
            assert get_random_state() == 42

    def test_get_cv_folds_from_yaml(self):
        with patch("src.estate_value_index.utils.settings.load_yaml_config") as mock_load:
            mock_load.return_value = {"training": {"cv_folds": 3}}
            assert get_cv_folds() == 3

    def test_get_cv_folds_default(self):
        with patch("src.estate_value_index.utils.settings.load_yaml_config", return_value={}):
            assert get_cv_folds() == 5

    def test_get_test_size_from_yaml(self):
        with patch("src.estate_value_index.utils.settings.load_yaml_config") as mock_load:
            mock_load.return_value = {"training": {"test_size": 0.3}}
            assert get_test_size() == 0.3

    def test_get_test_size_default(self):
        with patch("src.estate_value_index.utils.settings.load_yaml_config", return_value={}):
            assert get_test_size() == 0.2

    def test_get_batch_size_from_env(self):
        with patch.dict(os.environ, {"BIGQUERY_BATCH_SIZE": "2000"}):
            assert get_batch_size() == 2000

    def test_get_batch_size_from_yaml(self):
        with patch("src.estate_value_index.utils.settings.load_yaml_config") as mock_load:
            mock_load.return_value = {"bigquery": {"batch_size": 1500}}
            assert get_batch_size() == 1500

    def test_get_batch_size_default(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("src.estate_value_index.utils.settings.load_yaml_config", return_value={}):
                assert get_batch_size() == 1000

    def test_get_max_pages_from_env(self):
        with patch.dict(os.environ, {"SCRAPER_MAX_PAGES": "25"}):
            assert get_max_pages() == 25

    def test_get_max_pages_from_yaml(self):
        with patch.dict(os.environ, {"SCRAPER_MAX_PAGES": ""}):
            with patch("src.estate_value_index.utils.settings.load_yaml_config") as mock_load:
                mock_load.return_value = {"scraping": {"default_max_pages": 15}}
                assert get_max_pages() == 15

    def test_get_max_pages_default(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("src.estate_value_index.utils.settings.load_yaml_config", return_value={}):
                assert get_max_pages() == 10


class TestBooleanFlags:
    def test_is_debug_true(self):
        for value in ["true", "1", "yes", "on", "TRUE", "True"]:
            with patch.dict(os.environ, {"DEBUG": value}):
                assert is_debug() is True

    def test_is_debug_false(self):
        for value in ["false", "0", "no", "off", "FALSE", "False", ""]:
            with patch.dict(os.environ, {"DEBUG": value}):
                assert is_debug() is False

    def test_is_debug_default(self):
        with patch.dict(os.environ, {}, clear=True):
            assert is_debug() is False

    def test_is_dry_run_true(self):
        for value in ["true", "1", "yes", "on"]:
            with patch.dict(os.environ, {"DRY_RUN": value}):
                assert is_dry_run() is True

    def test_is_dry_run_false(self):
        for value in ["false", "0", "no", "off", ""]:
            with patch.dict(os.environ, {"DRY_RUN": value}):
                assert is_dry_run() is False

    def test_is_dry_run_default(self):
        with patch.dict(os.environ, {}, clear=True):
            assert is_dry_run() is False

    def test_is_verbose_logging_true(self):
        for value in ["true", "1", "yes", "on"]:
            with patch.dict(os.environ, {"VERBOSE_LOGGING": value}):
                assert is_verbose_logging() is True

    def test_is_verbose_logging_false(self):
        for value in ["false", "0", "no", "off", ""]:
            with patch.dict(os.environ, {"VERBOSE_LOGGING": value}):
                assert is_verbose_logging() is False

    def test_is_verbose_logging_default(self):
        with patch.dict(os.environ, {}, clear=True):
            assert is_verbose_logging() is True

    def test_is_gcs_enabled_true(self):
        for value in ["true", "1", "yes", "on"]:
            with patch.dict(os.environ, {"GCS_ENABLED": value}):
                assert is_gcs_enabled() is True

    def test_is_gcs_enabled_false(self):
        for value in ["false", "0", "no", "off", ""]:
            with patch.dict(os.environ, {"GCS_ENABLED": value}):
                assert is_gcs_enabled() is False

    def test_is_gcs_enabled_default(self):
        # Default flipped: GCS is opt-in
        with patch.dict(os.environ, {}, clear=True):
            assert is_gcs_enabled() is False

    def test_is_gcs_enabled_single_source(self):
        """Both import paths must resolve to the same function object."""
        from estate_value_index.utils.gcs import is_gcs_enabled as gcs_fn
        from estate_value_index.utils.settings import is_gcs_enabled as settings_fn

        assert settings_fn is gcs_fn


class TestEnvVarFunctions:
    def test_get_data_source_from_env(self):
        with patch.dict(os.environ, {"DATA_SOURCE": "bigquery"}):
            assert get_data_source() == "bigquery"

    def test_get_data_source_default(self):
        with patch.dict(os.environ, {}, clear=True):
            assert get_data_source() == "bigquery"

    def test_get_model_prefix_from_env(self):
        with patch.dict(os.environ, {"MODEL_PREFIX": "custom_model"}):
            assert get_model_prefix() == "custom_model"

    def test_get_model_prefix_default(self):
        with patch.dict(os.environ, {}, clear=True):
            assert get_model_prefix() == "price_prediction_model"

    def test_get_model_output_dir_from_env(self):
        with patch.dict(os.environ, {"MODEL_OUTPUT_DIR": "custom/models"}):
            assert get_model_output_dir() == Path("custom/models")

    def test_get_model_output_dir_default(self):
        with patch.dict(os.environ, {}, clear=True):
            assert get_model_output_dir() == Path("web/models")

    def test_get_cloud_run_service_name_from_env(self):
        with patch.dict(os.environ, {"CLOUD_RUN_SERVICE_NAME": "custom-service"}):
            assert get_cloud_run_service_name() == "custom-service"

    def test_get_cloud_run_service_name_default(self):
        with patch.dict(os.environ, {}, clear=True):
            assert get_cloud_run_service_name() == "estate-value-index-app"

    def test_get_cloud_run_region_from_env(self):
        with patch.dict(os.environ, {"CLOUD_RUN_REGION": "us-central1"}):
            assert get_cloud_run_region() == "us-central1"

    def test_get_cloud_run_region_default(self):
        with patch.dict(os.environ, {}, clear=True):
            assert get_cloud_run_region() == "europe-north1"


class TestConfigSummary:
    def test_print_config_summary_with_valid_config(self, capsys):
        env_vars = {
            "GCP_PROJECT_ID": "test-project",
            "GCP_REGION": "europe-north1",
            "BIGQUERY_PROJECT_ID": "test-project",
            "BIGQUERY_DATASET_RAW": "test_raw",
            "BIGQUERY_TABLE_LISTINGS": "test_listings",
            "BIGQUERY_DATASET_FEATURES": "test_features",
            "BIGQUERY_TABLE_FEATURES": "test_engineered_features",
            "GCS_BUCKET": "test-bucket",
        }

        with patch.dict(os.environ, env_vars):
            with patch("src.estate_value_index.utils.settings.load_yaml_config") as mock_load:
                mock_load.return_value = {
                    "training": {"mae_threshold": 300000},
                    "bigquery": {"batch_size": 2000},
                    "scraping": {"default_max_pages": 20},
                }

                print_config_summary()

                captured = capsys.readouterr()
                assert "ESTATE VALUE INDEX CONFIGURATION SUMMARY" in captured.out
                assert "test-project" in captured.out
                assert "test_raw" in captured.out
                assert "test_listings" in captured.out
                assert "test_features" in captured.out
                assert "test_engineered_features" in captured.out
                assert "test-bucket" in captured.out

    def test_print_config_summary_with_missing_vars(self, capsys):
        with patch.dict(os.environ, {}, clear=True):
            print_config_summary()

            captured = capsys.readouterr()
            assert "ESTATE VALUE INDEX CONFIGURATION SUMMARY" in captured.out
            assert "Missing required environment variable" in captured.out
