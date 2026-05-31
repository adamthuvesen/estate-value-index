"""Standardized return types for pipeline tasks and flows."""

from typing import TypedDict


class TaskResult(TypedDict):
    """Base result shape for all tasks."""

    success: bool
    timestamp: str


class ProcessingResult(TaskResult):
    """Result from data processing tasks."""

    input_file: str
    output_file: str
    total_listings: int
    dry_run: bool


class UploadResult(TaskResult):
    """Result from BigQuery upload tasks."""

    rows_uploaded: int
    table: str


class SyncResult(TaskResult):
    """Result from sync tasks."""

    source: str
    destination: str
    records_synced: int


class MaterializationResult(TaskResult):
    """Result from feature materialization."""

    row_count: int | None


class ValidationResult(TaskResult):
    """Result from model validation tasks."""

    validation_passed: bool
    mae: float
    rmse: float | None
    reasons: list[str]


class VertexJobResult(TaskResult):
    """Result from Vertex AI job submission."""

    job_id: str | None
    run_id: str | None
    model_uri: str | None
    output_uri: str | None


class DeploymentResult(TaskResult):
    """Result from deployment tasks."""

    service_url: str | None
    revision: str | None


class HealthCheckResult(TaskResult):
    """Result from health check tasks."""

    healthy: bool
    status_code: int | None
    response_time_ms: float | None


class AnalyticsResult(TaskResult):
    """Result from analytics generation tasks."""

    output_file: str
    records_generated: int


class RebuildContainerResult(TaskResult):
    """Result from container rebuild tasks."""

    image_uri: str | None
    build_id: str | None


class JobStatusResult(TaskResult):
    """Result from job status checks."""

    status: str
    job_name: str


class DownloadArtifactsResult(TaskResult):
    """Result from artifact download tasks."""

    artifacts: dict[str, str]
    local_dir: str


class PromotionResult(TaskResult):
    """Result from model promotion tasks."""

    model_path: str


class RollbackResult(TaskResult):
    """Result from rollback tasks."""

    revision: str
