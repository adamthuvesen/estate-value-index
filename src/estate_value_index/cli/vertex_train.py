"""``evi vertex-train``: run the production trainer on Vertex AI and download its artifacts.

The only module that starts external processes (``gcloud``). Import-linter forbids
``subprocess`` everywhere else (see ``pyproject.toml``). Every ``gcloud`` call asks for
``--format=json``, and the job id and model URI come from that response.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from estate_value_index.exceptions import InfrastructureError
from estate_value_index.model_artifacts import (
    DEFAULT_MODEL_PREFIX,
    required_production_artifact_files,
)
from estate_value_index.utils.approval import require_approval
from estate_value_index.utils.gcs import download_model_artifacts
from estate_value_index.utils.settings import get_settings

_JOB_NAME_RE: Final = re.compile(r"^projects/[\w-]+/locations/[\w-]+/customJobs/\d+$")
_TERMINAL_STATES: Final = frozenset(
    {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"}
)
_CONTAINER_MODEL_DIR: Final = "/tmp/estate-value-index/models"


def build_job_spec(
    *,
    project_id: str,
    bucket: str,
    run_id: str,
    image_uri: str,
    machine_type: str,
    service_account: str,
    trainer_args: list[str],
) -> dict[str, Any]:
    """Return the Vertex ``CustomJobSpec`` that runs ``evi train-production-models``."""
    settings = get_settings()
    env = {
        "GCP_PROJECT_ID": project_id,
        "BIGQUERY_DATASET_RAW": settings.bigquery_dataset_raw,
        "BIGQUERY_TABLE_LISTINGS": settings.bigquery_table_listings,
        "GCS_BUCKET": bucket,
        "GCS_ENABLED": "true",
        "MODEL_ARTIFACTS_URI": f"gs://{bucket}/vertex-ai/models/{run_id}",
    }
    return {
        "serviceAccount": service_account,
        "baseOutputDirectory": {"outputUriPrefix": f"gs://{bucket}/vertex-ai/jobs/{run_id}"},
        "workerPoolSpecs": [
            {
                "machineSpec": {"machineType": machine_type},
                "replicaCount": 1,
                "containerSpec": {
                    "imageUri": image_uri,
                    "args": [
                        "--data-source",
                        "bigquery",
                        "--model-dir",
                        _CONTAINER_MODEL_DIR,
                        "--model-prefix",
                        DEFAULT_MODEL_PREFIX,
                        *trainer_args,
                    ],
                    "env": [{"name": name, "value": value} for name, value in env.items()],
                },
            }
        ],
    }


def _gcloud_json(args: list[str], *, timeout: float) -> dict[str, Any]:
    result = subprocess.run(
        ["gcloud", *args, "--format=json"],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise InfrastructureError(
            f"gcloud {' '.join(args[:3])} failed with code {result.returncode}",
            context={"stderr": result.stderr.strip()[-2000:]},
        )
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise InfrastructureError(f"gcloud {' '.join(args[:3])} returned no JSON object")
    return payload


def job_name(job: dict[str, Any]) -> str:
    name = job.get("name")
    if not isinstance(name, str) or not _JOB_NAME_RE.match(name):
        raise InfrastructureError(f"Vertex response has no custom job name: {name!r}")
    return name


def model_uri(job: dict[str, Any]) -> str:
    """Read ``MODEL_ARTIFACTS_URI`` from the job spec the API returned."""
    for pool in job.get("jobSpec", {}).get("workerPoolSpecs", []):
        for env_var in pool.get("containerSpec", {}).get("env", []):
            if env_var.get("name") == "MODEL_ARTIFACTS_URI" and env_var.get("value"):
                return env_var["value"]
    raise InfrastructureError("Vertex response has no MODEL_ARTIFACTS_URI in its job spec")


def submit_job(
    spec: dict[str, Any], *, project_id: str, region: str, display_name: str
) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as config:
        json.dump(spec, config)
    try:
        return _gcloud_json(
            [
                "ai",
                "custom-jobs",
                "create",
                f"--project={project_id}",
                f"--region={region}",
                f"--display-name={display_name}",
                f"--config={config.name}",
            ],
            timeout=120,
        )
    finally:
        Path(config.name).unlink(missing_ok=True)


def wait_for_job(
    name: str, *, region: str, poll_seconds: float = 30, timeout_seconds: float = 3 * 3600
) -> dict[str, Any]:
    """Poll the job until it ends. Raise unless it ends in ``JOB_STATE_SUCCEEDED``."""
    deadline = time.monotonic() + timeout_seconds
    while True:
        job = _gcloud_json(
            ["ai", "custom-jobs", "describe", name, f"--region={region}"], timeout=60
        )
        state = job.get("state")
        if state in _TERMINAL_STATES:
            break
        if time.monotonic() > deadline:
            raise InfrastructureError(f"Vertex job {name} still {state} after {timeout_seconds}s")
        time.sleep(poll_seconds)
    if state != "JOB_STATE_SUCCEEDED":
        raise InfrastructureError(
            f"Vertex job {name} ended in {state}", context={"error": job.get("error")}
        )
    return job


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="evi vertex-train",
        description="Run the production trainer on Vertex AI, wait for it, and download the artifacts.",
    )
    parser.add_argument("--machine-type", default="n1-standard-4")
    parser.add_argument("--image-uri", default=None, help="Default: the lgbm-trainer:latest image.")
    parser.add_argument("--service-account", default=None)
    parser.add_argument("--display-name", default=None)
    parser.add_argument("--model-dir", type=Path, default=Path("web/models"))
    parser.add_argument("--tune", action="store_true", help="Pass --tune to the trainer.")
    parser.add_argument("--poll-seconds", type=float, default=30)
    parser.add_argument("--dry-run", action="store_true", help="Print the job spec and stop.")
    parser.add_argument(
        "--approved",
        action="store_true",
        help="Allow the Vertex job and the trainer's GCS artifact upload.",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    project_id = settings.require_gcp_project_id()
    bucket = settings.require_gcs_bucket()
    region = settings.gcp_region
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    spec = build_job_spec(
        project_id=project_id,
        bucket=bucket,
        run_id=run_id,
        image_uri=args.image_uri
        or f"{region}-docker.pkg.dev/{project_id}/vertex-training/lgbm-trainer:latest",
        machine_type=args.machine_type,
        service_account=args.service_account
        or f"estate-value-index-service-acc@{project_id}.iam.gserviceaccount.com",
        trainer_args=[
            *(["--approved"] if args.approved else []),
            *(["--tune"] if args.tune else []),
        ],
    )
    if args.dry_run:
        print(json.dumps(spec, indent=2))
        return 0

    require_approval("submit a Vertex AI training job", args.approved)
    job = submit_job(
        spec,
        project_id=project_id,
        region=region,
        display_name=args.display_name or f"lgbm-train-{run_id}",
    )
    name = job_name(job)
    artifacts_uri = model_uri(job)
    print(f"Submitted {name}", file=sys.stderr)
    final = wait_for_job(name, region=region, poll_seconds=args.poll_seconds)
    download_model_artifacts(
        artifacts_uri, args.model_dir, required_production_artifact_files(DEFAULT_MODEL_PREFIX)
    )
    print(
        json.dumps(
            {
                "job_id": name,
                "state": final["state"],
                "model_uri": artifacts_uri,
                "model_dir": str(args.model_dir),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
