#!/usr/bin/env python3
"""Deploy Prefect flows to Prefect Cloud using Prefect 3.x API."""

import sys
from dataclasses import asdict

from prefect import serve

# Import flows from package structure
from estate_value_index.pipelines.core.data_pipeline import ingest_booli_flow
from estate_value_index.pipelines.core.training_pipeline import (
    vertex_training_flow as train_model_flow,
)
from estate_value_index.pipelines.utils import TrainingFlowConfig

# Parameters Prefect serialises into the deployment registration. Lifted to a
# module-level constant so the flow-signature contract test can validate
# every key against `vertex_training_flow`'s actual signature.
TRAIN_DEPLOYMENT_PARAMETERS: dict = {
    "config": asdict(
        TrainingFlowConfig(
            tune=False,
            max_median_ape=0.08,
        )
    ),
}
INGESTION_DEPLOYMENT_PARAMETERS = {
    "max_pages": 20,
    "upload_to_cloud": True,
}


def deploy_all():
    """Deploy all flows using Prefect 3.x serve() pattern."""
    print("Deploying Prefect flows (v3.x)...")
    print("=" * 60)

    try:
        # Create deployments using .to_deployment()
        ingestion_deployment = ingest_booli_flow.to_deployment(
            name="Estate Value Index Weekly Ingestion",
            description="Weekly authorized Booli API ingestion",
            version="1.0.0",
            tags=["production", "ingestion", "data-collection"],
            parameters=INGESTION_DEPLOYMENT_PARAMETERS,
            cron="0 2 * * 0",  # Every Sunday at 2 AM CET
            paused=False,
        )

        train_deployment = train_model_flow.to_deployment(
            name="Estate Value Index Monthly ML Pipeline",
            description="Monthly production model retraining",
            version="1.0.0",
            tags=["production", "training", "ml"],
            # `vertex_training_flow` takes a single `config: TrainingFlowConfig`
            # argument; serialised here so Prefect can re-hydrate it on dispatch.
            parameters=TRAIN_DEPLOYMENT_PARAMETERS,
            cron="0 3 1 * *",  # First day of month at 3 AM CET
            paused=False,
        )

        print("Created ingestion deployment: weekly-ingestion")
        print("  Schedule: Every Sunday at 2:00 AM CET")
        print()
        print("Created training deployment: monthly-training")
        print("  Schedule: First day of each month at 3:00 AM CET")
        print()
        print("=" * 60)
        print("Starting deployment server (Prefect 3.x)...")
        print()
        print("This will start a long-running process that:")
        print("  - Registers deployments with Prefect Cloud")
        print("  - Monitors for scheduled runs")
        print("  - Executes flows on schedule")
        print()
        print("To trigger manual runs (in another terminal):")
        print("  Use 'prefect deployment ls' to find the registered deployment names.")
        print("  Then run one with 'prefect deployment run <flow-name>/<deployment-name>'.")
        print()
        print("To view deployments:")
        print("  prefect deployment ls")
        print()
        print("=" * 60)

        # Serve both deployments (blocking call)
        serve(ingestion_deployment, train_deployment)

    except Exception as e:
        print(f"Deployment failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    deploy_all()
