#!/usr/bin/env python3
"""Complete end-to-end ML pipeline orchestration.

This flow connects all pipeline stages into a single automated workflow:
1. Data Collection: Scrape → Process → BigQuery → Features
2. Model Training: Train (Vertex AI or local) → Validate
3. Enrichment: Generate area statistics → Upload to GCS
4. Deployment: Deploy to Cloud Run (optional)
5. Notification: Send alerts (optional)
"""

from datetime import datetime

from prefect import flow, get_run_logger

# Import flows from package structure
from estate_value_index.pipelines.core.data_pipeline import complete_scrape_flow
from estate_value_index.pipelines.core.training_pipeline import vertex_training_flow
from estate_value_index.pipelines.tasks import (
    deploy_to_cloud_run_task,
    sync_bigquery_to_local_task,
    sync_local_to_gcs_task,
    verify_sync_task,
)
from estate_value_index.pipelines.utils import TrainingFlowConfig
from estate_value_index.utils.gcs import get_gcs_bucket


@flow(name="Estate Value Index Complete ML Pipeline", log_prints=True)
def complete_pipeline_flow(
    # Scraping configuration
    max_pages: int = 10,
    skip_scraping: bool = False,
    config_file: str | None = None,
    # Training configuration
    tune: bool = False,
    use_vertex: bool = True,
    machine_type: str = "n1-standard-4",
    rebuild_container: bool = False,
    # Deployment configuration
    deploy_to_prod: bool = False,
    validate_deployment: bool = True,
    # Advanced options
    dry_run: bool = False,
) -> dict:
    """End-to-end ML pipeline: data collection → training → enrichment → deployment."""
    logger = get_run_logger()

    logger.info("Starting complete ML pipeline")
    logger.info(
        f"Config: scraping={'skip' if skip_scraping else max_pages}, "
        f"training={'vertex' if use_vertex else 'local'}, tune={tune}, "
        f"deploy={deploy_to_prod}, dry_run={dry_run}"
    )

    start_time = datetime.now()
    results = {
        "pipeline_start": start_time.isoformat(),
        "configuration": {
            "max_pages": max_pages,
            "skip_scraping": skip_scraping,
            "tune": tune,
            "use_vertex": use_vertex,
            "deploy_to_prod": deploy_to_prod,
            "dry_run": dry_run,
        },
        "stages": {},
    }

    try:
        # Stage 1: Data Collection
        if not skip_scraping:
            logger.info("Stage 1: Data collection (scrape, process, bigquery, features)")

            # Prefect parameter validation in some environments rejects None for str-typed params.
            # Ensure we pass a string (empty string means "no config file").
            _cfg = config_file or ""

            scrape_result = complete_scrape_flow(
                max_pages=max_pages,
                upload_to_bq=not dry_run,
                materialize_features=not dry_run,
                upload_to_cloud=not dry_run,
                config_file=_cfg,
            )

            results["stages"]["data_collection"] = scrape_result

            # Log summary
            scraping_info = scrape_result.get("scraping", {})
            processing_info = scrape_result.get("processing", {})
            bq_info = scrape_result.get("bigquery", {})
            features_info = scrape_result.get("features", {})

            scraped = scraping_info.get("validation", {}).get("valid_listings", 0)
            processed = processing_info.get("total_listings", 0)
            bq_rows = bq_info.get("uploaded", 0) if bq_info else 0
            feat_rows = features_info.get("row_count", 0) if features_info else 0
            logger.info(
                f"Stage 1 complete: scraped={scraped}, processed={processed}, bq={bq_rows}, features={feat_rows}"
            )
        else:
            logger.info("Stage 1: Skipped (using existing data)")
            results["stages"]["data_collection"] = {"skipped": True, "reason": "skip_scraping=True"}

        # Sync: Ensure local file matches BigQuery
        if not dry_run:
            logger.info("Syncing local file with BigQuery")
            try:
                sync_result = sync_bigquery_to_local_task()
                results["stages"]["sync"] = sync_result

                verify_result = verify_sync_task()
                results["stages"]["sync"]["verification"] = verify_result

                gcs_result = sync_local_to_gcs_task()
                results["stages"]["sync"]["gcs_backup"] = gcs_result

                logger.info(
                    f"Sync complete: {sync_result.get('listings_count', 0)} listings, in_sync={verify_result.get('in_sync', False)}"
                )
            except Exception as e:
                logger.warning(f"Sync failed but continuing: {e}")
                results["stages"]["sync"] = {"error": str(e), "success": False}
        else:
            logger.info("Sync: Skipped (dry_run)")
            results["stages"]["sync"] = {"skipped": True, "reason": "dry_run=True"}

        # Stage 2: Model Training
        logger.info(f"Stage 2: Training ({'vertex' if use_vertex else 'local'}, tune={tune})")

        if use_vertex:
            training_config = TrainingFlowConfig(
                tune=tune,
                machine_type=machine_type,
                rebuild_container=rebuild_container,
                skip_materialization=not skip_scraping,  # Already materialized in Stage 1
                register_to_vertex=False,  # Don't auto-register
                stream_logs=True,
                production_mode=True,  # Always retrain on full dataset for production
                dry_run=dry_run,
                use_vertex=True,
            )
            training_result = vertex_training_flow(config=training_config)
        else:
            # Use vertex_training_flow with use_vertex=False for local training
            training_config = TrainingFlowConfig(
                tune=tune,
                use_vertex=False,  # Force local training
                production_mode=True,  # Always retrain on full dataset
            )
            training_result = vertex_training_flow(config=training_config)

        results["stages"]["training"] = training_result

        # Check training success
        if not training_result.get("success", False):
            logger.error("Training failed - aborting pipeline")
            results["success"] = False
            results["aborted_at_stage"] = "training"
            return results

        metrics = training_result.get("metrics", {})
        validation_passed = training_result.get("validation_passed", False)
        mae = metrics.get("mae", 0)
        logger.info(
            f"Stage 2 complete: validation={'passed' if validation_passed else 'failed'}, MAE={mae:,.0f}"
        )

        # Stage 3: Enrichment (completed in training flow)
        area_stats = training_result.get("steps", {}).get("area_statistics", {})
        value_analysis = training_result.get("steps", {}).get("value_analysis", {})
        logger.info(
            f"Stage 3: Enrichment complete (areas={area_stats.get('areas_count', 0)}, properties={value_analysis.get('properties_count', 0)})"
        )

        results["stages"]["enrichment"] = {
            "completed_in_training_flow": True,
            "area_statistics": area_stats,
            "value_analysis": value_analysis,
        }

        # Stage 4: Deployment (optional)
        if deploy_to_prod and validation_passed and not dry_run:
            logger.info("Stage 4: Deploying to Cloud Run")
            try:
                model_gcs_uri = (
                    training_result.get("steps", {}).get("download_artifacts", {}).get("model_uri")
                )
                gcs_bucket = get_gcs_bucket()

                deploy_result = deploy_to_cloud_run_task(
                    model_artifacts_gcs_uri=model_gcs_uri or f"gs://{gcs_bucket}/models/",
                    enrichment_gcs_uri=f"gs://{gcs_bucket}/enrichment/",
                    validate=validate_deployment,
                )
                results["stages"]["deployment"] = deploy_result
                logger.info(
                    f"Stage 4 complete: deployed={deploy_result.get('deployed', False)}, url={deploy_result.get('url', 'N/A')}"
                )
            except ImportError:
                logger.warning("Deployment tasks not available - skipping")
                results["stages"]["deployment"] = {
                    "skipped": True,
                    "reason": "deployment_tasks_not_available",
                }
        else:
            reasons = []
            if not deploy_to_prod:
                reasons.append("deploy_to_prod=False")
            if not validation_passed:
                reasons.append("validation_failed")
            if dry_run:
                reasons.append("dry_run=True")

            logger.info(f"Stage 4: Skipped ({', '.join(reasons)})")
            results["stages"]["deployment"] = {"skipped": True, "reasons": reasons}

        results["stages"]["notification"] = {"skipped": True, "reason": "notifications_disabled"}

        # Pipeline complete
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        results["success"] = True
        results["pipeline_end"] = end_time.isoformat()
        results["duration_seconds"] = duration
        results["duration_minutes"] = round(duration / 60, 2)

        stages_done = len(
            [s for s in results["stages"].values() if isinstance(s, dict) and not s.get("skipped")]
        )
        deployed = deploy_to_prod and validation_passed
        logger.info(
            f"Pipeline complete: {duration / 60:.1f}min, {stages_done} stages, MAE={mae:,.0f}, validation={'passed' if validation_passed else 'failed'}, deployed={deployed}"
        )

        return results

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        results["success"] = False
        results["error"] = str(e)
        results["pipeline_end"] = end_time.isoformat()
        results["duration_seconds"] = duration
        results["duration_minutes"] = round(duration / 60, 2)

        raise


@flow(name="Estate Value Index Quick Pipeline - Testing")
def quick_pipeline_flow(max_pages: int = 5) -> dict:
    """Quick pipeline for testing (no tuning, no deployment)."""
    return complete_pipeline_flow(
        max_pages=max_pages, tune=False, deploy_to_prod=False, dry_run=False
    )


@flow(name="Estate Value Index Production Pipeline - Full")
def production_pipeline_flow(max_pages: int = 5, deploy: bool = True) -> dict:
    """Full production pipeline: scrape, tune, deploy."""
    return complete_pipeline_flow(
        max_pages=max_pages,
        tune=True,
        use_vertex=True,
        machine_type="n1-standard-4",
        deploy_to_prod=deploy,
        validate_deployment=True,
        dry_run=False,
    )


@flow(name="Estate Value Index Retrain Pipeline - No Scraping")
def retrain_pipeline_flow(tune: bool = True, deploy: bool = False) -> dict:
    """Retrain model using existing data (no scraping)."""
    return complete_pipeline_flow(
        skip_scraping=True, tune=tune, use_vertex=True, deploy_to_prod=deploy, dry_run=False
    )


# CLI support
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Complete ML Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""

  # Quick test run
  python complete_pipeline_flow.py --quick

  # Production run
  python complete_pipeline_flow.py --production

  # Retrain only
  python complete_pipeline_flow.py --retrain

  # Custom configuration
  python complete_pipeline_flow.py --max-pages 20 --tune --deploy

  # Dry run
  python complete_pipeline_flow.py --dry-run
        """,
    )

    # Preset modes
    parser.add_argument("--quick", action="store_true", help="Quick test run (5 pages, no tuning)")
    parser.add_argument(
        "--production", action="store_true", help="Full production run (5 pages, tuning, deploy)"
    )
    parser.add_argument("--retrain", action="store_true", help="Retrain only (no scraping)")

    # Custom configuration
    parser.add_argument("--max-pages", type=int, default=10, help="Maximum pages to scrape")
    parser.add_argument(
        "--skip-scraping", action="store_true", help="Skip scraping, use existing data"
    )
    parser.add_argument(
        "--config-file",
        type=str,
        default=None,
        help="Path to config file (e.g., ingestion/config/booli_solna_sundbyberg.json)",
    )
    parser.add_argument("--tune", action="store_true", help="Enable hyperparameter tuning")
    parser.add_argument(
        "--no-vertex", action="store_true", help="Use local training instead of Vertex AI"
    )
    parser.add_argument(
        "--rebuild-container",
        action="store_true",
        help="Rebuild Vertex training image before submitting job",
    )
    parser.add_argument("--deploy", action="store_true", help="Deploy to Cloud Run after training")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without execution")

    args = parser.parse_args()

    # Run appropriate flow
    if args.quick:
        print("Running QUICK pipeline...")
        result = quick_pipeline_flow(max_pages=5)
    elif args.production:
        print("Running PRODUCTION pipeline...")
        result = production_pipeline_flow(max_pages=5, deploy=True)
    elif args.retrain:
        print("Running RETRAIN pipeline...")
        result = retrain_pipeline_flow(tune=True, deploy=args.deploy)
    else:
        print("Running end-to-end pipeline...")
        result = complete_pipeline_flow(
            max_pages=args.max_pages,
            skip_scraping=args.skip_scraping,
            config_file=args.config_file,
            tune=args.tune,
            use_vertex=not args.no_vertex,
            rebuild_container=args.rebuild_container,
            deploy_to_prod=args.deploy,
            dry_run=args.dry_run,
        )

    # Print summary
    print("\n" + "=" * 80)
    print("PIPELINE RESULTS")
    print("=" * 80)
    print(f"Success: {result.get('success', False)}")
    print(f"Duration: {result.get('duration_minutes', 0):.1f} minutes")

    if result.get("stages", {}).get("training", {}).get("metrics"):
        metrics = result["stages"]["training"]["metrics"]
        print(f"MAE: {metrics.get('mae', 0):,.0f} SEK")

    print("=" * 80)
