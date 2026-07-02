"""Tasks for ML training: feature materialization, Vertex AI jobs, model management."""

import json
import logging
import os
import re
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Final

from prefect import task

from estate_value_index.pipelines.constants import DEFAULT_MAE_THRESHOLD
from estate_value_index.pipelines.types import (
    MaterializationResult,
    ValidationResult,
    VertexJobResult,
)
from estate_value_index.pipelines.utils import get_task_logger, run_command
from estate_value_index.utils.gcs import get_gcs_bucket

# Vertex AI job state strings that mean "done, stop polling". Mirrors
# `google.cloud.aiplatform_v1.types.JobState` without forcing the SDK import.
_TERMINAL_JOB_STATES: Final[frozenset[str]] = frozenset(
    {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED"}
)
_JOB_STATE_SUCCEEDED: Final[str] = "JOB_STATE_SUCCEEDED"
_CUSTOM_JOB_RE: Final[re.Pattern[str]] = re.compile(
    r"(projects/[\w-]+/locations/[\w-]+/customJobs/\d+)"
)
_RUN_ID_RE: Final[re.Pattern[str]] = re.compile(r"Run ID:\s*([\d-]+)")
_TIMESTAMP_RE: Final[re.Pattern[str]] = re.compile(r"(\d{8}-\d{6})")
_MODEL_URI_RE: Final[re.Pattern[str]] = re.compile(r"(gs://[\w-]+/vertex-ai/models/[\w-]+)")
_OUTPUT_URI_RE: Final[re.Pattern[str]] = re.compile(r"(gs://[\w-]+/vertex-ai/jobs/[\w-]+)")

# --- Helper functions for complex tasks ---


def _output_lines(stdout: str, stderr: str) -> list[str]:
    return stdout.split("\n") + stderr.split("\n")


def _search_line(pattern: re.Pattern[str], line: str) -> str | None:
    match = pattern.search(line)
    return match.group(1) if match else None


def _job_id_from_line(line: str) -> str | None:
    if "customJobs" not in line:
        return None
    return _search_line(_CUSTOM_JOB_RE, line)


def _explicit_run_id_from_line(line: str) -> str | None:
    if "Run ID:" not in line:
        return None
    return _search_line(_RUN_ID_RE, line)


def _run_id_from_model_line(line: str) -> str | None:
    if "models/" not in line or "gs://" not in line:
        return None
    return _search_line(_TIMESTAMP_RE, line)


def _model_uri_from_line(line: str) -> str | None:
    if "gs://" not in line or "models/" not in line:
        return None
    return _search_line(_MODEL_URI_RE, line)


def _output_uri_from_line(line: str) -> str | None:
    if "gs://" not in line or "jobs/" not in line:
        return None
    return _search_line(_OUTPUT_URI_RE, line)


def _parse_vertex_job_output(stdout: str, stderr: str) -> VertexJobResult:
    """Parse job information from Vertex AI submission output."""
    job_id = None
    run_id = None
    model_uri = None
    output_uri = None

    for line in _output_lines(stdout, stderr):
        job_id = _job_id_from_line(line) or job_id
        run_id = _explicit_run_id_from_line(line) or run_id
        if not run_id:
            run_id = _run_id_from_model_line(line)
        model_uri = _model_uri_from_line(line) or model_uri
        output_uri = _output_uri_from_line(line) or output_uri

    if model_uri and not run_id:
        run_id = model_uri.rstrip("/").split("/")[-1]

    return VertexJobResult(
        success=True,
        timestamp=datetime.now().isoformat(),
        job_id=job_id,
        run_id=run_id,
        model_uri=model_uri,
        output_uri=output_uri,
    )


def _get_job_state(job_id: str, region: str) -> str:
    """Get current state of a Vertex AI job."""
    result = subprocess.run(
        [
            "gcloud",
            "ai",
            "custom-jobs",
            "describe",
            job_id,
            "--region",
            region,
            "--format",
            "value(state)",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return result.stdout.strip()


def _stream_logs_background(job_id: str, region: str, stop_event: threading.Event):
    """Stream job logs in background thread."""
    log = logging.getLogger(__name__)
    try:
        subprocess.run(
            ["gcloud", "ai", "custom-jobs", "stream-logs", job_id, "--region", region],
            capture_output=False,
            timeout=3600,
            check=False,
        )
    except Exception as exc:
        log.warning("Vertex log stream ended early for %s: %s", job_id, exc)
    finally:
        stop_event.set()


# --- Tasks ---


@task(name="materialize-features", retries=2, retry_delay_seconds=30)
def materialize_features_task(truncate: bool = True) -> MaterializationResult:
    """Materialize engineered features in BigQuery."""
    logger = get_task_logger(__name__)
    logger.info("Materializing features in BigQuery")

    from estate_value_index.ml.feature_materialization import materialize_features

    result = materialize_features(
        project_id=None,
        dry_run=False,
        truncate=truncate,
        batch_size=None,
    )

    if result:
        row_count = result.get("row_count")
        if result.get("dry_run", False):
            logger.info(f"Features computed (dry_run): {row_count} rows prepared")
        else:
            logger.info(f"Features materialized: {row_count} rows")
    else:
        row_count = None
        logger.warning("Feature materialization returned no result")

    return MaterializationResult(
        success=True,
        timestamp=datetime.now().isoformat(),
        row_count=row_count,
    )


@task(name="rebuild-container", retries=1, retry_delay_seconds=60, timeout_seconds=900)
def rebuild_container_task(
    image_name: str = "lgbm-trainer",
    image_tag: str = "latest",
    dry_run: bool = False,
) -> dict:
    """Rebuild and push training container to Artifact Registry.

    Args:
        image_name: Container image name
        image_tag: Container tag
        dry_run: If True, only show command without executing

    Returns:
        Dict with image URI and build info
    """
    logger = get_task_logger(__name__)
    logger.info(f"Rebuilding container: {image_name}:{image_tag}")

    cmd = ["./scripts/vertex_ai/build_and_push.sh", "--image", image_name, "--tag", image_tag]
    if dry_run:
        cmd.append("--dry-run")

    result = run_command(cmd, "Container build", timeout=900)

    # Parse image URI from output
    image_uri = None
    build_id = None
    for line in result.stdout.split("\n"):
        if "docker.pkg.dev" in line:
            match = re.search(r"([\w-]+\.pkg\.dev/[\w-]+/[\w-]+/[\w-]+:[\w.-]+)", line)
            if match:
                image_uri = match.group(1)
        if "ID:" in line or "Build ID:" in line:
            match = re.search(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", line)
            if match:
                build_id = match.group(0)

    logger.info(f"Container built: {image_uri}")

    return {
        "success": True,
        "image_uri": image_uri,
        "build_id": build_id,
        "timestamp": datetime.now().isoformat(),
    }


@task(name="submit-vertex-training-job", retries=2, retry_delay_seconds=60, timeout_seconds=120)
def submit_vertex_training_job_task(
    tune: bool = False,
    machine_type: str = "n1-standard-4",
    importance_threshold: float | None = None,
    production_mode: bool = True,
    display_name: str | None = None,
    image_uri: str | None = None,
    dry_run: bool = False,
) -> VertexJobResult:
    """Submit training job to Vertex AI.

    Args:
        tune: Enable hyperparameter tuning
        machine_type: GCP machine type
        importance_threshold: Feature importance threshold
        production_mode: Enable production mode (retrain on all data)
        display_name: Custom job display name
        dry_run: If True, only show command without submitting

    Returns:
        VertexJobResult with job_id, run_id, model_uri
    """
    logger = get_task_logger(__name__)
    logger.info(f"Submitting Vertex AI job (tune={tune}, machine={machine_type})")

    cmd = ["./scripts/vertex_ai/submit_custom_job.sh", "--machine-type", machine_type]
    if image_uri:
        cmd.extend(["--image-uri", image_uri])
    if tune:
        cmd.append("--tune")
    if display_name:
        cmd.extend(["--display-name", display_name])
    if dry_run:
        cmd.append("--dry-run")

    extra_args = []
    if importance_threshold is not None:
        extra_args.extend(["--importance-threshold", str(importance_threshold)])
    if production_mode:
        extra_args.append("--production-mode")
    if extra_args:
        cmd.extend(["--"] + extra_args)

    env = os.environ.copy()
    env["GCP_REGION"] = "europe-north1"

    result = subprocess.run(
        cmd,
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=env,
    )

    if result.returncode != 0:
        logger.error(f"Job submission failed: {result.stderr}")
        raise RuntimeError(f"Job submission failed with code {result.returncode}")

    job_result = _parse_vertex_job_output(result.stdout, result.stderr)
    logger.info(f"Job submitted: {job_result['job_id']}")

    return job_result


@task(name="poll-vertex-job-status", retries=0, timeout_seconds=3600)
def poll_vertex_job_status_task(
    job_id: str,
    region: str = "europe-north1",
    poll_interval: int = 30,
    stream_logs: bool = True,
) -> dict:
    """Poll Vertex AI job status until completion.

    Args:
        job_id: Full job resource name
        region: GCP region
        poll_interval: Seconds between status checks
        stream_logs: If True, stream logs during training

    Returns:
        Dict with final state, duration, and completion info
    """
    logger = get_task_logger(__name__)
    logger.info(f"Monitoring job: {job_id}")

    if not job_id:
        raise ValueError("job_id is required")

    start_time = time.time()
    log_stop_event = threading.Event()

    if stream_logs:
        log_thread = threading.Thread(
            target=_stream_logs_background,
            args=(job_id, region, log_stop_event),
            daemon=True,
        )
        log_thread.start()

    # Poll for completion
    while True:
        state = _get_job_state(job_id, region)
        if state in _TERMINAL_JOB_STATES:
            logger.info(f"Job reached terminal state: {state}")
            break
        time.sleep(poll_interval)

    if stream_logs:
        log_stop_event.wait(timeout=10)
        # Grace period for Vertex AI cleanup
        time.sleep(60)

    # Get final job info
    result = subprocess.run(
        [
            "gcloud",
            "ai",
            "custom-jobs",
            "describe",
            job_id,
            "--region",
            region,
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )

    job_info = json.loads(result.stdout)
    final_state = job_info.get("state", "UNKNOWN")
    duration = time.time() - start_time

    logger.info(f"Job completed: {final_state} ({duration / 60:.1f}m)")

    if final_state != _JOB_STATE_SUCCEEDED:
        error_info = job_info.get("error", {})
        logger.error(f"Job failed: {error_info}")
        raise RuntimeError(f"Training job failed with state: {final_state}")

    return {
        "success": True,
        "state": final_state,
        "duration_seconds": duration,
        "job_info": job_info,
        "timestamp": datetime.now().isoformat(),
    }


@task(name="download-model-artifacts", retries=3, retry_delay_seconds=30, timeout_seconds=300)
def download_model_artifacts_task(
    model_uri: str,
    local_dir: Path = Path("web/models"),
    model_prefix: str = "price_prediction_model",
) -> dict:
    """Download trained model artifacts from GCS.

    Args:
        model_uri: GCS URI to model directory
        local_dir: Local directory to save artifacts
        model_prefix: Expected model filename prefix

    Returns:
        Dict mapping artifact type to local path
    """
    logger = get_task_logger(__name__)
    logger.info(f"Downloading model artifacts from {model_uri}")

    if not model_uri or not model_uri.startswith("gs://"):
        raise ValueError(f"Invalid model_uri: {model_uri}")

    import platform

    local_dir = Path(local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)

    # MacOS fix for gsutil multiprocessing bug
    is_macos = platform.system() == "Darwin"
    gsutil_opts = ["-o", "GSUtil:parallel_process_count=1"] if is_macos else []

    cmd = ["gsutil"] + gsutil_opts + ["-m", "cp", "-r", f"{model_uri}/*", str(local_dir)]
    run_command(cmd, "GCS download", timeout=300)

    # Verify downloaded files
    artifacts = {}
    expected_files = [
        f"{model_prefix}_lgbm.joblib",
        f"{model_prefix}_metrics_lgbm.json",
        f"{model_prefix}_feature_context.json",
        f"{model_prefix}_feature_importance.json",
    ]

    for filename in expected_files:
        file_path = local_dir / filename
        if file_path.exists():
            key = filename.split("_")[-1].replace(".json", "").replace(".joblib", "")
            artifacts[key] = str(file_path)
            logger.info(f"Found: {filename}")

    if not artifacts:
        raise FileNotFoundError(f"No model artifacts found in {local_dir}")

    logger.info(f"Downloaded {len(artifacts)} artifacts to {local_dir}")

    return {
        "success": True,
        "artifacts": artifacts,
        "local_dir": str(local_dir),
        "timestamp": datetime.now().isoformat(),
    }


@task(name="validate-model-performance", retries=0, timeout_seconds=60)
def validate_model_performance_task(
    metrics_path: Path,
    max_mae: float = DEFAULT_MAE_THRESHOLD,
    max_rmse: float | None = None,
) -> ValidationResult:
    """Validate model performance against thresholds.

    Args:
        metrics_path: Path to metrics JSON file
        max_mae: Maximum acceptable MAE
        max_rmse: Optional maximum acceptable RMSE

    Returns:
        ValidationResult with validation status and metrics
    """
    logger = get_task_logger(__name__)
    logger.info(f"Validating model performance from {metrics_path}")

    with open(metrics_path) as f:
        metrics = json.load(f)

    mae = metrics.get("mae")
    rmse = metrics.get("rmse")
    r2 = metrics.get("r2")

    if mae is None:
        raise ValueError("MAE not found in metrics file")

    rmse_str = f"{rmse:,.0f}" if rmse else "N/A"
    r2_str = f"{r2:.4f}" if r2 else "N/A"
    logger.info(f"Model metrics: MAE={mae:,.0f}, RMSE={rmse_str}, R2={r2_str}")

    validation_passed = True
    reasons: list[str] = []

    if mae > max_mae:
        validation_passed = False
        reasons.append(f"MAE ({mae:,.0f}) exceeds threshold ({max_mae:,.0f})")

    if max_rmse and rmse and rmse > max_rmse:
        validation_passed = False
        reasons.append(f"RMSE ({rmse:,.0f}) exceeds threshold ({max_rmse:,.0f})")

    if validation_passed:
        logger.info("Model validation passed")
    else:
        logger.warning(f"Model validation failed: {'; '.join(reasons)}")

    return ValidationResult(
        success=True,
        timestamp=datetime.now().isoformat(),
        validation_passed=validation_passed,
        mae=mae,
        rmse=rmse or 0.0,
        reasons=reasons,
    )


@task(name="promote-model-to-production", retries=2, retry_delay_seconds=30, timeout_seconds=300)
def promote_model_to_production_task(
    model_uri: str,
    gcs_bucket: str | None = None,
    production_prefix: str = "price_prediction_model",
) -> dict:
    """Promote validated model artifacts to production names in GCS.

    Args:
        model_uri: GCS URI to model directory
        gcs_bucket: GCS bucket name
        production_prefix: Production model filename prefix

    Returns:
        Dict with promotion status and production URIs
    """
    logger = get_task_logger(__name__)
    logger.info(f"Promoting model to production: {model_uri}")

    if not model_uri or not model_uri.startswith("gs://"):
        raise ValueError(f"Invalid model_uri: {model_uri}")

    gcs_bucket = gcs_bucket or get_gcs_bucket()

    import platform

    # Extract timestamp from model_uri
    match = re.search(r"/(\d{8}-\d{6})/?$", model_uri.rstrip("/"))
    if not match:
        raise ValueError(f"Could not extract timestamp from model_uri: {model_uri}")

    timestamp = match.group(1)
    vertex_prefix = f"vertex-lgbm-{timestamp}"

    is_macos = platform.system() == "Darwin"
    gsutil_opts = ["-o", "GSUtil:parallel_process_count=1"] if is_macos else []

    artifact_types = [
        "lgbm.joblib",
        "feature_context.json",
        "metrics_lgbm.json",
        "feature_importance.json",
    ]
    production_path = f"gs://{gcs_bucket}/models"
    promoted_files = []

    for artifact in artifact_types:
        source = f"{model_uri.rstrip('/')}/{vertex_prefix}_{artifact}"
        dest = f"{production_path}/{production_prefix}_{artifact}"

        cmd = ["gsutil"] + gsutil_opts + ["cp", source, dest]
        run_command(cmd, f"Copy {artifact}", timeout=60)
        promoted_files.append(dest)
        logger.info(f"Promoted: {artifact}")

    logger.info(f"Promoted {len(promoted_files)} artifacts to production")

    return {
        "success": True,
        "promoted_files": promoted_files,
        "production_path": production_path,
        "timestamp": datetime.now().isoformat(),
    }


@task(name="register-model-to-vertex", retries=2, retry_delay_seconds=60, timeout_seconds=300)
def register_model_to_vertex_task(
    model_uri: str,
    display_name: str = "lgbm-vertex",
    container_image_uri: str | None = None,
    region: str = "europe-north1",
) -> dict:
    """Register model to Vertex AI Model Registry.

    Args:
        model_uri: GCS URI to model artifacts
        display_name: Model display name
        container_image_uri: Optional serving container image
        region: GCP region

    Returns:
        Dict with model resource name and info
    """
    logger = get_task_logger(__name__)
    logger.info(f"Registering model to Vertex AI: {display_name}")

    cmd = [
        "gcloud",
        "ai",
        "models",
        "upload",
        "--display-name",
        display_name,
        "--artifact-uri",
        model_uri,
        "--region",
        region,
    ]
    if container_image_uri:
        cmd.extend(["--container-image-uri", container_image_uri])

    result = run_command(cmd, "Model registration", timeout=300)

    model_resource_name = None
    for line in result.stdout.split("\n"):
        if "projects/" in line and "models/" in line:
            match = re.search(r"(projects/[\w-]+/locations/[\w-]+/models/\d+)", line)
            if match:
                model_resource_name = match.group(1)

    logger.info(f"Model registered: {model_resource_name}")

    return {
        "success": True,
        "model_resource_name": model_resource_name,
        "display_name": display_name,
        "timestamp": datetime.now().isoformat(),
    }
