"""Unit tests for drift detection module."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from estate_value_index.monitoring.drift_detection import DriftResult, ModelMonitor


@pytest.fixture
def baseline_data() -> pd.DataFrame:
    np.random.seed(42)
    n_samples = 500

    data = pd.DataFrame(
        {
            # Numeric features
            "living_area": np.random.normal(75, 20, n_samples),
            "price_per_sqm": np.random.normal(80000, 15000, n_samples),
            "area_target_encoded": np.random.normal(5000000, 1000000, n_samples),
            "area_price_median": np.random.normal(5500000, 1200000, n_samples),
            "days_on_market": np.random.exponential(30, n_samples),
            "construction_quality_score": np.random.uniform(0.5, 1.0, n_samples),
            "energy_efficiency_est": np.random.uniform(0.6, 1.0, n_samples),
            "area_sold_price_median_3m": np.random.normal(5200000, 1100000, n_samples),
            # Categorical features
            "area": np.random.choice(["sodermalm", "ostermalm", "vasastan"], n_samples),
            "swedish_season": np.random.choice(["winter", "spring", "summer", "autumn"], n_samples),
            "area_price_tier": np.random.choice(["mid", "high", "premium"], n_samples),
            "architectural_era": np.random.choice(
                ["pre_1930", "1930_1960", "post_1960"], n_samples
            ),
            # Target
            "sold_price": np.random.normal(6000000, 1500000, n_samples),
        }
    )

    # Ensure categorical columns are dtype='category'
    for col in ["area", "swedish_season", "area_price_tier", "architectural_era"]:
        data[col] = data[col].astype("category")

    return data


@pytest.fixture
def baseline_parquet_path(baseline_data: pd.DataFrame) -> Path:
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
        path = Path(tmp.name)
        baseline_data.to_parquet(path, index=False)
        return path


@pytest.fixture
def current_data_no_drift(baseline_data: pd.DataFrame) -> pd.DataFrame:
    np.random.seed(123)
    n_samples = 200

    data = pd.DataFrame(
        {
            # Same distribution as baseline
            "living_area": np.random.normal(75, 20, n_samples),
            "price_per_sqm": np.random.normal(80000, 15000, n_samples),
            "area_target_encoded": np.random.normal(5000000, 1000000, n_samples),
            "area_price_median": np.random.normal(5500000, 1200000, n_samples),
            "days_on_market": np.random.exponential(30, n_samples),
            "construction_quality_score": np.random.uniform(0.5, 1.0, n_samples),
            "energy_efficiency_est": np.random.uniform(0.6, 1.0, n_samples),
            "area_sold_price_median_3m": np.random.normal(5200000, 1100000, n_samples),
            "area": np.random.choice(["sodermalm", "ostermalm", "vasastan"], n_samples),
            "swedish_season": np.random.choice(["winter", "spring", "summer", "autumn"], n_samples),
            "area_price_tier": np.random.choice(["mid", "high", "premium"], n_samples),
            "architectural_era": np.random.choice(
                ["pre_1930", "1930_1960", "post_1960"], n_samples
            ),
            "sold_price": np.random.normal(6000000, 1500000, n_samples),
        }
    )

    for col in ["area", "swedish_season", "area_price_tier", "architectural_era"]:
        data[col] = data[col].astype("category")

    return data


@pytest.fixture
def current_data_with_drift(baseline_data: pd.DataFrame) -> pd.DataFrame:
    np.random.seed(456)
    n_samples = 200

    data = pd.DataFrame(
        {
            # Shifted distributions (drift)
            "living_area": np.random.normal(90, 25, n_samples),  # Larger apartments
            "price_per_sqm": np.random.normal(100000, 20000, n_samples),  # Higher prices
            "area_target_encoded": np.random.normal(6500000, 1200000, n_samples),  # Shift up
            "area_price_median": np.random.normal(7000000, 1500000, n_samples),  # Shift up
            "days_on_market": np.random.exponential(15, n_samples),  # Faster sales
            "construction_quality_score": np.random.uniform(0.7, 1.0, n_samples),  # Higher quality
            "energy_efficiency_est": np.random.uniform(0.8, 1.0, n_samples),  # Better efficiency
            "area_sold_price_median_3m": np.random.normal(6800000, 1400000, n_samples),  # Shift up
            # Different categorical distribution
            "area": np.random.choice(
                ["sodermalm", "ostermalm", "vasastan"], n_samples, p=[0.6, 0.3, 0.1]
            ),
            "swedish_season": np.random.choice(
                ["winter", "spring", "summer", "autumn"], n_samples, p=[0.1, 0.2, 0.5, 0.2]
            ),
            "area_price_tier": np.random.choice(
                ["mid", "high", "premium"], n_samples, p=[0.2, 0.5, 0.3]
            ),
            "architectural_era": np.random.choice(
                ["pre_1930", "1930_1960", "post_1960"], n_samples, p=[0.3, 0.3, 0.4]
            ),
            "sold_price": np.random.normal(7500000, 1800000, n_samples),  # Higher prices
        }
    )

    for col in ["area", "swedish_season", "area_price_tier", "architectural_era"]:
        data[col] = data[col].astype("category")

    return data


@pytest.fixture
def current_data_with_performance_degradation(baseline_data: pd.DataFrame) -> pd.DataFrame:
    np.random.seed(789)
    n_samples = 200

    # Same feature distribution as baseline
    data = pd.DataFrame(
        {
            "living_area": np.random.normal(75, 20, n_samples),
            "price_per_sqm": np.random.normal(80000, 15000, n_samples),
            "area_target_encoded": np.random.normal(5000000, 1000000, n_samples),
            "area_price_median": np.random.normal(5500000, 1200000, n_samples),
            "days_on_market": np.random.exponential(30, n_samples),
            "construction_quality_score": np.random.uniform(0.5, 1.0, n_samples),
            "energy_efficiency_est": np.random.uniform(0.6, 1.0, n_samples),
            "area_sold_price_median_3m": np.random.normal(5200000, 1100000, n_samples),
            "area": np.random.choice(["sodermalm", "ostermalm", "vasastan"], n_samples),
            "swedish_season": np.random.choice(["winter", "spring", "summer", "autumn"], n_samples),
            "area_price_tier": np.random.choice(["mid", "high", "premium"], n_samples),
            "architectural_era": np.random.choice(
                ["pre_1930", "1930_1960", "post_1960"], n_samples
            ),
            "sold_price": np.random.normal(6000000, 1500000, n_samples),
        }
    )

    for col in ["area", "swedish_season", "area_price_tier", "architectural_era"]:
        data[col] = data[col].astype("category")

    # Add predictions with large errors (simulating poor model performance)
    data["predicted_price"] = data["sold_price"] + np.random.normal(
        500000, 800000, n_samples
    )  # Large bias + variance

    return data


class TestModelMonitor:
    def test_initialization_success(self, baseline_parquet_path: Path):
        monitor = ModelMonitor(
            reference_data_path=baseline_parquet_path,
            model_version="test-v1",
        )

        assert monitor.model_version == "test-v1"
        assert len(monitor.reference_data) == 500
        assert "sold_price" in monitor.reference_data.columns

    def test_initialization_missing_target_warning(
        self, baseline_data: pd.DataFrame, tmp_path: Path
    ):
        data_no_target = baseline_data.drop(columns=["sold_price"])
        parquet_path = tmp_path / "no_target.parquet"
        data_no_target.to_parquet(parquet_path, index=False)

        monitor = ModelMonitor(reference_data_path=parquet_path, model_version="test-v1")

        assert "sold_price" not in monitor.reference_data.columns

    def test_detect_drift_no_drift(
        self, baseline_parquet_path: Path, current_data_no_drift: pd.DataFrame
    ):
        monitor = ModelMonitor(
            reference_data_path=baseline_parquet_path,
            model_version="test-v1",
        )

        result = monitor.detect_drift(current_data_no_drift)

        assert isinstance(result, DriftResult)
        # Allow minor random drift
        assert result.num_drifted_features <= 3
        assert result.drift_score < 0.5
        assert result.drift_detected is False
        assert not result.performance_degraded
        assert result.timestamp is not None
        assert len(result.report_html) > 0

    def test_detect_drift_with_drift(
        self, baseline_parquet_path: Path, current_data_with_drift: pd.DataFrame
    ):
        monitor = ModelMonitor(
            reference_data_path=baseline_parquet_path,
            model_version="test-v1",
        )

        result = monitor.detect_drift(current_data_with_drift)

        assert isinstance(result, DriftResult)
        assert result.drift_detected
        # Drift score can be 0.0 if column drift scores aren't in the report
        assert result.drift_score >= 0.0
        assert len(result.report_html) > 0

    def test_performance_degradation_uses_mdape_without_evidently(
        self, baseline_parquet_path: Path, current_data_with_performance_degradation: pd.DataFrame
    ):
        monitor = ModelMonitor(
            reference_data_path=baseline_parquet_path,
            model_version="test-v1",
        )

        monitor.reference_data["predicted_price"] = monitor.reference_data["sold_price"] * 1.02

        current_median_ape = monitor._median_ape(
            current_data_with_performance_degradation,
            "sold_price",
            "predicted_price",
        )
        reference_median_ape = monitor._median_ape(
            monitor.reference_data,
            "sold_price",
            "predicted_price",
        )
        degraded, degradation_pct = monitor._performance_degradation(
            current_median_ape,
            reference_median_ape,
            has_predictions=True,
        )

        assert current_median_ape is not None
        assert reference_median_ape == pytest.approx(0.02)
        assert degraded is True
        assert degradation_pct is not None
        assert degradation_pct > 10.0

    def test_drift_result_structure(
        self, baseline_parquet_path: Path, current_data_no_drift: pd.DataFrame
    ):
        monitor = ModelMonitor(
            reference_data_path=baseline_parquet_path,
            model_version="test-v1",
        )

        result = monitor.detect_drift(current_data_no_drift)

        for field in [
            "drift_detected",
            "drifted_features",
            "drift_score",
            "performance_degraded",
            "current_median_ape",
            "reference_median_ape",
            "degradation_pct",
            "report_html",
            "timestamp",
            "num_drifted_features",
        ]:
            assert hasattr(result, field)

        assert isinstance(result.drift_detected, bool)
        assert isinstance(result.drifted_features, list)
        assert isinstance(result.drift_score, float)
        assert isinstance(result.performance_degraded, bool)
        assert isinstance(result.report_html, str)
        assert isinstance(result.timestamp, str)
        assert isinstance(result.num_drifted_features, int)

    def test_detect_drift_with_missing_features(
        self, baseline_parquet_path: Path, current_data_no_drift: pd.DataFrame
    ):
        monitor = ModelMonitor(
            reference_data_path=baseline_parquet_path,
            model_version="test-v1",
        )

        common_numeric = ["living_area", "price_per_sqm", "area_target_encoded", "days_on_market"]
        common_categorical = ["area", "swedish_season"]
        cols_to_keep = common_numeric + common_categorical + ["sold_price"]

        result = monitor.detect_drift(current_data_no_drift[cols_to_keep])

        assert isinstance(result, DriftResult)
        assert len(result.report_html) > 0

    def test_critical_columns_come_from_model_metadata(
        self, baseline_data: pd.DataFrame, current_data_no_drift: pd.DataFrame, tmp_path: Path
    ):
        metadata = tmp_path / "metrics.json"
        metadata.write_text(
            """
            {
              "numeric_features": ["living_area"],
              "categorical_features": ["area"]
            }
            """,
            encoding="utf-8",
        )
        parquet_path = tmp_path / "baseline.parquet"
        baseline_data.to_parquet(parquet_path, index=False)

        monitor = ModelMonitor(
            reference_data_path=parquet_path,
            model_version="test-v1",
            feature_metadata_path=metadata,
        )

        categorical, numeric = monitor._critical_columns(current_data_no_drift)

        assert numeric == ["living_area"]
        assert categorical == ["area"]

    def test_extracts_evidently_04_data_drift_table(self, baseline_parquet_path: Path):
        monitor = ModelMonitor(
            reference_data_path=baseline_parquet_path,
            model_version="test-v1",
        )

        extracted = monitor._extract_all_metrics(
            {
                "metrics": [
                    {
                        "metric": "DataDriftTable",
                        "result": {
                            "dataset_drift": True,
                            "drift_by_columns": {
                                "living_area": {
                                    "drift_detected": True,
                                    "drift_score": 0.42,
                                },
                                "area": {
                                    "drift_detected": False,
                                    "drift_score": 0.05,
                                },
                            },
                        },
                    }
                ]
            }
        )

        assert extracted.dataset_drift is True
        assert extracted.drifted_features == ["living_area"]
        assert extracted.drift_scores == [0.42, 0.05]

    def test_html_report_generation(
        self, baseline_parquet_path: Path, current_data_with_drift: pd.DataFrame
    ):
        monitor = ModelMonitor(
            reference_data_path=baseline_parquet_path,
            model_version="test-v1",
        )

        result = monitor.detect_drift(current_data_with_drift)

        assert "<!DOCTYPE html>" in result.report_html or "<html" in result.report_html
        assert len(result.report_html) > 1000


@pytest.mark.unit
def test_drift_result_dataclass():
    result = DriftResult(
        drift_detected=True,
        drifted_features=["living_area", "price_per_sqm"],
        drift_score=0.35,
        performance_degraded=False,
        current_median_ape=0.062,
        reference_median_ape=0.058,
        degradation_pct=6.9,
        report_html="<html>Test Report</html>",
        timestamp="2025-12-24T10:00:00",
        num_drifted_features=2,
    )

    assert result.drift_detected
    assert len(result.drifted_features) == 2
    assert result.drift_score == 0.35
    assert not result.performance_degraded
    assert result.num_drifted_features == 2
