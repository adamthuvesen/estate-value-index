#!/bin/bash
# Set up BigQuery datasets and tables for Estate Value Index.

set -euo pipefail
IFS=$'\n\t'

usage() {
  cat <<'USAGE'
Set up BigQuery datasets and tables for Estate Value Index.

Usage:
  ./scripts/setup_bigquery.sh --project PROJECT [--region REGION]

Flags:
  --project PROJECT  GCP project ID (default: $GCP_PROJECT_ID)
  --region REGION    GCP region (default: $GCP_REGION or europe-north1)
USAGE
}

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-}"
REGION="${GCP_REGION:-europe-north1}"
DATASET_RAW="booli_raw"
DATASET_FEATURES="booli_features"
SCHEMA_DIR="schemas"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      PROJECT_ID=${2:?"--project requires a value"}
      shift 2
      ;;
    --region)
      REGION=${2:?"--region requires a value"}
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

: "${PROJECT_ID:?GCP project is required; pass --project or set GCP_PROJECT_ID}"
: "${DATASET_RAW:?DATASET_RAW is required}"
: "${DATASET_FEATURES:?DATASET_FEATURES is required}"

echo "Setting up BigQuery for project: $PROJECT_ID"
echo "Region: $REGION"

# Set active project
gcloud config set project "$PROJECT_ID"

# Create booli_raw dataset
echo "Ensuring dataset exists: $DATASET_RAW"
if bq --project_id="$PROJECT_ID" show --dataset "${PROJECT_ID}:${DATASET_RAW}" &> /dev/null; then
  echo "  Dataset $DATASET_RAW already exists, skipping"
else
  bq mk --location=EU --dataset "${PROJECT_ID}:${DATASET_RAW}"
  echo "  Created dataset $DATASET_RAW"
fi

# Create booli_features dataset
echo "Ensuring dataset exists: $DATASET_FEATURES"
if bq --project_id="$PROJECT_ID" show --dataset "${PROJECT_ID}:${DATASET_FEATURES}" &> /dev/null; then
  echo "  Dataset $DATASET_FEATURES already exists, skipping"
else
  bq mk --location=EU --dataset "${PROJECT_ID}:${DATASET_FEATURES}"
  echo "  Created dataset $DATASET_FEATURES"
fi

# Create booli_raw.listings table
LISTINGS_SCHEMA="${SCHEMA_DIR}/bq_raw_listings.json"
if [[ ! -f "$LISTINGS_SCHEMA" ]]; then
  echo "ERROR: schema file not found: $LISTINGS_SCHEMA" >&2
  exit 1
fi

echo "Ensuring table exists: $DATASET_RAW.listings"
if bq --project_id="$PROJECT_ID" show "${PROJECT_ID}:${DATASET_RAW}.listings" &> /dev/null; then
  echo "  Table $DATASET_RAW.listings already exists, skipping"
else
  bq mk --table \
    --time_partitioning_field scraped_at_date \
    --time_partitioning_type DAY \
    --clustering_fields area,rooms \
    "${PROJECT_ID}:${DATASET_RAW}.listings" \
    "$LISTINGS_SCHEMA"
  echo "  Created table $DATASET_RAW.listings"
fi

echo "BigQuery setup complete."
echo ""
echo "Verifying setup..."
bq ls "${PROJECT_ID}:${DATASET_RAW}"
bq ls "${PROJECT_ID}:${DATASET_FEATURES}"
echo ""
echo "Schema for $DATASET_RAW.listings:"
bq show --schema "${PROJECT_ID}:${DATASET_RAW}.listings"
