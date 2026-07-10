"""Tests for cost-monitoring estimate helpers."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from estate_value_index.monitoring import cost_monitoring


def _job(
    *,
    machine_type: str = "n1-standard-4",
    gpu_type: str | None = None,
    gpu_count: int = 0,
    create_time: datetime | None = None,
    end_time: datetime | None = None,
):
    accelerator_type = SimpleNamespace(name=gpu_type) if gpu_type else None
    machine_spec = SimpleNamespace(
        machine_type=machine_type,
        accelerator_type=accelerator_type,
        accelerator_count=gpu_count,
    )
    worker_pool = SimpleNamespace(machine_spec=machine_spec)
    return SimpleNamespace(
        display_name="training-job",
        name="projects/p/locations/r/customJobs/1",
        state=SimpleNamespace(name="JOB_STATE_SUCCEEDED"),
        job_spec=SimpleNamespace(worker_pool_specs=[worker_pool]),
        create_time=create_time,
        end_time=end_time,
    )


def test_training_job_cost_includes_machine_and_gpu_costs() -> None:
    start = datetime(2024, 1, 1, 0, 0, 0)
    end = datetime(2024, 1, 1, 2, 0, 0)

    estimate = cost_monitoring._training_job_cost(
        _job(
            machine_type="n1-standard-4",
            gpu_type="NVIDIA_TESLA_T4",
            gpu_count=2,
            create_time=start,
            end_time=end,
        )
    )

    assert estimate["machine_type"] == "n1-standard-4"
    assert estimate["gpu_type"] == "NVIDIA_TESLA_T4"
    assert estimate["gpu_count"] == 2
    assert estimate["duration_hours"] == 2
    assert estimate["estimated_cost"] == pytest.approx((0.19 + 0.35 * 2) * 2)


def test_training_job_cost_defaults_missing_specs() -> None:
    estimate = cost_monitoring._training_job_cost(
        SimpleNamespace(
            display_name="",
            name="job-name",
            state=None,
            job_spec=SimpleNamespace(worker_pool_specs=[]),
            create_time=None,
            end_time=None,
        )
    )

    assert estimate["name"] == "job-name"
    assert estimate["state"] == "UNKNOWN"
    assert estimate["machine_type"] == "default"
    assert estimate["estimated_cost"] == 0


def test_endpoint_cost_uses_uptime_hours() -> None:
    endpoint = SimpleNamespace(
        display_name="endpoint",
        name="projects/p/locations/r/endpoints/1",
        create_time=datetime.now() - timedelta(hours=3),
    )

    estimate = cost_monitoring._endpoint_cost(endpoint)

    assert estimate["name"] == "endpoint"
    assert estimate["uptime_hours"] == pytest.approx(3, rel=0.01)
    assert estimate["estimated_cost"] == pytest.approx(0.30, rel=0.01)


def test_vertex_cost_result_sums_training_and_endpoint_estimates() -> None:
    result = cost_monitoring._vertex_cost_result(
        "project",
        "region",
        5,
        training_jobs=[{"estimated_cost": 2.0}],
        endpoints=[{"estimated_cost": 3.0}],
    )

    assert result["estimated_cost_usd"] == 5.0
    assert result["average_daily_cost_usd"] == 1.0
    assert result["training_jobs_count"] == 1
    assert result["endpoints_count"] == 1
