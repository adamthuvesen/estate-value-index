#!/bin/bash
# Create BigQuery predictions table for drift monitoring.

set -euo pipefail
IFS=$'\n\t'

PROJECT_ID="${GCP_PROJECT_ID:-estate-value-index}"
DATASET="booli_raw"
TABLE="predictions"
SCHEMA_FILE="schemas/predictions_table.json"

: "${PROJECT_ID:?PROJECT_ID is required}"
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
