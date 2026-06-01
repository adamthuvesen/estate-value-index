#!/bin/bash
# Create BigQuery predictions table for drift monitoring.

set -euo pipefail
IFS=$'\n\t'

usage() {
  cat <<'USAGE'
Create BigQuery predictions table for drift monitoring.

Usage:
  ./scripts/create_predictions_table.sh --project PROJECT

Flags:
  --project PROJECT  BigQuery project ID (default: $BIGQUERY_PROJECT_ID, then $GCP_PROJECT_ID)
USAGE
}

PROJECT_ID="${BIGQUERY_PROJECT_ID:-${GCP_PROJECT_ID:-}}"
DATASET="booli_raw"
TABLE="predictions"
SCHEMA_FILE="schemas/predictions_table.json"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      PROJECT_ID=${2:?"--project requires a value"}
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

: "${PROJECT_ID:?BigQuery project is required; pass --project or set BIGQUERY_PROJECT_ID/GCP_PROJECT_ID}"
: "${DATASET:?DATASET is required}"
: "${TABLE:?TABLE is required}"

TARGET="${PROJECT_ID}:${DATASET}.${TABLE}"

echo "Creating BigQuery table: $TARGET"

# Check if schema file exists
if [[ ! -f "$SCHEMA_FILE" ]]; then
    echo "ERROR: schema file not found: $SCHEMA_FILE" >&2
    exit 1
fi

# Skip if table already exists (idempotent).
if bq --project_id="$PROJECT_ID" show "$TARGET" &> /dev/null; then
    echo "Table $TARGET already exists, skipping creation"
else
    bq mk \
      --table \
      --time_partitioning_field prediction_timestamp \
      --time_partitioning_type DAY \
      --clustering_fields area,model_version \
      --schema "$SCHEMA_FILE" \
      "$TARGET"
    echo "Table created successfully"
fi

# Verify table state
bq show "$TARGET"
