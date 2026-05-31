"""Cached Google Cloud client factories.

A single client is reused per process because auth + gRPC channel setup is
expensive (~100ms) and these clients are created repeatedly across ingestion,
ML, and pipeline tasks. The cache is per-process; if a process-based task
runner (fork) is ever introduced, clear it in the child since gRPC channels do
not survive a fork.
"""

from functools import cache

from google.cloud import bigquery, storage


@cache
def get_bq_client(project_id: str | None = None) -> bigquery.Client:
    """Return a shared BigQuery client. ``project_id=None`` uses the ADC default."""
    return bigquery.Client(project=project_id)


@cache
def get_storage_client() -> storage.Client:
    """Return a shared Cloud Storage client (ADC default project)."""
    return storage.Client()
