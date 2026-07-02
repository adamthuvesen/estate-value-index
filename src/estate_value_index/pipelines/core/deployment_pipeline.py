#!/usr/bin/env python3
"""Prefect flow for Cloud Run deployment orchestration.

This flow wraps deployment tasks into a complete deployment pipeline:
1. Deploy new model to Cloud Run
2. Validate deployment health
3. Optionally rollback if validation fails
"""

from prefect import flow, get_run_logger

# Import deployment tasks from new focused modules
from estate_value_index.pipelines.tasks import (
    deploy_to_cloud_run_task,
    rollback_deployment_task,
)
from estate_value_index.pipelines.utils import DeploymentFlowConfig
from estate_value_index.utils.gcs import get_gcs_bucket


@flow(name="Estate Value Index Deployment Pipeline", log_prints=True)
def deployment_pipeline_flow(config: DeploymentFlowConfig | None = None) -> dict:
    """Deploy to Cloud Run with optional health validation and rollback."""
    if config is None:
        config = DeploymentFlowConfig()

    logger = get_run_logger()

    gcs_bucket = get_gcs_bucket()
    model_artifacts_gcs_uri = config.model_artifacts_gcs_uri or f"gs://{gcs_bucket}/models/"
    enrichment_gcs_uri = config.enrichment_gcs_uri or f"gs://{gcs_bucket}/derived/"

    logger.info(
        f"Starting deployment: validate={config.validate}, auto_rollback={config.auto_rollback_on_failure}, dry_run={config.dry_run}"
    )

    deployment_result = deploy_to_cloud_run_task(
        model_artifacts_gcs_uri=model_artifacts_gcs_uri,
        enrichment_gcs_uri=enrichment_gcs_uri,
        service_name=config.service_name,
        region=config.region,
        validate=config.validate,
        dry_run=config.dry_run,
    )

    # A dry run returns success=True without deploying anything; never report it as deployed.
    deployed = deployment_result.get("success", False) and not config.dry_run
    health_check = deployment_result.get("health_check", {})
    # Assume healthy if no health check was run
    is_healthy = health_check.get("healthy", False) if health_check else True

    if deployed and not is_healthy and config.auto_rollback_on_failure:
        previous_revision = deployment_result.get("previous_revision")

        if previous_revision:
            logger.warning("Deployment unhealthy - initiating auto-rollback")
            try:
                rollback_result = rollback_deployment_task(
                    previous_revision=previous_revision,
                    service_name=config.service_name,
                    region=config.region,
                )
                deployment_result["rollback"] = rollback_result
                deployment_result["auto_rolled_back"] = True
                logger.info("Auto-rollback completed")
            except Exception as e:
                logger.error(f"Auto-rollback failed: {e}")
                deployment_result["rollback_error"] = str(e)
        else:
            logger.warning("Cannot rollback: No previous revision found")

    # Final summary
    if deployment_result.get("auto_rolled_back"):
        logger.info("Deployment rolled back (health check failed)")
    elif deployed and is_healthy:
        logger.info(
            f"Deployment successful: url={deployment_result.get('service_url')}, "
            f"healthy={is_healthy}"
        )
    elif config.dry_run:
        logger.info("Dry run complete")
    else:
        logger.warning(f"Deployment completed with warnings: healthy={is_healthy}")

    return deployment_result


@flow(name="Estate Value Index Quick Deploy")
def quick_deploy_flow(dry_run: bool = False) -> dict:
    """Quick deployment with sensible defaults."""
    config = DeploymentFlowConfig(validate=True, auto_rollback_on_failure=False, dry_run=dry_run)
    return deployment_pipeline_flow(config)


# CLI support
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Deploy to Cloud Run")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without actual deployment")
    parser.add_argument("--quick", action="store_true", help="Quick deployment with defaults")
    parser.add_argument(
        "--auto-rollback", action="store_true", help="Auto-rollback on health check failure"
    )
    args = parser.parse_args()

    if args.quick:
        result = quick_deploy_flow(dry_run=args.dry_run)
    else:
        config = DeploymentFlowConfig(
            auto_rollback_on_failure=args.auto_rollback, dry_run=args.dry_run
        )
        result = deployment_pipeline_flow(config)

    print("\n" + "=" * 80)
    print("DEPLOYMENT RESULT")
    print("=" * 80)
    print(f"Deployed: {result.get('success', False) and not args.dry_run}")
    print(f"URL: {result.get('service_url', 'N/A')}")
    print("=" * 80)
