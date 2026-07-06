"""Tasks for Cloud Run deployment, health checks, and monitoring."""

import json
import os
import subprocess
import time
from datetime import datetime
from logging import Logger
from pathlib import Path

import requests
from prefect import task

from estate_value_index.pipelines.types import DeploymentResult, HealthCheckResult
from estate_value_index.pipelines.utils import get_task_logger
from estate_value_index.utils.clients import get_bq_client, get_storage_client
from estate_value_index.utils.gcs import get_gcs_bucket

# --- Helper functions ---


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} environment variable is required")
    return value


def _runtime_service_account(project_id: str) -> str:
    return os.getenv(
        "CLOUD_RUN_RUNTIME_SERVICE_ACCOUNT",
        os.getenv(
            "RUNTIME_SERVICE_ACCOUNT",
            f"evi-cloud-run-runtime@{project_id}.iam.gserviceaccount.com",
        ),
    )


def _cloud_run_env_vars(gcs_bucket: str) -> str:
    return ",".join(
        [
            "GCS_ENABLED=true",
            f"GCS_BUCKET={gcs_bucket}",
            "NODE_ENV=production",
            "PREDICTION_API_URL=http://127.0.0.1:8000",
            "TRUST_PROXY_HEADERS=true",
        ]
    )


def _describe_service(
    service_name: str,
    region: str,
    field: str,
    project_id: str | None = None,
) -> str | None:
    """Run `gcloud run services describe ... --format value(<field>)` and return the value.

    This runs at deployment time where any gcloud/subprocess failure should
    fall back to "no info" rather than crash the pipeline.
    """
    try:
        cmd = [
            "gcloud",
            "run",
            "services",
            "describe",
            service_name,
            "--region",
            region,
            "--format",
            f"value({field})",
        ]
        if project_id:
            cmd.extend(["--project", project_id])
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _get_current_revision(
    service_name: str,
    region: str,
    project_id: str | None = None,
) -> str | None:
    """Get the currently serving revision."""
    return _describe_service(service_name, region, "status.latestReadyRevisionName", project_id)


def _get_service_url(
    service_name: str,
    region: str,
    project_id: str | None = None,
) -> str | None:
    """Get the service URL."""
    return _describe_service(service_name, region, "status.url", project_id)


def _get_service_ingress(
    service_name: str,
    region: str,
    project_id: str | None = None,
) -> str | None:
    """Get the service ingress setting (all, internal, internal-and-cloud-load-balancing)."""
    return _describe_service(
        service_name,
        region,
        'metadata.annotations."run.googleapis.com/ingress"',
        project_id,
    )


def _revision_ready(
    service_name: str,
    region: str,
    project_id: str | None = None,
) -> bool:
    """Platform readiness: the latest created revision is also the latest ready one."""
    created = _describe_service(
        service_name, region, "status.latestCreatedRevisionName", project_id
    )
    ready = _describe_service(service_name, region, "status.latestReadyRevisionName", project_id)
    return created is not None and created == ready


def _validate_deployment(
    logger: Logger,
    service_name: str,
    region: str,
    project_id: str,
    service_url: str | None,
) -> bool | None:
    """Post-deploy validation. Warning-only: a failed check never fails the deploy.

    The service is deployed with internal ingress, so an unauthenticated
    external probe from the runner always hits a Google Frontend 404. For
    anything but public ingress ("all"), use Cloud Run's own revision
    readiness (gcloud run services describe) instead of an HTTP probe.

    Returns True when the check passed, False when it failed after retries,
    None when it was skipped. The caller records this in DeploymentResult so
    flows can act on it (auto-rollback); it never raises.
    """
    # Deploy always sets --ingress internal; if the lookup fails, assume internal.
    ingress = _get_service_ingress(service_name, region, project_id) or "internal"

    if ingress != "all":
        logger.info("External health check skipped: internal ingress, platform readiness used")
        for attempt in range(3):
            if attempt:
                time.sleep(10)
            if _revision_ready(service_name, region, project_id):
                logger.info("Platform readiness check passed")
                return True
        logger.warning("Platform readiness check failed: latest revision not ready")
        return False

    if not service_url:
        logger.warning("No service URL available - skipping health check")
        return None

    # Retry health check while the Cloud Run revision warms up
    for attempt in range(3):
        try:
            health_result = health_check_task(f"{service_url}/api/health")
            if health_result["healthy"]:
                logger.info("Health check passed")
                return True
        except Exception as e:
            logger.warning(f"Health check attempt {attempt + 1} failed: {e}")
        time.sleep(10)
    logger.warning("Health check did not pass after 3 attempts")
    return False


def _assert_runtime_service_account_exists(runtime_service_account: str) -> None:
    result = subprocess.run(
        [
            "gcloud",
            "iam",
            "service-accounts",
            "describe",
            runtime_service_account,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Cloud Run runtime service account not found: "
            f"{runtime_service_account}. Create it with scripts/setup_gcp.sh or set "
            "CLOUD_RUN_RUNTIME_SERVICE_ACCOUNT to a GCS-read-only runtime account."
        )


# --- Tasks ---


@task(
    name="deploy-to-cloud-run",
    description="Deploy to Cloud Run",
    retries=2,
    retry_delay_seconds=30,
    timeout_seconds=1800,
)
def deploy_to_cloud_run_task(
    model_artifacts_gcs_uri: str,
    enrichment_gcs_uri: str,
    service_name: str | None = None,
    region: str | None = None,
    validate: bool = True,
    dry_run: bool = False,
) -> DeploymentResult:
    """Deploy new model to Cloud Run.

    Args:
        model_artifacts_gcs_uri: GCS URI for model artifacts
        enrichment_gcs_uri: GCS URI for enrichment data
        service_name: Cloud Run service name
        region: GCP region
        validate: Run health check after deployment
        dry_run: Simulate without actual deployment

    Returns:
        DeploymentResult with deployment status
    """
    logger = get_task_logger(__name__)

    service_name = service_name or os.getenv("CLOUD_RUN_SERVICE_NAME", "estate-value-index-app")
    region = region or os.getenv("CLOUD_RUN_REGION") or os.getenv("GCP_REGION", "europe-north1")
    project_id = _require_env("GCP_PROJECT_ID")

    logger.info(f"Deploying to Cloud Run: {service_name} in {region}")

    if dry_run:
        return DeploymentResult(
            success=True,
            timestamp=datetime.now().isoformat(),
            service_url=None,
            revision=None,
            previous_revision=None,
            healthy=None,
        )

    gcs_bucket = get_gcs_bucket()
    runtime_service_account = _runtime_service_account(project_id)
    current_revision = _get_current_revision(service_name, region, project_id)
    _assert_runtime_service_account_exists(runtime_service_account)

    deploy_cmd = [
        "gcloud",
        "run",
        "deploy",
        service_name,
        "--source",
        ".",
        "--region",
        region,
        "--platform",
        "managed",
        "--service-account",
        runtime_service_account,
        "--allow-unauthenticated",
        "--project",
        project_id,
        "--port",
        "8080",
        "--timeout",
        "900s",
        "--memory",
        "1Gi",
        "--cpu",
        "1",
        "--min-instances",
        "0",
        "--max-instances",
        "2",
        "--ingress",
        "internal",
        "--set-env-vars",
        _cloud_run_env_vars(gcs_bucket),
        "--quiet",
    ]

    result = subprocess.run(
        deploy_cmd,
        capture_output=True,
        text=True,
        timeout=1800,
        cwd=Path.cwd(),
    )

    if result.returncode != 0:
        logger.error(f"Deployment failed: {result.stderr}")
        raise RuntimeError(f"Cloud Run deployment failed: {result.stderr}")

    time.sleep(30)  # Wait for Cloud Run supervisor to start all services

    service_url = _get_service_url(service_name, region, project_id)
    new_revision = _get_current_revision(service_name, region, project_id)

    logger.info(f"Deployment complete: {current_revision} -> {new_revision}")

    healthy = None
    if validate:
        healthy = _validate_deployment(logger, service_name, region, project_id, service_url)

    return DeploymentResult(
        success=True,
        timestamp=datetime.now().isoformat(),
        service_url=service_url,
        revision=new_revision,
        previous_revision=current_revision,
        healthy=healthy,
    )


@task(
    name="rollback-deployment",
    description="Rollback to previous Cloud Run revision",
    retries=1,
    retry_delay_seconds=10,
    timeout_seconds=120,
)
def rollback_deployment_task(
    previous_revision: str,
    service_name: str | None = None,
    region: str | None = None,
) -> dict:
    """Rollback to previous Cloud Run revision.

    Args:
        previous_revision: Previous revision identifier
        service_name: Cloud Run service name
        region: GCP region

    Returns:
        Rollback result
    """
    logger = get_task_logger(__name__)

    service_name = service_name or os.getenv("CLOUD_RUN_SERVICE_NAME", "estate-value-index-app")
    region = region or os.getenv("CLOUD_RUN_REGION") or os.getenv("GCP_REGION", "europe-north1")
    project_id = _require_env("GCP_PROJECT_ID")

    logger.info(f"Rolling back {service_name} to {previous_revision}")

    current_revision = _get_current_revision(service_name, region, project_id)

    result = subprocess.run(
        [
            "gcloud",
            "run",
            "services",
            "update-traffic",
            service_name,
            "--to-revisions",
            f"{previous_revision}=100",
            "--region",
            region,
            "--project",
            project_id,
            "--quiet",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        logger.error(f"Rollback failed: {result.stderr}")
        raise RuntimeError(f"Rollback failed: {result.stderr}")

    active_revision = _get_current_revision(service_name, region, project_id)
    logger.info(f"Rolled back: {current_revision} -> {previous_revision}")

    return {
        "success": True,
        "from_revision": current_revision,
        "to_revision": previous_revision,
        "active_revision": active_revision,
        "timestamp": datetime.now().isoformat(),
    }


@task(
    name="health-check",
    description="Check if deployed service is healthy",
    retries=3,
    retry_delay_seconds=5,
    timeout_seconds=30,
)
def health_check_task(
    service_url: str,
    expected_status: int = 200,
    timeout: int = 10,
) -> HealthCheckResult:
    """Check if a deployed service is healthy.

    Args:
        service_url: Service URL to check
        expected_status: Expected HTTP status code
        timeout: Request timeout in seconds

    Returns:
        HealthCheckResult with health status
    """
    logger = get_task_logger(__name__)
    logger.info(f"Health check: {service_url}")

    start_time = time.time()

    try:
        response = requests.get(service_url, timeout=timeout, allow_redirects=True)
        response_time_ms = (time.time() - start_time) * 1000
        is_healthy = response.status_code == expected_status
        # 503 = degraded but service is running; treat as "alive" for deployment checks
        is_alive = response.status_code in (200, 503)

        if is_healthy:
            logger.info(f"Healthy (status={response.status_code}, time={response_time_ms:.0f}ms)")
        elif is_alive:
            logger.info(
                f"Degraded but alive (status={response.status_code}, time={response_time_ms:.0f}ms)"
            )
        else:
            logger.warning(f"Unhealthy (status={response.status_code})")

        return HealthCheckResult(
            success=True,
            timestamp=datetime.now().isoformat(),
            healthy=is_alive,  # Consider alive services as healthy for deployment purposes
            status_code=response.status_code,
            response_time_ms=round(response_time_ms, 2),
        )

    except requests.exceptions.Timeout:
        logger.error(f"Health check timed out after {timeout}s")
        return HealthCheckResult(
            success=False,
            timestamp=datetime.now().isoformat(),
            healthy=False,
            status_code=None,
            response_time_ms=None,
        )

    except requests.exceptions.RequestException as e:
        logger.error(f"Health check failed: {e}")
        return HealthCheckResult(
            success=False,
            timestamp=datetime.now().isoformat(),
            healthy=False,
            status_code=None,
            response_time_ms=None,
        )


@task(
    name="log-metrics",
    description="Log pipeline metrics to GCS",
    retries=2,
    retry_delay_seconds=10,
    timeout_seconds=60,
)
def log_metrics_task(
    metrics: dict,
    destination: str = "gcs",
    gcs_bucket: str | None = None,
    gcs_prefix: str = "metrics/",
) -> dict:
    """Log pipeline metrics to GCS or local file.

    Args:
        metrics: Metrics dictionary to log
        destination: "gcs" or "local"
        gcs_bucket: GCS bucket name
        gcs_prefix: GCS prefix path

    Returns:
        Logging result
    """
    logger = get_task_logger(__name__)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"pipeline_metrics_{timestamp}.json"

    if destination == "gcs":
        try:
            bucket_name = gcs_bucket or get_gcs_bucket()
            client = get_storage_client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(f"{gcs_prefix}{filename}")
            blob.upload_from_string(
                json.dumps(metrics, indent=2, ensure_ascii=False),
                content_type="application/json",
            )

            logger.info(f"Metrics logged to gs://{bucket_name}/{gcs_prefix}{filename}")

            return {
                "success": True,
                "destination": "gcs",
                "uri": f"gs://{bucket_name}/{gcs_prefix}{filename}",
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.warning(f"GCS logging failed, falling back to local: {e}")
            destination = "local"

    # Local logging
    local_dir = Path("data/derived/metrics")
    local_dir.mkdir(parents=True, exist_ok=True)
    local_path = local_dir / filename

    with open(local_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)

    logger.info(f"Metrics logged to {local_path}")

    return {
        "success": True,
        "destination": "local",
        "path": str(local_path),
        "timestamp": datetime.now().isoformat(),
    }


@task(
    name="monitor-pipeline-health",
    description="Check overall pipeline health",
    retries=1,
    retry_delay_seconds=30,
    timeout_seconds=120,
)
def monitor_pipeline_health_task() -> dict:
    """Check overall pipeline health.

    Checks BigQuery table, model artifacts, and Cloud Run service.

    Returns:
        Health status with issues list
    """
    logger = get_task_logger(__name__)
    logger.info("Checking pipeline health")

    issues: list[str] = []
    checks: dict = {}

    project_id = _require_env("BIGQUERY_PROJECT_ID")

    # Check BigQuery
    try:
        client = get_bq_client()
        dataset_id = os.getenv("BIGQUERY_DATASET_RAW", "booli_raw")
        table_id = os.getenv("BIGQUERY_TABLE_LISTINGS", "listings")

        table = client.get_table(f"{project_id}.{dataset_id}.{table_id}")

        checks["bigquery_listings"] = {
            "healthy": table.num_rows > 0,
            "row_count": table.num_rows,
        }
        if table.num_rows == 0:
            issues.append("BigQuery listings table is empty")

        logger.info(f"BigQuery: {table.num_rows:,} rows")
    except Exception as e:
        checks["bigquery_listings"] = {"healthy": False, "error": str(e)}
        issues.append(f"BigQuery check failed: {e}")

    # Check model artifacts
    try:
        model_dir = Path("web/models")
        model_files = list(model_dir.glob("price_prediction_model_*.joblib"))

        if model_files:
            latest_model = max(model_files, key=lambda p: p.stat().st_mtime)
            age_hours = (time.time() - latest_model.stat().st_mtime) / 3600

            checks["model_artifacts"] = {
                "healthy": age_hours < 168,
                "age_hours": round(age_hours, 1),
            }
            if age_hours > 168:
                issues.append(f"Model is {age_hours / 24:.1f} days old")
        else:
            checks["model_artifacts"] = {"healthy": False, "error": "No models found"}
            issues.append("No model artifacts found")
    except Exception as e:
        checks["model_artifacts"] = {"healthy": False, "error": str(e)}

    # Check Cloud Run
    cloud_run_url = os.getenv("CLOUD_RUN_URL")
    if cloud_run_url:
        try:
            health_result = health_check_task(f"{cloud_run_url}/api/health")
            checks["cloud_run"] = {"healthy": health_result["healthy"]}
            if not health_result["healthy"]:
                issues.append("Cloud Run service unhealthy")
        except Exception as e:
            checks["cloud_run"] = {"healthy": False, "error": str(e)}
    else:
        checks["cloud_run"] = {"skipped": True}

    is_healthy = len(issues) == 0

    if is_healthy:
        logger.info("Pipeline is healthy")
    else:
        logger.warning(f"Pipeline has {len(issues)} issue(s)")
        for issue in issues:
            logger.warning(f"  - {issue}")

    return {
        "healthy": is_healthy,
        "checks": checks,
        "issues": issues,
        "timestamp": datetime.now().isoformat(),
    }
