"""Model monitoring with Evidently AI for drift detection."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from estate_value_index.monitoring.constants import (
    CRITICAL_CATEGORICAL_FEATURES,
    CRITICAL_NUMERIC_FEATURES,
    PERFORMANCE_DEGRADATION_THRESHOLD,
)

logger = logging.getLogger(__name__)


@dataclass
class DriftResult:
    """Results from drift detection analysis."""

    drift_detected: bool
    drifted_features: list[str]
    drift_score: float
    performance_degraded: bool
    current_median_ape: float | None
    reference_median_ape: float | None
    degradation_pct: float | None
    report_html: str
    timestamp: str
    num_drifted_features: int


@dataclass
class _ExtractedMetrics:
    dataset_drift: bool
    drifted_features: list[str]
    drift_scores: list[float]


class ModelMonitor:
    """Production model monitoring with Evidently AI.

    Detects data drift and performance degradation by comparing current
    production data against baseline training data.

    Args:
        reference_data_path: Path to baseline training data (parquet)
        model_version: Model version identifier (e.g., "2025-12-23-lgbm")
    """

    def __init__(
        self,
        reference_data_path: str | Path,
        model_version: str,
    ) -> None:
        self.reference_data = pd.read_parquet(reference_data_path)
        self.model_version = model_version

        if "sold_price" not in self.reference_data.columns:
            logger.warning("Reference data missing 'sold_price' - performance monitoring disabled")

    def detect_drift(
        self,
        current_data: pd.DataFrame,
        target_column: str = "sold_price",
        prediction_column: str = "predicted_price",
    ) -> DriftResult:
        """Detect data drift and performance degradation.

        Args:
            current_data: Recent production data with features and predictions
            target_column: Name of target column (actual values)
            prediction_column: Name of prediction column

        Returns:
            DriftResult with drift metrics and HTML report
        """
        logger.info(
            f"Running drift detection: {len(self.reference_data)} reference vs "
            f"{len(current_data)} current samples"
        )

        has_predictions = self._has_predictions(
            current_data,
            target_column=target_column,
            prediction_column=prediction_column,
        )
        column_mapping = self._column_mapping(
            current_data,
            has_predictions=has_predictions,
            target_column=target_column,
            prediction_column=prediction_column,
        )
        drift_report = self._run_drift_report(current_data, column_mapping, has_predictions)

        extracted = self._extract_all_metrics(drift_report.as_dict())
        drift_score = self._drift_score(extracted.drift_scores)
        # Gate performance on MdAPE (median absolute % error), the AVM-standard
        # metric. Evidently reports MAE, not MdAPE, so compute it from the data.
        current_median_ape = self._median_ape(current_data, target_column, prediction_column)
        reference_median_ape = self._median_ape(
            self.reference_data, target_column, prediction_column
        )
        performance_degraded, degradation_pct = self._performance_degradation(
            current_median_ape,
            reference_median_ape,
            has_predictions=has_predictions,
        )

        logger.info(
            f"Drift detection complete: drift={extracted.dataset_drift}, "
            f"drifted_features={len(extracted.drifted_features)}, "
            f"performance_degraded={performance_degraded}"
        )

        return DriftResult(
            drift_detected=extracted.dataset_drift,
            drifted_features=extracted.drifted_features,
            drift_score=drift_score,
            performance_degraded=performance_degraded,
            current_median_ape=current_median_ape,
            reference_median_ape=reference_median_ape,
            degradation_pct=degradation_pct,
            report_html=drift_report.get_html(),
            timestamp=datetime.now().isoformat(),
            num_drifted_features=len(extracted.drifted_features),
        )

    def _median_ape(
        self,
        data: pd.DataFrame,
        target_column: str,
        prediction_column: str,
    ) -> float | None:
        """Median absolute % error, or None when target/prediction are unavailable."""
        if target_column not in data.columns or prediction_column not in data.columns:
            return None
        actual = pd.to_numeric(data[target_column], errors="coerce")
        predicted = pd.to_numeric(data[prediction_column], errors="coerce")
        abs_pct = (predicted - actual).abs() / actual.replace(0, pd.NA)
        abs_pct = abs_pct.replace([float("inf"), float("-inf")], pd.NA).dropna()
        if abs_pct.empty:
            return None
        return float(abs_pct.median())

    def _has_predictions(
        self,
        current_data: pd.DataFrame,
        *,
        target_column: str,
        prediction_column: str,
    ) -> bool:
        cur_cols = current_data.columns
        return prediction_column in cur_cols and target_column in cur_cols

    def _critical_columns(self, current_data: pd.DataFrame) -> tuple[list[str], list[str]]:
        ref_cols = self.reference_data.columns
        cur_cols = current_data.columns
        categorical_cols = [
            f for f in CRITICAL_CATEGORICAL_FEATURES if f in ref_cols and f in cur_cols
        ]
        numeric_cols = [f for f in CRITICAL_NUMERIC_FEATURES if f in ref_cols and f in cur_cols]
        return categorical_cols, numeric_cols

    def _column_mapping(
        self,
        current_data: pd.DataFrame,
        *,
        has_predictions: bool,
        target_column: str,
        prediction_column: str,
    ) -> ColumnMapping:
        # Imported lazily: the prediction serving path imports this module
        # transitively (production_models -> runner -> monitoring), but the
        # runtime image installs only .[ml], not the .[monitoring] extra that
        # provides evidently. Drift detection is a separate monitoring job.
        from evidently import ColumnMapping

        categorical_cols, numeric_cols = self._critical_columns(current_data)
        column_mapping = ColumnMapping()
        column_mapping.numerical_features = numeric_cols
        column_mapping.categorical_features = categorical_cols

        if has_predictions:
            column_mapping.target = target_column
            column_mapping.prediction = prediction_column

        return column_mapping

    def _run_drift_report(
        self,
        current_data: pd.DataFrame,
        column_mapping: ColumnMapping,
        has_predictions: bool,
    ) -> Report:
        # Lazy import: see _column_mapping. Keeps evidently out of the serving path.
        from evidently.metric_preset import DataDriftPreset, RegressionPreset
        from evidently.report import Report

        metrics: list = [DataDriftPreset()]
        if has_predictions:
            metrics.append(RegressionPreset())
        drift_report = Report(metrics=metrics)
        drift_report.run(
            reference_data=self.reference_data,
            current_data=current_data,
            column_mapping=column_mapping,
        )
        return drift_report

    def _drift_score(self, drift_scores: list[float]) -> float:
        return sum(drift_scores) / len(drift_scores) if drift_scores else 0.0

    def _performance_degradation(
        self,
        current_median_ape: float | None,
        reference_median_ape: float | None,
        *,
        has_predictions: bool,
    ) -> tuple[bool, float | None]:
        if (
            not has_predictions
            or current_median_ape is None
            or reference_median_ape is None
            or reference_median_ape == 0
        ):
            return False, None

        degradation_pct = (
            (current_median_ape - reference_median_ape) / reference_median_ape * 100
        )
        return degradation_pct > (PERFORMANCE_DEGRADATION_THRESHOLD * 100), degradation_pct

    def _extract_all_metrics(self, report_dict: dict) -> _ExtractedMetrics:
        """Extract data-drift metrics from an Evidently report dict."""
        dataset_drift = False
        drifted_features: list[str] = []
        drift_scores: list[float] = []

        for metric in report_dict.get("metrics", []):
            metric_type = metric.get("metric")
            result = metric.get("result", {})

            if metric_type == "DatasetDriftMetric":
                dataset_drift = result.get("dataset_drift", False)

            elif metric_type == "ColumnDriftMetric":
                drifted = result.get("drift_detected", False)
                if drifted:
                    drifted_features.append(result.get("column_name", "unknown"))
                score = result.get("drift_score", 0.0)
                if score == 0.0 and drifted:
                    score = 1.0
                drift_scores.append(score)

        return _ExtractedMetrics(
            dataset_drift=dataset_drift,
            drifted_features=drifted_features,
            drift_scores=drift_scores,
        )
