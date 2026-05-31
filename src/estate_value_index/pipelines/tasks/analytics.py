"""Tasks for generating analytics and enrichment data."""

import json
from datetime import datetime
from pathlib import Path

from prefect import task

from estate_value_index.pipelines.types import AnalyticsResult
from estate_value_index.pipelines.utils import get_task_logger
from estate_value_index.utils.clients import get_storage_client


@task(
    name="generate-area-statistics",
    description="Generate area statistics for web app",
    retries=2,
    retry_delay_seconds=30,
    timeout_seconds=300,
)
def generate_area_statistics_task(
    output_file: Path | None = None,
    data_source: str = "bigquery",
    feature_context_path: Path | None = None,
    value_analysis_path: Path | None = None,
    raw_listings_path: Path | None = None,
) -> AnalyticsResult:
    """Generate area statistics for web application.

    Args:
        output_file: Path to write statistics
        data_source: Data source - "bigquery" or "json"
        feature_context_path: Path to feature_context.json
        value_analysis_path: Path to value_analysis.json
        raw_listings_path: Path to raw listings JSON

    Returns:
        AnalyticsResult with generation statistics
    """
    logger = get_task_logger(__name__)

    if output_file is None:
        output_file = Path("data/enrichment/area_statistics.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Generating area statistics from {data_source}")

    from estate_value_index.analytics.area_statistics import generate_area_statistics

    generate_area_statistics(
        data_source=data_source,
        feature_context_path=feature_context_path,
        value_analysis_path=value_analysis_path,
        raw_listings_path=raw_listings_path,
        output_path=output_file,
    )

    if not output_file.exists():
        raise FileNotFoundError(f"Output file not created: {output_file}")

    with open(output_file, encoding="utf-8") as f:
        stats = json.load(f)
        areas_count = len(stats.get("areas", []))

    logger.info(f"Area statistics generated: {areas_count} areas")

    return AnalyticsResult(
        success=True,
        timestamp=datetime.now().isoformat(),
        output_file=str(output_file),
        records_generated=areas_count,
    )


@task(
    name="generate-value-analysis",
    description="Generate property value analysis predictions",
    retries=2,
    retry_delay_seconds=30,
    timeout_seconds=600,
)
def generate_value_analysis_task(
    output_file: Path | None = None,
    data_file: Path | None = None,
    model_type: str = "lgbm",
    apply_training_filters: bool = False,
) -> AnalyticsResult:
    """Generate value analysis by running predictions on all properties.

    Args:
        output_file: Path to write analysis
        data_file: Input data file
        model_type: Model type to use
        apply_training_filters: Whether to apply training filters

    Returns:
        AnalyticsResult with generation statistics
    """
    logger = get_task_logger(__name__)

    if output_file is None:
        output_file = Path("data/enrichment/value_analysis.json")
    if data_file is None:
        data_file = Path("data/raw/booli/booli_listings_prod.json")

    output_file.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Generating value analysis from {data_file}")

    # Import the analysis function directly instead of using sys.argv patching
    from estate_value_index.analytics.value_analysis import run_analysis

    run_analysis(
        data_file=data_file,
        model_type=model_type,
        output_file=output_file,
        apply_training_filters=apply_training_filters,
    )

    if not output_file.exists():
        raise FileNotFoundError(f"Output file not created: {output_file}")

    with open(output_file, encoding="utf-8") as f:
        analysis = json.load(f)
        stats = analysis.get("statistics", {})
        properties_count = stats.get("total_properties", 0)

    logger.info(f"Value analysis generated: {properties_count} properties")

    return AnalyticsResult(
        success=True,
        timestamp=datetime.now().isoformat(),
        output_file=str(output_file),
        records_generated=properties_count,
    )


@task(
    name="upload-enrichment-to-gcs",
    description="Upload enrichment data to GCS for Cloud Run",
    retries=3,
    retry_delay_seconds=30,
    timeout_seconds=300,
)
def upload_enrichment_to_gcs_task(
    local_dir: Path,
    gcs_bucket: str,
    gcs_prefix: str = "enrichment/",
) -> dict:
    """Upload enrichment data to GCS.

    Args:
        local_dir: Local directory containing enrichment files
        gcs_bucket: GCS bucket name
        gcs_prefix: GCS prefix/path

    Returns:
        Upload statistics
    """
    logger = get_task_logger(__name__)

    logger.info(f"Uploading enrichment from {local_dir} to gs://{gcs_bucket}/{gcs_prefix}")

    client = get_storage_client()
    bucket = client.bucket(gcs_bucket)

    enrichment_files = list(local_dir.glob("*.json"))

    if not enrichment_files:
        logger.warning(f"No enrichment files found in {local_dir}")
        return {"success": True, "uploaded_files": 0, "files": []}

    uploaded_files = []
    for file_path in enrichment_files:
        blob_name = f"{gcs_prefix}{file_path.name}"
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(str(file_path))

        gcs_uri = f"gs://{gcs_bucket}/{blob_name}"
        uploaded_files.append(
            {
                "local_path": str(file_path),
                "gcs_uri": gcs_uri,
                "size_bytes": file_path.stat().st_size,
            }
        )
        logger.info(f"Uploaded: {file_path.name}")

    logger.info(f"Upload complete: {len(uploaded_files)} files")

    return {
        "success": True,
        "uploaded_files": len(uploaded_files),
        "files": uploaded_files,
        "bucket": gcs_bucket,
        "prefix": gcs_prefix,
        "timestamp": datetime.now().isoformat(),
    }
