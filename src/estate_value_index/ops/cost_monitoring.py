"""GCP cost estimates for BigQuery, GCS, and Vertex AI.

Library functions only. Run via ``uv run python -m estate_value_index.cli costs``.
NOT billing truth—sanity checks only.
"""

from datetime import datetime

MACHINE_COSTS = {
    "n1-standard-4": 0.19,
    "n1-standard-8": 0.38,
    "n1-standard-16": 0.76,
    "n1-highmem-2": 0.12,
    "n1-highmem-4": 0.24,
    "n1-highmem-8": 0.48,
    "n1-highcpu-16": 0.57,
    "a2-highgpu-1g": 3.67,
    "default": 0.19,
}
GPU_COSTS = {
    "NVIDIA_TESLA_T4": 0.35,
    "NVIDIA_TESLA_V100": 2.48,
    "NVIDIA_TESLA_P4": 0.60,
    "NVIDIA_TESLA_P100": 1.46,
    "NVIDIA_TESLA_K80": 0.45,
    "NVIDIA_L4": 0.80,
    "NVIDIA_A100_80GB": 3.67,
}
ENDPOINT_HOURLY_COST = 0.10


def monitor_bigquery_costs(project_id: str, days: int = 7) -> dict:
    """Estimate BigQuery query costs from INFORMATION_SCHEMA.JOBS for the past N days."""
    try:
        from google.cloud import bigquery

        from estate_value_index.utils.bigquery_safety import _validate_bq_project_id
        from estate_value_index.utils.clients import get_bq_client

        project_id = _validate_bq_project_id(project_id)
        client = get_bq_client(project_id)

        # Estimate from bytes processed; not actual billing. ``project_id`` is
        # validated above; ``days`` is bound as a query parameter (never an
        # f-string) per the codebase's value-vs-identifier SQL rule.
        query = f"""
        SELECT
            TIMESTAMP_TRUNC(creation_time, DAY) as date,
            SUM(total_bytes_processed) / POW(10, 12) as total_tb_processed,
            SUM(total_bytes_processed) / POW(10, 12) * 5.0 as estimated_cost_usd
        FROM
            `{project_id}.region-europe-north1.INFORMATION_SCHEMA.JOBS`
        WHERE
            creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @days DAY)
            AND job_type = 'QUERY'
            AND state = 'DONE'
        GROUP BY
            date
        ORDER BY
            date DESC
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("days", "INT64", days)]
        )
        results = list(client.query(query, job_config=job_config).result())

        total_tb = sum(row.total_tb_processed or 0 for row in results)
        total_cost = sum(row.estimated_cost_usd or 0 for row in results)

        print(f"\n{'=' * 80}")
        print(f"BIGQUERY COST ESTIMATE (Last {days} days)")
        print(f"{'=' * 80}")
        print(f"Project: {project_id}")
        print(f"Total TB processed: {total_tb:.4f} TB")
        print(f"Estimated cost: ${total_cost:.4f} USD")
        print(f"Average per day: ${total_cost / days:.4f} USD")
        print(f"{'=' * 80}\n")

        if results:
            print("Daily breakdown:")
            for row in results:
                print(
                    f"  {row.date}: {row.total_tb_processed:.4f} TB → ${row.estimated_cost_usd:.4f}"
                )

        return {
            "project_id": project_id,
            "days": days,
            "total_tb_processed": total_tb,
            "estimated_cost_usd": total_cost,
            "average_daily_cost_usd": total_cost / days,
            "daily_breakdown": [
                {
                    "date": str(row.date),
                    "tb_processed": row.total_tb_processed,
                    "estimated_cost": row.estimated_cost_usd,
                }
                for row in results
            ],
        }

    except ImportError:
        print("google-cloud-bigquery not installed")
        print("   Run: pip install google-cloud-bigquery")
        return {}


def monitor_gcs_costs(bucket_name: str) -> dict:
    """Estimate GCS Standard Storage cost ($0.020/GB/month in EU)."""
    try:
        from estate_value_index.utils.clients import get_storage_client

        client = get_storage_client()
        bucket = client.bucket(bucket_name)

        # Single GCS list pass: paginating once is enough to derive the count,
        # the total bytes, and the top-10. The previous code listed twice.
        blobs_with_size = [(blob.name, blob.size or 0) for blob in bucket.list_blobs()]
        blob_count = len(blobs_with_size)
        total_bytes = sum(size for _, size in blobs_with_size)

        total_gb = total_bytes / (1024**3)
        monthly_cost = total_gb * 0.020

        print(f"\n{'=' * 80}")
        print("GCS STORAGE COST ESTIMATE")
        print(f"{'=' * 80}")
        print(f"Bucket: gs://{bucket_name}")
        print(f"Total files: {blob_count:,}")
        print(f"Total size: {total_gb:.2f} GB ({total_bytes:,} bytes)")
        print(f"Estimated monthly cost: ${monthly_cost:.4f} USD")
        print(f"Estimated daily cost: ${monthly_cost / 30:.4f} USD")
        print(f"{'=' * 80}\n")

        if blobs_with_size:
            blobs_with_size.sort(key=lambda x: x[1], reverse=True)
            print("Top 10 largest files:")
            for name, size in blobs_with_size[:10]:
                size_mb = size / (1024**2)
                print(f"  {name}: {size_mb:.2f} MB")

        return {
            "bucket_name": bucket_name,
            "blob_count": blob_count,
            "total_bytes": total_bytes,
            "total_gb": total_gb,
            "estimated_monthly_cost_usd": monthly_cost,
            "estimated_daily_cost_usd": monthly_cost / 30,
        }

    except ImportError:
        print("google-cloud-storage not installed")
        print("   Run: pip install google-cloud-storage")
        return {}


def _duration_hours(create_time, end_time=None) -> float:
    if create_time and end_time:
        return (end_time - create_time).total_seconds() / 3600
    if create_time:
        return (datetime.now() - create_time).total_seconds() / 3600
    return 0


def _training_job_cost(job) -> dict:
    machine_type = "default"
    gpu_type = None
    gpu_count = 0

    if job.job_spec.worker_pool_specs:
        spec = job.job_spec.worker_pool_specs[0]
        if spec.machine_spec.machine_type:
            machine_type = spec.machine_spec.machine_type
        if spec.machine_spec.accelerator_type:
            gpu_type = spec.machine_spec.accelerator_type.name
            gpu_count = spec.machine_spec.accelerator_count or 1

    duration = _duration_hours(job.create_time, job.end_time)
    machine_cost = MACHINE_COSTS.get(machine_type, MACHINE_COSTS["default"]) * duration
    gpu_cost = GPU_COSTS.get(gpu_type, 0) * gpu_count * duration if gpu_type and gpu_count else 0
    job_cost = machine_cost + gpu_cost

    return {
        "name": job.display_name or job.name,
        "state": job.state.name if job.state else "UNKNOWN",
        "machine_type": machine_type,
        "gpu_type": gpu_type,
        "gpu_count": gpu_count,
        "duration_hours": duration,
        "estimated_cost": job_cost,
        "create_time": str(job.create_time) if job.create_time else None,
    }


def _endpoint_cost(endpoint) -> dict:
    uptime = _duration_hours(endpoint.create_time)
    endpoint_cost = ENDPOINT_HOURLY_COST * uptime
    return {
        "name": endpoint.display_name or endpoint.name,
        "uptime_hours": uptime,
        "estimated_cost": endpoint_cost,
        "create_time": str(endpoint.create_time) if endpoint.create_time else None,
    }


def _list_training_job_costs(job_client, request_type, project_id: str, region: str) -> list[dict]:
    parent = job_client.common_location_path(project=project_id, location=region)
    req = request_type(parent=parent, filter="state!=JOB_STATE_CANCELLED")
    return [_training_job_cost(job) for job in job_client.list_custom_jobs(request=req)]


def _list_endpoint_costs(endpoint_client, request_type, project_id: str, region: str) -> list[dict]:
    parent = endpoint_client.common_location_path(project=project_id, location=region)
    req = request_type(parent=parent)
    return [_endpoint_cost(endpoint) for endpoint in endpoint_client.list_endpoints(request=req)]


def _print_vertex_summary(
    project_id: str,
    region: str,
    days: int,
    training_jobs: list[dict],
    endpoints: list[dict],
) -> None:
    total_training_cost = sum(job["estimated_cost"] for job in training_jobs)
    total_endpoint_cost = sum(endpoint["estimated_cost"] for endpoint in endpoints)
    total_cost = total_training_cost + total_endpoint_cost

    print(f"\n{'=' * 80}")
    print(f"VERTEX AI COST ESTIMATE (Last {days} days)")
    print(f"{'=' * 80}")
    print(f"Project: {project_id}")
    print(f"Region: {region}")
    print(f"Training jobs: {len(training_jobs)}")
    print(f"Endpoints: {len(endpoints)}")
    print(f"Total training cost: ${total_training_cost:.4f} USD")
    print(f"Total endpoint cost: ${total_endpoint_cost:.4f} USD")
    print(f"Total estimated cost: ${total_cost:.4f} USD")
    print(f"Average per day: ${total_cost / days:.4f} USD")
    print(f"{'=' * 80}\n")


def _print_training_jobs(training_jobs: list[dict]) -> None:
    if not training_jobs:
        return

    print("Training Jobs:")
    for job in training_jobs[:10]:
        gpu_info = f" + {job['gpu_count']}x{job['gpu_type']}" if job["gpu_type"] else ""
        print(f"  {job['name']} ({job['state']})")
        print(f"    Machine: {job['machine_type']}{gpu_info}")
        print(f"    Duration: {job['duration_hours']:.2f}h → ${job['estimated_cost']:.4f}")


def _print_endpoints(endpoints: list[dict]) -> None:
    if not endpoints:
        return

    print("\nEndpoints:")
    for endpoint in endpoints[:10]:
        print(f"  {endpoint['name']}")
        print(f"    Uptime: {endpoint['uptime_hours']:.2f}h → ${endpoint['estimated_cost']:.4f}")


def _vertex_cost_result(
    project_id: str,
    region: str,
    days: int,
    training_jobs: list[dict],
    endpoints: list[dict],
) -> dict:
    total_training_cost = sum(job["estimated_cost"] for job in training_jobs)
    total_endpoint_cost = sum(endpoint["estimated_cost"] for endpoint in endpoints)
    total_cost = total_training_cost + total_endpoint_cost

    return {
        "project_id": project_id,
        "region": region,
        "days": days,
        "training_jobs_count": len(training_jobs),
        "endpoints_count": len(endpoints),
        "total_training_cost_usd": total_training_cost,
        "total_endpoint_cost_usd": total_endpoint_cost,
        "estimated_cost_usd": total_cost,
        "average_daily_cost_usd": total_cost / days,
        "training_jobs": training_jobs,
        "endpoints": endpoints,
    }


def monitor_vertex_ai_costs(project_id: str, region: str = "europe-north1", days: int = 7) -> dict:
    """Estimate Vertex AI training-job + endpoint costs.

    Costs are derived from machine type, GPU type/count, duration, and uptime
    using approximate hourly rates (Vertex AI Training pricing, ~2024).
    """
    try:
        # REST transport avoids gRPC (and ALTS warnings) entirely
        from google.api_core.client_options import ClientOptions
        from google.cloud.aiplatform_v1.services.endpoint_service import EndpointServiceClient
        from google.cloud.aiplatform_v1.services.job_service import JobServiceClient
        from google.cloud.aiplatform_v1.types import endpoint_service as es
        from google.cloud.aiplatform_v1.types import job_service as js

        client_options = ClientOptions(api_endpoint=f"{region}-aiplatform.googleapis.com")
        job_client = JobServiceClient(client_options=client_options, transport="rest")
        endpoint_client = EndpointServiceClient(client_options=client_options, transport="rest")

        try:
            training_jobs = _list_training_job_costs(
                job_client, js.ListCustomJobsRequest, project_id, region
            )
        except Exception as e:
            print(f"WARNING: Could not list training jobs: {e}")
            training_jobs = []

        try:
            endpoints = _list_endpoint_costs(
                endpoint_client, es.ListEndpointsRequest, project_id, region
            )
        except Exception as e:
            print(f"WARNING: Could not list endpoints: {e}")
            endpoints = []

        _print_vertex_summary(project_id, region, days, training_jobs, endpoints)
        _print_training_jobs(training_jobs)
        _print_endpoints(endpoints)
        return _vertex_cost_result(project_id, region, days, training_jobs, endpoints)

    except ImportError:
        print("google-cloud-aiplatform not installed")
        print("   Run: pip install google-cloud-aiplatform")
        return {}
