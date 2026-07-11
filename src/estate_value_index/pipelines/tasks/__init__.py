"""Pipeline tasks - curated public API.

This module provides a unified interface to all pipeline tasks, organized by domain:

- **Ingestion**: Process ingested listings and upload them to BigQuery
- **Sync**: BigQuery ↔ Local ↔ GCS synchronization
- **Analytics**: Area statistics and value analysis generation
- **Training**: Feature materialization and Vertex AI training jobs
- **Deployment**: Cloud Run deployment, health checks, rollback
"""

# Ingestion tasks
# Analytics tasks
from .analytics import (
    generate_area_statistics_task,
    generate_overall_statistics_task,
    generate_value_analysis_task,
    upload_enrichment_to_gcs_task,
)

# Deployment tasks
from .deployment import (
    deploy_to_cloud_run_task,
    health_check_task,
    log_metrics_task,
    monitor_pipeline_health_task,
    rollback_deployment_task,
)
from .ingestion import geocode_new_addresses_task, process_listings_task, upload_to_bigquery_task

# Sync tasks
from .sync import (
    sync_bigquery_to_local_task,
    sync_local_to_gcs_task,
    verify_sync_task,
)

# Training tasks
from .training import (
    download_model_artifacts_task,
    materialize_features_task,
    poll_vertex_job_status_task,
    promote_model_to_production_task,
    rebuild_container_task,
    register_model_to_vertex_task,
    submit_vertex_training_job_task,
    validate_model_performance_task,
)

__all__ = [
    # Ingestion
    "geocode_new_addresses_task",
    "process_listings_task",
    "upload_to_bigquery_task",
    # Sync
    "sync_bigquery_to_local_task",
    "sync_local_to_gcs_task",
    "verify_sync_task",
    # Analytics
    "generate_area_statistics_task",
    "generate_overall_statistics_task",
    "generate_value_analysis_task",
    "upload_enrichment_to_gcs_task",
    # Training
    "download_model_artifacts_task",
    "materialize_features_task",
    "poll_vertex_job_status_task",
    "promote_model_to_production_task",
    "rebuild_container_task",
    "register_model_to_vertex_task",
    "submit_vertex_training_job_task",
    "validate_model_performance_task",
    # Deployment
    "deploy_to_cloud_run_task",
    "health_check_task",
    "log_metrics_task",
    "monitor_pipeline_health_task",
    "rollback_deployment_task",
]
