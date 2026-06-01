#!/usr/bin/env python3
"""Prefect flow for Vertex AI training orchestration.

This flow manages the complete ML pipeline using Vertex AI Custom Training Jobs:
1. Materialize features in BigQuery
2. (Optional) Rebuild training container
3. Submit training job to Vertex AI
4. Monitor job completion
5. Download model artifacts
6. Validate model performance
7. (Optional) Register to Vertex AI Model Registry
"""

import io
import json
import sys
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from datetime import datetime
from logging import Logger
from pathlib import Path

from prefect import flow, get_run_logger

from estate_value_index.ml.training_workflow import TrainingConfig, run_training

# Import training tasks from new focused modules
from estate_value_index.pipelines.tasks import (
    download_model_artifacts_task,
    materialize_features_task,
    poll_vertex_job_status_task,
    promote_model_to_production_task,
    rebuild_container_task,
    register_model_to_vertex_task,
    submit_vertex_training_job_task,
    validate_model_performance_task,
)
from estate_value_index.pipelines.utils import TrainingFlowConfig
from estate_value_index.utils.gcs import get_gcs_bucket


@dataclass
class _VertexJobState:
    """Mutable identifiers and artifact locations resolved across Vertex stages."""

    job_id: str | None = None
    run_id: str | None = None
    model_uri: str | None = None
    resolved_model_prefix: str | None = None
    submission_results: dict = field(default_factory=dict)


def _log_flow_configuration(config: TrainingFlowConfig, logger: Logger) -> None:
    """Log the flow header and resolved configuration."""
    logger.info("=" * 80)
    logger.info("Starting Vertex AI Training Pipeline")
    logger.info("=" * 80)
    logger.info("Configuration:")
    logger.info(f"  Use Vertex AI: {config.use_vertex}")
    logger.info(f"  Hyperparameter tuning: {config.tune}")
    logger.info(f"  Machine type: {config.machine_type}")
    logger.info(f"  Rebuild container: {config.rebuild_container}")
    logger.info(f"  Skip materialization: {config.skip_materialization}")
    logger.info(f"  Register to Vertex: {config.register_to_vertex}")
    logger.info(f"  Dry run: {config.dry_run}")
    logger.info("=" * 80)


def _run_local_training(config: TrainingFlowConfig, results: dict, logger: Logger) -> dict:
    """Stage: run training locally when Vertex AI is disabled."""
    logger.info("Running LOCAL training (Vertex AI disabled)")
    logger.info("-" * 80)

    data_file = Path("data/raw/booli/booli_listings_prod.json")
    if not data_file.exists():
        raise FileNotFoundError(f"Training data not found: {data_file}")

    logger.info(
        "Training with: tune=%s, use_materialized_features=%s, production_mode=%s",
        config.tune,
        False,
        config.production_mode,
    )
    logger.info("Using local data file: %s", data_file)

    try:
        stdout_capture = io.StringIO()
        with redirect_stdout(stdout_capture):
            mae = run_training(
                TrainingConfig(
                    hyperparameter_tuning=config.tune,
                    data_source="json",
                    use_materialized_features=False,
                    data_file=str(data_file),
                    model_dir=None,
                    metrics_prefix=None,
                    importance_threshold=config.importance_threshold,
                    production_mode=config.production_mode,
                    config_file=None,
                )
            )

        logger.info(f"Training completed with MAE: {mae:,.0f} SEK")
        training_results = {"success": True, "method": "local_direct", "mae": mae}
        results["steps"]["local_training"] = training_results
        results["success"] = True

    except Exception as e:
        logger.error(f"Training failed: {e}")
        raise RuntimeError(f"Local training failed: {e}") from e

    # Validate local model
    metrics_file = Path(config.local_model_dir) / f"{config.model_prefix}_metrics_lgbm.json"
    if metrics_file.exists():
        validation_results = validate_model_performance_task(
            metrics_path=metrics_file, max_mae=config.max_mae, max_rmse=config.max_rmse
        )
        results["steps"]["validation"] = validation_results
        results["validation_passed"] = validation_results["validation_passed"]
        results["metrics"] = {
            "mae": validation_results["mae"],
            "rmse": validation_results.get("rmse"),
            "r2": validation_results.get("r2"),
        }

    logger.info("=" * 80)
    logger.info("Local training flow completed")
    logger.info("=" * 80)
    return results


def _materialize_features_stage(config: TrainingFlowConfig, results: dict, logger: Logger) -> None:
    """Stage 1: materialize engineered features in BigQuery."""
    if not config.skip_materialization:
        logger.info("STEP 1: Materializing features in BigQuery")
        logger.info("-" * 80)

        if not config.dry_run:
            materialization_results = materialize_features_task(truncate=True)
            results["steps"]["materialize_features"] = materialization_results

            if materialization_results.get("row_count"):
                logger.info(f"Materialized {materialization_results['row_count']} rows")
        else:
            logger.info("DRY RUN: Skipping feature materialization")
            results["steps"]["materialize_features"] = {"skipped": True, "reason": "dry_run"}
    else:
        logger.info("STEP 1: Skipping feature materialization (skip_materialization=True)")
        results["steps"]["materialize_features"] = {"skipped": True, "reason": "user_skip"}


def _rebuild_container_stage(config: TrainingFlowConfig, results: dict, logger: Logger) -> None:
    """Stage 2: optionally rebuild the training container image."""
    if config.rebuild_container:
        logger.info("STEP 2: Rebuilding training container")
        logger.info("-" * 80)

        if not config.dry_run:
            build_results = rebuild_container_task(dry_run=config.dry_run)
            results["steps"]["rebuild_container"] = build_results

            if build_results.get("image_uri"):
                logger.info(f"Container built: {build_results['image_uri']}")
        else:
            logger.info("DRY RUN: Skipping container rebuild")
            results["steps"]["rebuild_container"] = {"skipped": True, "reason": "dry_run"}
    else:
        logger.info("STEP 2: Skipping container rebuild (using existing image)")
        results["steps"]["rebuild_container"] = {"skipped": True, "reason": "user_skip"}


def _submit_training_job_stage(
    config: TrainingFlowConfig, results: dict, logger: Logger
) -> tuple[_VertexJobState | None, bool]:
    """Stage 3: submit the Vertex AI training job.

    Returns the resolved job state and a flag signalling the flow should return early.
    """
    logger.info("STEP 3: Submitting training job to Vertex AI")
    logger.info("-" * 80)

    job_display_name = (
        config.custom_display_name or f"lgbm-train-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    )

    submission_results = submit_vertex_training_job_task(
        tune=config.tune,
        machine_type=config.machine_type,
        importance_threshold=config.importance_threshold,
        production_mode=config.production_mode,
        display_name=job_display_name,
        image_uri=(results.get("steps", {}).get("rebuild_container", {}).get("image_uri")),
        dry_run=config.dry_run,
    )
    results["steps"]["submit_job"] = submission_results

    state = _VertexJobState(
        job_id=submission_results.get("job_id"),
        run_id=submission_results.get("run_id"),
        model_uri=submission_results.get("model_uri"),
        resolved_model_prefix=results["configuration"]["model_prefix"],
        submission_results=submission_results,
    )

    submitted_prefix = submission_results.get("model_prefix")
    if submitted_prefix:
        state.resolved_model_prefix = submitted_prefix
        results["configuration"]["model_prefix"] = submitted_prefix

    if not state.job_id and not config.dry_run:
        logger.warning("Job ID not found - cannot monitor job")
        results["success"] = False
        results["error"] = "Job ID not extracted from submission"
        return None, True

    logger.info(f"Job submitted: {job_display_name}")
    logger.info(f"  Job ID: {state.job_id}")
    logger.info(f"  Run ID: {state.run_id}")
    logger.info(f"  Model will be saved to: {state.model_uri}")

    if config.dry_run:
        logger.info("DRY RUN: Stopping here (no actual job submitted)")
        results["success"] = True
        results["dry_run"] = True
        return None, True

    return state, False


def _resolve_artifacts_from_job_info(
    monitoring_results: dict, state: _VertexJobState, results: dict, logger: Logger
) -> None:
    """Recover the model URI and prefix from the job's worker pool spec when missing."""
    job_info = monitoring_results.get("job_info", {}) or {}
    job_spec = job_info.get("jobSpec", {}) or {}
    worker_specs = job_spec.get("workerPoolSpecs", []) or []

    for spec in worker_specs:
        container_spec = spec.get("containerSpec", {}) or {}
        args = container_spec.get("args", []) or []
        env_vars = container_spec.get("env", []) or []

        for idx, arg in enumerate(args):
            if arg == "--model-dir" and idx + 1 < len(args) and not state.model_uri:
                state.model_uri = args[idx + 1]
            if arg == "--model-prefix" and idx + 1 < len(args) and not state.resolved_model_prefix:
                state.resolved_model_prefix = args[idx + 1]

        if not state.model_uri:
            for env_var in env_vars:
                if env_var.get("name") == "MODEL_ARTIFACTS_URI":
                    state.model_uri = env_var.get("value")
                    break

        if state.model_uri and state.resolved_model_prefix:
            break

    if state.model_uri and not state.run_id:
        state.run_id = state.model_uri.rstrip("/").split("/")[-1]
        state.submission_results["run_id"] = state.run_id

    if not state.resolved_model_prefix and state.run_id:
        state.resolved_model_prefix = f"vertex-lgbm-{state.run_id}"

    if state.resolved_model_prefix:
        results["configuration"]["model_prefix"] = state.resolved_model_prefix
        state.submission_results["model_prefix"] = state.resolved_model_prefix
        logger.info(f"  Resolved model prefix: {state.resolved_model_prefix}")

    if state.model_uri:
        state.submission_results["model_uri"] = state.model_uri
        logger.info(f"  Resolved model URI: {state.model_uri}")


def _monitor_job_stage(
    config: TrainingFlowConfig, state: _VertexJobState, results: dict, logger: Logger
) -> None:
    """Stage 4: monitor the training job to completion and resolve artifact locations."""
    logger.info("STEP 4: Monitoring training job")
    logger.info("-" * 80)
    logger.info("Waiting for job to complete (this may take 10-30 minutes)...")

    monitoring_results = poll_vertex_job_status_task(
        job_id=state.job_id,
        region="europe-north1",
        poll_interval=30,
        stream_logs=config.stream_logs,
    )
    results["steps"]["monitor_job"] = monitoring_results

    duration_minutes = monitoring_results["duration_seconds"] / 60
    logger.info(f"Training completed in {duration_minutes:.1f} minutes")

    if not state.model_uri or not state.resolved_model_prefix:
        _resolve_artifacts_from_job_info(monitoring_results, state, results, logger)


def _download_artifacts_stage(
    config: TrainingFlowConfig, state: _VertexJobState, results: dict, logger: Logger
) -> bool:
    """Stage 5: download model artifacts from GCS.

    Returns True when the flow should return early (model URI unavailable).
    """
    logger.info("STEP 5: Downloading model artifacts from GCS")
    logger.info("-" * 80)

    if not state.model_uri:
        logger.error("Model URI not available - cannot download artifacts")
        results["success"] = False
        results["error"] = "Model URI missing"
        return True

    download_results = download_model_artifacts_task(
        model_uri=state.model_uri,
        local_dir=Path(config.local_model_dir),
        model_prefix=state.resolved_model_prefix,
    )
    results["steps"]["download_artifacts"] = download_results

    artifacts = download_results.get("artifacts", {})
    logger.info(f"Downloaded {len(artifacts)} artifacts")
    for artifact_type, path in artifacts.items():
        logger.info(f"  - {artifact_type}: {path}")

    return False


def _promote_model_local_files(
    config: TrainingFlowConfig, state: _VertexJobState, logger: Logger
) -> None:
    """Copy versioned model files to production names so downstream tasks can find them."""
    import shutil

    local_dir = Path(config.local_model_dir)

    # Define file types to promote
    file_types = [
        "lgbm.joblib",
        "metrics_lgbm.json",
        "feature_context.json",
        "feature_importance.json",
    ]

    for file_type in file_types:
        versioned_file = local_dir / f"{state.resolved_model_prefix}_{file_type}"
        production_file = local_dir / f"{config.model_prefix}_{file_type}"

        # Skip if source and destination are the same file
        if versioned_file == production_file:
            logger.info(f"  Skipping {file_type}: already at production name")
            continue

        if versioned_file.exists():
            shutil.copy2(versioned_file, production_file)
            logger.info(f"  Local promotion: {versioned_file.name} → {production_file.name}")
        else:
            logger.warning(f"  Versioned file not found: {versioned_file}")


def _validate_and_promote_stage(
    config: TrainingFlowConfig, state: _VertexJobState, results: dict, logger: Logger
) -> None:
    """Stage 6: validate model performance and promote it to production when it passes."""
    logger.info("STEP 6: Validating model performance")
    logger.info("-" * 80)

    metrics_path = Path(config.local_model_dir) / f"{state.resolved_model_prefix}_metrics_lgbm.json"
    if not metrics_path.exists():
        logger.warning(f"Metrics file not found: {metrics_path}")
        results["validation_passed"] = False
        return

    validation_results = validate_model_performance_task(
        metrics_path=metrics_path, max_mae=config.max_mae, max_rmse=config.max_rmse
    )
    results["steps"]["validation"] = validation_results
    results["validation_passed"] = validation_results["validation_passed"]
    results["metrics"] = {
        "mae": validation_results["mae"],
        "rmse": validation_results.get("rmse"),
        "r2": validation_results.get("r2"),
    }

    if validation_results["validation_passed"]:
        logger.info("Model validation PASSED")

        logger.info("STEP 6b: Promoting validated model to production")
        logger.info("-" * 80)

        if not config.dry_run:
            try:
                promotion_results = promote_model_to_production_task(
                    model_uri=state.model_uri,
                )
                results["steps"]["promotion"] = promotion_results
                logger.info(f"Promoted to: {promotion_results['production_path']}")

                # Also promote locally: copy versioned files to production names
                # This ensures that downstream tasks (like generate_value_analysis_task)
                # can find the model files with production names
                _promote_model_local_files(config, state, logger)

            except Exception as e:
                logger.warning(f"Model promotion failed: {e}")
                logger.warning("   Model artifacts remain in timestamped location")
        else:
            logger.info("[DRY RUN] Would promote model to production names")
    else:
        logger.warning("Model validation FAILED")
        for reason in validation_results.get("reasons", []):
            logger.warning(f"  - {reason}")
        logger.warning("   Skipping model promotion - validation did not pass")


def _generate_enrichment_stage(config: TrainingFlowConfig, results: dict, logger: Logger) -> None:
    """Stage 7: generate and upload enrichment data for the web app (non-critical)."""
    logger.info("STEP 7: Generating enrichment data for web app")
    logger.info("-" * 80)

    try:
        from estate_value_index.pipelines.tasks import (
            generate_area_statistics_task,
            generate_value_analysis_task,
            upload_enrichment_to_gcs_task,
        )

        # Generate area statistics
        area_stats_result = generate_area_statistics_task(
            output_file=Path("data/enrichment/area_statistics.json"),
            data_source="bigquery",
            feature_context_path=Path(config.local_model_dir)
            / f"{config.model_prefix}_feature_context.json",
            value_analysis_path=Path("data/enrichment/value_analysis.json"),
            raw_listings_path=Path("data/raw/booli/booli_listings_prod.json"),
        )
        results["steps"]["area_statistics"] = area_stats_result
        logger.info(
            f"Generated statistics for {area_stats_result.get('records_generated', 0)} areas"
        )

        # Generate value analysis (property predictions)
        value_analysis_result = generate_value_analysis_task(
            output_file=Path("data/enrichment/value_analysis.json"),
            data_file=Path("data/raw/booli/booli_listings_prod.json"),
            model_type="lgbm",
            apply_training_filters=False,
        )
        results["steps"]["value_analysis"] = value_analysis_result
        logger.info(
            f"Generated value analysis for {value_analysis_result.get('records_generated', 0)} properties"
        )

        # Upload enrichment data to GCS (for Cloud Run to access)
        enrichment_upload_result = upload_enrichment_to_gcs_task(
            local_dir=Path("data/enrichment"),
            gcs_bucket=get_gcs_bucket(),
            gcs_prefix="enrichment/",
        )
        results["steps"]["enrichment_upload"] = enrichment_upload_result
        logger.info(
            f"Uploaded {enrichment_upload_result.get('uploaded_files', 0)} enrichment files to GCS"
        )

    except Exception as e:
        logger.warning(f"Enrichment generation failed (non-critical): {e}")
        results["steps"]["enrichment"] = {"error": str(e)}


def _register_model_stage(
    config: TrainingFlowConfig, state: _VertexJobState, results: dict, logger: Logger
) -> None:
    """Stage 8: optionally register the validated model to the Vertex AI Model Registry."""
    if config.register_to_vertex and results.get("validation_passed", False):
        logger.info("STEP 8: Registering model to Vertex AI Model Registry")
        logger.info("-" * 80)

        registry_results = register_model_to_vertex_task(
            model_uri=state.model_uri, display_name=f"lgbm-{state.run_id}", region="europe-north1"
        )
        results["steps"]["register_model"] = registry_results

        logger.info(f"Model registered: {registry_results.get('model_resource_name')}")
    else:
        if config.register_to_vertex:
            logger.info("STEP 8: Skipping model registration (validation failed)")
            results["steps"]["register_model"] = {
                "skipped": True,
                "reason": "validation_failed",
            }
        else:
            logger.info("STEP 8: Skipping model registration (not requested)")
            results["steps"]["register_model"] = {"skipped": True, "reason": "user_skip"}


def _finalize_results(flow_start_time: datetime, results: dict, logger: Logger) -> dict:
    """Stage: record final timing and log the success summary."""
    flow_end_time = datetime.now()
    flow_duration = (flow_end_time - flow_start_time).total_seconds()

    results["success"] = True
    results["end_time"] = flow_end_time.isoformat()
    results["duration_seconds"] = flow_duration
    results["duration_minutes"] = flow_duration / 60

    logger.info("=" * 80)
    logger.info("VERTEX AI TRAINING PIPELINE COMPLETED SUCCESSFULLY")
    logger.info("=" * 80)
    logger.info(f"Total Duration: {flow_duration / 60:.1f} minutes")
    logger.info(f"Validation: {'PASSED' if results.get('validation_passed') else 'FAILED'}")

    if results.get("metrics"):
        metrics = results["metrics"]
        logger.info("Model Performance:")
        logger.info(f"  MAE: {metrics.get('mae', 0):,.0f} SEK")
        if metrics.get("rmse"):
            logger.info(f"  RMSE: {metrics.get('rmse', 0):,.0f} SEK")
        if metrics.get("r2"):
            logger.info(f"  R²: {metrics.get('r2', 0):.4f}")

    logger.info("=" * 80)

    return results


@flow(name="Estate Value Index Vertex AI Training Pipeline", log_prints=True)
def vertex_training_flow(config: TrainingFlowConfig | None = None) -> dict:
    """
    Complete ML training pipeline with Vertex AI integration.

    This flow orchestrates:
    - Feature materialization in BigQuery
    - Optional container rebuilding
    - Vertex AI training job submission and monitoring
    - Model artifact download and validation
    - Optional model registry registration

    Args:
        config: Training configuration. If None, uses defaults.

    Returns:
        Dict with flow results, metrics, and artifact locations
    """
    if config is None:
        config = TrainingFlowConfig()

    logger = get_run_logger()
    _log_flow_configuration(config, logger)

    flow_start_time = datetime.now()
    results = {
        "use_vertex": config.use_vertex,
        "configuration": {
            "tune": config.tune,
            "machine_type": config.machine_type,
            "importance_threshold": config.importance_threshold,
            "max_mae": config.max_mae,
        },
        "steps": {},
        "start_time": flow_start_time.isoformat(),
    }
    results["configuration"]["model_prefix"] = config.model_prefix

    try:
        if not config.use_vertex:
            return _run_local_training(config, results, logger)

        _materialize_features_stage(config, results, logger)
        _rebuild_container_stage(config, results, logger)

        state, should_return = _submit_training_job_stage(config, results, logger)
        if should_return:
            return results

        _monitor_job_stage(config, state, results, logger)

        if _download_artifacts_stage(config, state, results, logger):
            return results

        _validate_and_promote_stage(config, state, results, logger)
        _generate_enrichment_stage(config, results, logger)
        _register_model_stage(config, state, results, logger)

        return _finalize_results(flow_start_time, results, logger)

    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"PIPELINE FAILED: {e}")
        logger.error("=" * 80)

        results["success"] = False
        results["error"] = str(e)
        results["end_time"] = datetime.now().isoformat()

        raise


@flow(name="Estate Value Index Vertex AI Training - Quick Run")
def quick_vertex_training_flow(tune: bool = False) -> dict:
    """
    Simplified flow for quick training runs.

    Uses sensible defaults:
    - Small machine (n1-standard-4)
    - No container rebuild
    - No model registry
    - Stream logs enabled

    Args:
        tune: Enable hyperparameter tuning

    Returns:
        Training results dict
    """
    config = TrainingFlowConfig(
        tune=tune,
        machine_type="n1-standard-4",
        rebuild_container=False,
        skip_materialization=False,
        register_to_vertex=False,
        stream_logs=True,
        use_vertex=True,
    )
    return vertex_training_flow(config)


@flow(name="Estate Value Index Vertex AI Training - Production Run")
def production_vertex_training_flow(rebuild: bool = False, register: bool = True) -> dict:
    """
    Production flow with full validation and registration.

    Features:
    - Hyperparameter tuning enabled
    - Standard machine (n1-standard-4)
    - Optional container rebuild
    - Model registry registration
    - Strict validation thresholds

    Args:
        rebuild: Rebuild container before training
        register: Register to Vertex AI Model Registry

    Returns:
        Training results dict
    """
    config = TrainingFlowConfig(
        tune=True,
        machine_type="n1-standard-4",
        rebuild_container=rebuild,
        skip_materialization=False,
        register_to_vertex=register,
        stream_logs=True,
        use_vertex=True,
        max_mae=255000,  # Strict threshold matching current best
    )
    return vertex_training_flow(config)


if __name__ == "__main__":
    import sys

    # Simple CLI for testing
    if len(sys.argv) > 1 and sys.argv[1] == "--dry-run":
        print("Running in DRY RUN mode...")
        config = TrainingFlowConfig(tune=False, dry_run=True, use_vertex=True)
        result = vertex_training_flow(config)
    elif len(sys.argv) > 1 and sys.argv[1] == "--local":
        print("Running LOCAL training...")
        config = TrainingFlowConfig(tune=False, use_vertex=False)
        result = vertex_training_flow(config)
    elif len(sys.argv) > 1 and sys.argv[1] == "--quick":
        print("Running QUICK Vertex AI training...")
        result = quick_vertex_training_flow(tune=False)
    elif len(sys.argv) > 1 and sys.argv[1] == "--production":
        print("Running PRODUCTION Vertex AI training...")
        result = production_vertex_training_flow(rebuild=False, register=False)
    else:
        print("Running STANDARD Vertex AI training...")
        config = TrainingFlowConfig(tune=False, machine_type="n1-standard-4", use_vertex=True)
        result = vertex_training_flow(config)

    # Print results
    print("\n" + "=" * 80)
    print("FLOW RESULTS")
    print("=" * 80)
    print(json.dumps(result, indent=2, default=str))
