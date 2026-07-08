#!/usr/bin/env bash
# Local/private one-time Booli catch-up path: scrape windows, merge, upload,
# feature-build, sync, retrain, deploy. Do not call this from public GitHub Actions.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# shellcheck source=lib/preamble.sh
source "${SCRIPT_DIR}/lib/preamble.sh"
# shellcheck source=lib/gcp_account.sh
source "${SCRIPT_DIR}/lib/gcp_account.sh"

cd "$ROOT_DIR"

is_true() {
  case "$1" in
    true | TRUE | True | 1 | yes | YES | Yes) return 0 ;;
    *) return 1 ;;
  esac
}

json_value() {
  local json_file="$1"
  local dotted_key="$2"
  uv run python - "$json_file" "$dotted_key" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as file:
    value = json.load(file)
for key in sys.argv[2].split("."):
    value = value[key]
print(value)
PY
}

validation_passed() {
  local json_file="$1"
  local threshold="$2"
  uv run python - "$json_file" "$threshold" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as file:
    summary = json.load(file)
rate = float(summary.get("validation", {}).get("validation_rate", 0.0))
threshold = float(sys.argv[2])
if rate < threshold:
    print(f"validation rate {rate:.1%} is below {threshold:.1%}", file=sys.stderr)
    raise SystemExit(1)
print(f"validation rate {rate:.1%}")
PY
}

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "ERROR: $name must be set when DRY_RUN=false." >&2
    exit 1
  fi
}

cloud_preflight() {
  echo "Running cloud preflight..."
  gcloud config set project "$GCP_PROJECT_ID" >/dev/null
  bq ls "${BIGQUERY_PROJECT_ID}:${BIGQUERY_DATASET_RAW}" >/dev/null
  bq ls "${BIGQUERY_PROJECT_ID}:${BIGQUERY_DATASET_FEATURES}" >/dev/null
  gcloud storage ls "gs://${GCS_BUCKET}" >/dev/null

  if is_true "$RUN_TRAIN_DEPLOY"; then
    local runtime_sa
    runtime_sa="${CLOUD_RUN_RUNTIME_SERVICE_ACCOUNT:-evi-cloud-run-runtime@${GCP_PROJECT_ID}.iam.gserviceaccount.com}"
    if ! gcloud iam service-accounts describe "$runtime_sa" --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
      echo "ERROR: Cloud Run runtime service account is missing: $runtime_sa" >&2
      echo "Create it first with scripts/setup_gcp.sh or run this catch-up with RUN_TRAIN_DEPLOY=false." >&2
      exit 1
    fi
  fi
}

run_backfill() {
  local label="$1"
  local start_date="$2"
  local max_pages="$3"
  local delay="$4"
  local output_dir="$5"
  local summary_file="$6"

  local command=(
    uv run python -m estate_value_index.cli --json backfill
    --base-config "$BACKFILL_BASE_CONFIG"
    --output-dir "$output_dir"
    --start-date "$start_date"
    --end-date "$BACKFILL_END"
    --window-days "$BACKFILL_WINDOW_DAYS"
    --max-pages "$max_pages"
    --concurrent "$BACKFILL_CONCURRENT"
    --delay "$delay"
    --source "$BACKFILL_SOURCE"
    --max-window-retries "$BACKFILL_MAX_WINDOW_RETRIES"
    --min-validation-rate "$BACKFILL_MIN_VALIDATION_RATE"
  )

  if is_true "$DRY_RUN"; then
    command+=(--dry-run)
  fi

  echo "Running ${label} backfill..."
  "${command[@]}" | tee "$summary_file"
}

RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
DRY_RUN="${DRY_RUN:-true}"
GCP_PROJECT_ID="${GCP_PROJECT_ID:-}"
BIGQUERY_PROJECT_ID="${BIGQUERY_PROJECT_ID:-$GCP_PROJECT_ID}"
GCP_REGION="${GCP_REGION:-europe-north1}"
GCS_BUCKET="${GCS_BUCKET:-}"
BIGQUERY_DATASET_RAW="${BIGQUERY_DATASET_RAW:-}"
BIGQUERY_TABLE_LISTINGS="${BIGQUERY_TABLE_LISTINGS:-}"
BIGQUERY_DATASET_FEATURES="${BIGQUERY_DATASET_FEATURES:-}"
BIGQUERY_TABLE_FEATURES="${BIGQUERY_TABLE_FEATURES:-}"
RUN_TRAIN_DEPLOY="${RUN_TRAIN_DEPLOY:-true}"
BACKFILL_BASE_CONFIG="${BACKFILL_BASE_CONFIG:-src/estate_value_index/ingestion/config/booli_all_locations.json}"
BACKFILL_SOURCE="${BACKFILL_SOURCE:-spider}"
BACKFILL_START="${BACKFILL_START:-2025-12-22}"
BACKFILL_END="${BACKFILL_END:-$(date -u +%Y-%m-%d)}"
if [[ -z "$BACKFILL_END" ]]; then
  BACKFILL_END="$(date -u +%Y-%m-%d)"
fi
BACKFILL_WINDOW_DAYS="${BACKFILL_WINDOW_DAYS:-7}"
BACKFILL_MAX_PAGES="${BACKFILL_MAX_PAGES:-20}"
BACKFILL_CONCURRENT="${BACKFILL_CONCURRENT:-1}"
BACKFILL_DELAY="${BACKFILL_DELAY:-1.0}"
BACKFILL_FALLBACK_START="${BACKFILL_FALLBACK_START:-2026-04-27}"
BACKFILL_FALLBACK_MAX_PAGES="${BACKFILL_FALLBACK_MAX_PAGES:-10}"
BACKFILL_FALLBACK_DELAY="${BACKFILL_FALLBACK_DELAY:-2.0}"
BACKFILL_MAX_WINDOW_RETRIES="${BACKFILL_MAX_WINDOW_RETRIES:-2}"
BACKFILL_MIN_VALIDATION_RATE="${BACKFILL_MIN_VALIDATION_RATE:-0.5}"
BACKFILL_OUTPUT_ROOT="${BACKFILL_OUTPUT_ROOT:-data/raw/booli}"
SUMMARY_DIR="${SUMMARY_DIR:-data/derived/backfill}"
PRODUCTION_FILE="${PRODUCTION_FILE:-data/raw/booli/booli_listings_prod.json}"

PRIMARY_OUTPUT_DIR="${BACKFILL_OUTPUT_ROOT}/catchup_primary_${RUN_ID}"
FALLBACK_OUTPUT_DIR="${BACKFILL_OUTPUT_ROOT}/catchup_recent_${RUN_ID}"
PRIMARY_SUMMARY="${SUMMARY_DIR}/catchup_primary_${RUN_ID}.json"
FALLBACK_SUMMARY="${SUMMARY_DIR}/catchup_recent_${RUN_ID}.json"

mkdir -p "$SUMMARY_DIR"

echo "Catch-up configuration"
echo "  Dry run:       $DRY_RUN"
echo "  Primary:       ${BACKFILL_START}..${BACKFILL_END}, max_pages=${BACKFILL_MAX_PAGES}, delay=${BACKFILL_DELAY}"
echo "  Fallback:      ${BACKFILL_FALLBACK_START}..${BACKFILL_END}, max_pages=${BACKFILL_FALLBACK_MAX_PAGES}, delay=${BACKFILL_FALLBACK_DELAY}"
echo "  Source:        $BACKFILL_SOURCE"
echo "  Window days:   $BACKFILL_WINDOW_DAYS"
echo "  Concurrent:    $BACKFILL_CONCURRENT"
echo "  Min valid:     $BACKFILL_MIN_VALIDATION_RATE"
echo "  Train/deploy:  $RUN_TRAIN_DEPLOY"
echo "  GCP project:   $GCP_PROJECT_ID"
echo "  GCS bucket:    $GCS_BUCKET"

if ! is_true "$DRY_RUN"; then
  require_env GCP_PROJECT_ID
  require_env BIGQUERY_PROJECT_ID
  require_env GCS_BUCKET
  require_env BIGQUERY_DATASET_RAW
  require_env BIGQUERY_TABLE_LISTINGS
  require_env BIGQUERY_DATASET_FEATURES
  require_env BIGQUERY_TABLE_FEATURES
  require_personal_gcloud_account
  export GCS_ENABLED="${GCS_ENABLED:-true}"
  export GCP_PROJECT_ID BIGQUERY_PROJECT_ID GCP_REGION GCS_BUCKET
  export BIGQUERY_DATASET_RAW BIGQUERY_TABLE_LISTINGS BIGQUERY_DATASET_FEATURES BIGQUERY_TABLE_FEATURES
  cloud_preflight
fi

if is_true "$DRY_RUN"; then
  run_backfill primary "$BACKFILL_START" "$BACKFILL_MAX_PAGES" "$BACKFILL_DELAY" "$PRIMARY_OUTPUT_DIR" "$PRIMARY_SUMMARY"
  run_backfill fallback "$BACKFILL_FALLBACK_START" "$BACKFILL_FALLBACK_MAX_PAGES" "$BACKFILL_FALLBACK_DELAY" "$FALLBACK_OUTPUT_DIR" "$FALLBACK_SUMMARY"
  echo "Dry run complete. No BigQuery, GCS, Vertex, or Cloud Run changes were made."
  exit 0
fi

selected_summary=""
if run_backfill primary "$BACKFILL_START" "$BACKFILL_MAX_PAGES" "$BACKFILL_DELAY" "$PRIMARY_OUTPUT_DIR" "$PRIMARY_SUMMARY" \
  && validation_passed "$PRIMARY_SUMMARY" "$BACKFILL_MIN_VALIDATION_RATE"; then
  selected_summary="$PRIMARY_SUMMARY"
else
  echo "Primary backfill failed or validation dropped below threshold. Trying recent fallback..."
  run_backfill fallback "$BACKFILL_FALLBACK_START" "$BACKFILL_FALLBACK_MAX_PAGES" "$BACKFILL_FALLBACK_DELAY" "$FALLBACK_OUTPUT_DIR" "$FALLBACK_SUMMARY"
  validation_passed "$FALLBACK_SUMMARY" "$BACKFILL_MIN_VALIDATION_RATE"
  selected_summary="$FALLBACK_SUMMARY"
fi

merged_file="$(json_value "$selected_summary" "merge.output_file")"
if [[ ! -s "$merged_file" ]]; then
  echo "ERROR: merged backfill file is missing or empty: $merged_file" >&2
  exit 1
fi

echo "Processing merged backfill: $merged_file"
uv run python -m estate_value_index.cli process \
  --input "$merged_file" \
  --production "$PRODUCTION_FILE"

echo "Uploading processed listings through BigQuery append/merge path..."
uv run python -m estate_value_index.cli migrate --data-file "$PRODUCTION_FILE"

echo "Materializing engineered features with truncate..."
uv run python -m estate_value_index.cli features --truncate

echo "Syncing BigQuery back to local file and GCS backup..."
uv run python - "$PRODUCTION_FILE" <<'PY'
from pathlib import Path
import sys

from estate_value_index.pipelines.tasks.sync import (
    sync_bigquery_to_local_task,
    sync_local_to_gcs_task,
    verify_sync_task,
)

local_file = Path(sys.argv[1])
sync_result = sync_bigquery_to_local_task.fn(output_file=local_file, backup_existing=True)
verify_result = verify_sync_task.fn(local_file=local_file)
gcs_result = sync_local_to_gcs_task.fn(local_file=local_file)

print(f"Synced {sync_result['records_synced']} rows to {local_file}")
print(f"BigQuery/local in sync: {verify_result['in_sync']}")
print(f"GCS backup: {gcs_result['destination']}")

if not verify_result["in_sync"]:
    raise SystemExit("BigQuery/local sync check failed")
PY

if is_true "$RUN_TRAIN_DEPLOY"; then
  echo "Retraining on Vertex and deploying only after validation passes..."
  uv run python -m estate_value_index.pipelines.core.complete_pipeline --retrain --tune --deploy
else
  echo "Skipping retrain/deploy because RUN_TRAIN_DEPLOY=false"
fi

echo "Catch-up complete"
echo "  Summary: $selected_summary"
echo "  Merged:  $merged_file"
