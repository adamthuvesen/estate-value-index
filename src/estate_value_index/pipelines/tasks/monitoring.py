"""Tasks for ML monitoring: drift detection, alert management."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
from prefect import task

from estate_value_index.monitoring.drift_detection import DriftResult, ModelMonitor
from estate_value_index.pipelines.utils import get_task_logger
from estate_value_index.utils.bigquery_safety import safe_table_ref
from estate_value_index.utils.clients import get_bq_client, get_storage_client
from estate_value_index.utils.gcs import get_gcs_bucket, upload_blob, upload_html_to_gcs

# Kwargs forwarded to `complete_pipeline_flow` from
# `trigger_retraining_on_drift_task`. Defined as a module-level constant so the
# contract test in tests/pipelines/test_flow_signatures.py can validate every
# key against the flow's actual signature without duplicating literals.
_DRIFT_RETRAIN_KWARGS: dict = {
    "skip_scraping": True,
    "tune": True,
    "use_vertex": True,
    "deploy_to_prod": True,
}


@task(name="export-recent-predictions", retries=2, retry_delay_seconds=30)
def export_recent_predictions_task(
    days_lookback: int = 7,
    output_path: Path | None = None,
) -> dict:
    """Export recent predictions from BigQuery for drift detection.

    Args:
        days_lookback: Number of days of predictions to export
        output_path: Local path to save exported data (optional)

    Returns:
        Dict with export status and path
    """
    logger = get_task_logger(__name__)
    logger.info(f"Exporting predictions from last {days_lookback} days")

    from google.cloud import bigquery

    client = get_bq_client()
    project_id = client.project

    # Query to get recent predictions with features (parameterized for security)
    query = f"""
        SELECT *
        FROM {safe_table_ref(project_id, "booli_raw", "predictions", quote=True)}
        WHERE prediction_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @days_lookback DAY)
        ORDER BY prediction_timestamp DESC
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("days_lookback", "INT64", days_lookback),
        ]
    )

    try:
        df = client.query(query, job_config=job_config).to_dataframe()
        logger.info(f"Exported {len(df)} predictions from predictions table")
    except Exception as e:
        # Predictions table is optional in some environments; fall through to features-table fallback
        logger.info(f"Predictions table not available: {e}")
        df = pd.DataFrame()

    # Fallback 1: Use features table with feature_date filter (when features were computed)
    if len(df) < 10:
        logger.info("Using features table fallback with feature_date filter")
        fallback_query = f"""
            SELECT *
            FROM {safe_table_ref(project_id, "booli_features", "engineered_features", quote=True)}
            WHERE feature_date >= DATE_SUB(CURRENT_DATE(), INTERVAL @days_lookback DAY)
            ORDER BY feature_date DESC
            LIMIT 500
        """
        fallback_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("days_lookback", "INT64", days_lookback),
            ]
        )
        df = client.query(fallback_query, job_config=fallback_config).to_dataframe()
        logger.info(f"Exported {len(df)} rows using feature_date filter")

    # Fallback 2: Sample from most recent available data (no date filter)
    if len(df) < 10:
        logger.info("No recent data found, sampling from most recent available data")
        sample_query = f"""
            SELECT *
            FROM {safe_table_ref(project_id, "booli_features", "engineered_features", quote=True)}
            ORDER BY feature_date DESC
            LIMIT 500
        """
        df = client.query(sample_query).to_dataframe()
        logger.info(f"Sampled {len(df)} rows from most recent available data")

    # Validate sufficient data for drift detection
    if len(df) < 10:
        logger.warning(f"Insufficient data for drift detection: {len(df)} rows (need at least 10)")
        return {
            "success": False,
            "row_count": len(df),
            "error": "Insufficient recent data for drift detection",
            "timestamp": datetime.now().isoformat(),
        }

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(output_path, index=False)
        logger.info(f"Saved to {output_path}")

    return {
        "success": True,
        "row_count": len(df),
        "output_path": str(output_path) if output_path else None,
        "timestamp": datetime.now().isoformat(),
    }


@task(name="monitor-model-drift", retries=2, retry_delay_seconds=30)
def monitor_model_drift_task(
    current_data_path: str | Path,
    reference_data_path: str | Path,
    model_version: str,
    alert_on_drift: bool = True,
    upload_to_gcs: bool = True,
    gcs_bucket: str | None = None,
) -> dict:
    """Monitor model drift and trigger alerts if needed.

    Args:
        current_data_path: Path to current production data (parquet)
        reference_data_path: Path to baseline training data (parquet, can be gs:// URI)
        model_version: Model version identifier
        alert_on_drift: If True, log alerts when drift detected
        upload_to_gcs: If True, upload drift reports to GCS
        gcs_bucket: GCS bucket for report storage

    Returns:
        Dict with drift detection results
    """
    logger = get_task_logger(__name__)
    logger.info("Running drift detection")

    # Load current data
    current_data = pd.read_parquet(current_data_path)

    # Handle GCS reference path - download to temp file first
    reference_path_str = str(reference_data_path)
    if reference_path_str.startswith("gs://"):
        # Parse GCS URI
        gcs_parts = reference_path_str.replace("gs://", "").split("/", 1)
        bucket_name = gcs_parts[0]
        blob_name = gcs_parts[1] if len(gcs_parts) > 1 else ""

        client = get_storage_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        if not blob.exists():
            # Baseline must be created during model training, not from current data
            # Creating baseline from current data would compare data to itself (useless)
            logger.error(
                f"Baseline data not found at {reference_path_str}. "
                "Baseline must be created during model training. "
                "Run train_model.py with GCS_ENABLED=true to create baseline."
            )
            return {
                "success": False,
                "drift_detected": False,
                "drifted_features": [],
                "num_drifted_features": 0,
                "drift_score": 0.0,
                "performance_degraded": False,
                "current_median_ape": None,
                "reference_median_ape": None,
                "degradation_pct": None,
                "timestamp": datetime.now().isoformat(),
                "error": "Baseline not found - run model training first to create baseline",
            }

        # Download baseline to temp file
        local_reference_path = Path("/tmp/baseline_data.parquet")
        blob.download_to_filename(str(local_reference_path))
        reference_data_path = local_reference_path
        logger.info(
            f"Downloaded baseline from GCS: {len(pd.read_parquet(local_reference_path))} rows"
        )

    # Initialize monitor
    monitor = ModelMonitor(
        reference_data_path=reference_data_path,
        model_version=model_version,
    )

    # Detect drift
    result: DriftResult = monitor.detect_drift(current_data)

    # Save HTML report locally (for CI artifact upload) and to GCS
    report_name = f"drift_report_{model_version}_{result.timestamp.replace(':', '-')}.html"
    local_report_path = Path("/tmp") / report_name
    local_report_path.write_text(result.report_html)
    logger.info(f"Saved drift report locally: {local_report_path}")

    if upload_to_gcs:
        gcs_bucket = gcs_bucket or get_gcs_bucket()
        gcs_path = f"monitoring/drift_reports/{report_name}"

        upload_html_to_gcs(
            html_content=result.report_html,
            bucket_name=gcs_bucket,
            destination_blob_name=gcs_path,
        )
        logger.info(f"Uploaded drift report to gs://{gcs_bucket}/{gcs_path}")

    # Alert if drift detected
    if alert_on_drift and result.drift_detected:
        logger.warning(
            f"Data drift detected! {result.num_drifted_features} features drifted: "
            f"{', '.join(result.drifted_features[:5])}"
        )

    # Alert if performance degraded
    if result.performance_degraded:
        logger.critical(
            f"Model performance degraded by {result.degradation_pct:.1f}%! "
            f"MdAPE: {result.reference_median_ape:.2%} → {result.current_median_ape:.2%}"
        )

    # Return structured result
    return {
        "success": True,
        "drift_detected": result.drift_detected,
        "drifted_features": result.drifted_features,
        "num_drifted_features": result.num_drifted_features,
        "drift_score": result.drift_score,
        "performance_degraded": result.performance_degraded,
        "current_median_ape": result.current_median_ape,
        "reference_median_ape": result.reference_median_ape,
        "degradation_pct": result.degradation_pct,
        "timestamp": result.timestamp,
    }


@task(name="save-baseline-data", retries=2, retry_delay_seconds=30)
def save_baseline_data_task(
    training_data: pd.DataFrame,
    gcs_bucket: str | None = None,
    baseline_path: str = "monitoring/baseline/baseline_data.parquet",
) -> dict:
    """Save training data as baseline for drift detection.

    Args:
        training_data: Training dataframe with features and target
        gcs_bucket: GCS bucket name
        baseline_path: GCS path for baseline data

    Returns:
        Dict with save status
    """
    logger = get_task_logger(__name__)
    gcs_bucket = gcs_bucket or get_gcs_bucket()
    logger.info(f"Saving baseline data: {len(training_data)} rows")

    # Save locally first
    local_path = Path("/tmp/baseline_data.parquet")
    training_data.to_parquet(local_path, index=False)

    # Upload to GCS
    upload_blob(
        bucket_name=gcs_bucket,
        source_file_name=str(local_path),
        destination_blob_name=baseline_path,
    )

    logger.info(f"Baseline data saved to gs://{gcs_bucket}/{baseline_path}")

    return {
        "success": True,
        "row_count": len(training_data),
        "gcs_uri": f"gs://{gcs_bucket}/{baseline_path}",
        "timestamp": datetime.now().isoformat(),
    }


@task(name="trigger-retraining-on-drift")
def trigger_retraining_on_drift_task(
    drift_result: dict,
    auto_retrain: bool = True,
) -> dict:
    """Trigger retraining workflow if drift exceeds thresholds.

    Args:
        drift_result: Output from monitor_model_drift_task
        auto_retrain: If True, automatically trigger retraining

    Returns:
        Dict with retraining status
    """
    logger = get_task_logger(__name__)

    if not drift_result.get("success", False):
        logger.warning(
            f"Drift task failed; skipping retrain trigger. "
            f"upstream_error={drift_result.get('error')}"
        )
        return {
            "success": False,
            "retrain_triggered": False,
            "reason": "drift task failed",
            "upstream_error": drift_result.get("error"),
        }

    should_retrain = (
        drift_result["performance_degraded"] or drift_result["num_drifted_features"] >= 3
    )

    if not should_retrain:
        logger.info("No retraining needed")
        return {"success": True, "retrain_triggered": False}

    if not auto_retrain:
        logger.warning("Retraining needed but auto_retrain=False")
        return {"success": True, "retrain_triggered": False}

    logger.info("Triggering retraining due to drift")

    # Trigger complete pipeline with retrain flag. Kwargs must match
    # `complete_pipeline_flow`'s signature.
    from estate_value_index.pipelines.core.complete_pipeline import complete_pipeline_flow

    flow_run = complete_pipeline_flow.with_options(
        name=f"auto-retrain-drift-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    )(**_DRIFT_RETRAIN_KWARGS)

    logger.info(f"Retraining flow triggered: {flow_run}")

    return {
        "success": True,
        "retrain_triggered": True,
        "flow_run_id": str(flow_run),
        "timestamp": datetime.now().isoformat(),
    }
