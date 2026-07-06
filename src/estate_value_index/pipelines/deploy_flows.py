#!/usr/bin/env python3
"""Deploy Prefect flows to Prefect Cloud using Prefect 3.x API."""

import sys
from dataclasses import asdict

from prefect import serve

# Import flows from package structure
from estate_value_index.pipelines.core.data_pipeline import scrape_booli_flow
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
            max_mae=350000,
            production_mode=True,
        )
    ),
}


def deploy_all():
    """Deploy all flows using Prefect 3.x serve() pattern."""
    print("Deploying Prefect flows (v3.x)...")
    print("=" * 60)

    try:
        # Create deployments using .to_deployment()
        scrape_deployment = scrape_booli_flow.to_deployment(
            name="Estate Value Index Weekly Scrape",
            description="Weekly automated scraping of Booli listings",
            version="1.0.0",
            tags=["production", "scraping", "data-collection"],
            parameters={
                "max_pages": 20,  # Scrape more pages in production
                "concurrent_requests": 4,
                "delay": 0.1,
                "upload_to_cloud": True,
            },
            cron="0 2 * * 0",  # Every Sunday at 2 AM CET
            paused=False,
        )

        train_deployment = train_model_flow.to_deployment(
            name="Estate Value Index Monthly ML Pipeline",
            description="Monthly model retraining with hyperparameter tuning",
            version="1.0.0",
            tags=["production", "training", "ml"],
            # `vertex_training_flow` takes a single `config: TrainingFlowConfig`
            # argument; serialised here so Prefect can re-hydrate it on dispatch.
            parameters=TRAIN_DEPLOYMENT_PARAMETERS,
            cron="0 3 1 * *",  # First day of month at 3 AM CET
            paused=False,
        )

        print("Created scraping deployment: weekly-scrape")
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
        print("  prefect deployment run 'scrape-booli-flow/weekly-scrape'")
        print("  prefect deployment run 'train-model-flow/monthly-training'")
        print()
        print("To view deployments:")
        print("  prefect deployment ls")
        print()
        print("=" * 60)

        # Serve both deployments (blocking call)
        serve(scrape_deployment, train_deployment)

    except Exception as e:
        print(f"Deployment failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    deploy_all()
