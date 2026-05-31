"""GCP cost estimates for BigQuery, GCS, and Vertex AI.

Library functions only. Run via ``python -m estate_value_index.cli costs``.
NOT billing truth—sanity checks only.
"""

from datetime import datetime


def monitor_bigquery_costs(project_id: str, days: int = 7) -> dict:
    """Estimate BigQuery query costs from INFORMATION_SCHEMA.JOBS for the past N days."""
    try:
        from estate_value_index.utils.bigquery_safety import _validate_bq_project_id
        from estate_value_index.utils.clients import get_bq_client

        project_id = _validate_bq_project_id(project_id)
        client = get_bq_client(project_id)

        # Estimate from bytes processed; not actual billing
        query = f"""
        SELECT
            TIMESTAMP_TRUNC(creation_time, DAY) as date,
            SUM(total_bytes_processed) / POW(10, 12) as total_tb_processed,
            SUM(total_bytes_processed) / POW(10, 12) * 5.0 as estimated_cost_usd
        FROM
            `{project_id}.region-europe-north1.INFORMATION_SCHEMA.JOBS`
        WHERE
            creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days} DAY)
            AND job_type = 'QUERY'
            AND state = 'DONE'
        GROUP BY
            date
        ORDER BY
            date DESC
        """

        results = list(client.query(query).result())

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

        MACHINE_COSTS = {
            "n1-standard-4": 0.19,
            "n1-standard-8": 0.38,
            "n1-standard-16": 0.76,
            "n1-highmem-2": 0.12,
            "n1-highmem-4": 0.24,
            "n1-highmem-8": 0.48,
            "n1-highcpu-16": 0.57,
            "a2-highgpu-1g": 3.67,  # with 1 A100 GPU
            "default": 0.19,  # fallback
        }

        # GPU costs (per hour)
        GPU_COSTS = {
            "NVIDIA_TESLA_T4": 0.35,
            "NVIDIA_TESLA_V100": 2.48,
            "NVIDIA_TESLA_P4": 0.60,
            "NVIDIA_TESLA_P100": 1.46,
            "NVIDIA_TESLA_K80": 0.45,
            "NVIDIA_L4": 0.80,
            "NVIDIA_A100_80GB": 3.67,
        }

        training_jobs = []
        total_training_cost = 0.0

        try:
            parent = job_client.common_location_path(project=project_id, location=region)
            req = js.ListCustomJobsRequest(parent=parent, filter="state!=JOB_STATE_CANCELLED")
            jobs_iter = job_client.list_custom_jobs(request=req)

            for job in jobs_iter:
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

                if job.create_time and job.end_time:
                    duration = (job.end_time - job.create_time).total_seconds() / 3600
                elif job.create_time:
                    # Still running
                    duration = (datetime.now() - job.create_time).total_seconds() / 3600
                else:
                    duration = 0

                machine_cost = MACHINE_COSTS.get(machine_type, MACHINE_COSTS["default"]) * duration
                gpu_cost = 0
                if gpu_type and gpu_count:
                    gpu_cost = GPU_COSTS.get(gpu_type, 0) * gpu_count * duration

                job_cost = machine_cost + gpu_cost
                total_training_cost += job_cost

                training_jobs.append(
                    {
                        "name": job.display_name or job.name,
                        "state": job.state.name if job.state else "UNKNOWN",
                        "machine_type": machine_type,
                        "gpu_type": gpu_type,
                        "gpu_count": gpu_count,
                        "duration_hours": duration,
                        "estimated_cost": job_cost,
                        "create_time": str(job.create_time) if job.create_time else None,
                    }
                )

        except Exception as e:
            print(f"WARNING: Could not list training jobs: {e}")

        endpoints = []
        total_endpoint_cost = 0.0

        try:
            parent = endpoint_client.common_location_path(project=project_id, location=region)
            req = es.ListEndpointsRequest(parent=parent)
            endpoint_iter = endpoint_client.list_endpoints(request=req)

            # Approximate prediction pricing per node-hour
            ENDPOINT_HOURLY_COST = 0.10

            for endpoint in endpoint_iter:
                if endpoint.create_time:
                    uptime = (datetime.now() - endpoint.create_time).total_seconds() / 3600
                else:
                    uptime = 0

                # Assume 1 replica
                endpoint_cost = ENDPOINT_HOURLY_COST * uptime
                total_endpoint_cost += endpoint_cost

                endpoints.append(
                    {
                        "name": endpoint.display_name or endpoint.name,
                        "uptime_hours": uptime,
                        "estimated_cost": endpoint_cost,
                        "create_time": str(endpoint.create_time) if endpoint.create_time else None,
                    }
                )

        except Exception as e:
            print(f"WARNING: Could not list endpoints: {e}")

        # Print summary
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

        # Show training jobs
        if training_jobs:
            print("Training Jobs:")
            for job in training_jobs[:10]:  # Show top 10
                gpu_info = f" + {job['gpu_count']}x{job['gpu_type']}" if job["gpu_type"] else ""
                print(f"  {job['name']} ({job['state']})")
                print(f"    Machine: {job['machine_type']}{gpu_info}")
                print(f"    Duration: {job['duration_hours']:.2f}h → ${job['estimated_cost']:.4f}")

        # Show endpoints
        if endpoints:
            print("\nEndpoints:")
            for ep in endpoints[:10]:  # Show top 10
                print(f"  {ep['name']}")
                print(f"    Uptime: {ep['uptime_hours']:.2f}h → ${ep['estimated_cost']:.4f}")

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

    except ImportError:
        print("google-cloud-aiplatform not installed")
        print("   Run: pip install google-cloud-aiplatform")
        return {}
