#!/usr/bin/env bash
# Plan or apply cloud artifact cleanup with rollback buffers.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# shellcheck source=lib/preamble.sh
source "${SCRIPT_DIR}/lib/preamble.sh"
# shellcheck source=lib/gcp_account.sh
source "${SCRIPT_DIR}/lib/gcp_account.sh"

cd "$ROOT_DIR"

APPLY="false"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply)
      APPLY="true"
      shift
      ;;
    --dry-run)
      APPLY="false"
      shift
      ;;
    *)
      echo "Usage: $0 [--dry-run|--apply]" >&2
      exit 2
      ;;
  esac
done

PROJECT_ID="${GCP_PROJECT_ID:-estate-value-index}"
REGION="${GCP_REGION:-europe-north1}"
BUCKET="${GCS_BUCKET:-estate-value-index-data-production}"
SERVICE_NAME="${CLOUD_RUN_SERVICE_NAME:-estate-value-index-app}"
SOURCE_BUCKET="${CLOUD_RUN_SOURCE_BUCKET:-run-sources-${PROJECT_ID}-${REGION}}"
APP_IMAGE="${APP_IMAGE:-gcr.io/${PROJECT_ID}/${SERVICE_NAME}}"
TRAINER_IMAGE="${TRAINER_IMAGE:-${REGION}-docker.pkg.dev/${PROJECT_ID}/vertex-training/lgbm-trainer}"

require_personal_gcloud_account

run_or_print() {
  if [[ "$APPLY" == "true" ]]; then
    "$@"
  else
    printf 'DRY RUN:'
    printf ' %q' "$@"
    printf '\n'
  fi
}

prune_gcs_listing() {
  local label="$1"
  local keep="$2"
  local recursive="$3"
  local pattern="$4"
  local count=0
  local uri

  echo ""
  echo "$label"
  while IFS= read -r uri; do
    [[ -z "$uri" ]] && continue
    count=$((count + 1))
    if (( count <= keep )); then
      echo "KEEP: $uri"
    elif [[ "$recursive" == "true" ]]; then
      run_or_print gcloud storage rm --recursive "$uri"
    else
      run_or_print gcloud storage rm "$uri"
    fi
  done < <(gcloud storage ls "$pattern" 2>/dev/null | sort -r || true)
}

prune_gcr_untagged() {
  local label="$1"
  local image="$2"
  local keep="$3"
  local count=0
  local digest

  echo ""
  echo "$label"
  while IFS= read -r digest; do
    [[ -z "$digest" ]] && continue
    count=$((count + 1))
    if (( count <= keep )); then
      echo "KEEP: ${image}@${digest}"
    else
      run_or_print gcloud container images delete "${image}@${digest}" --quiet
    fi
  done < <(
    gcloud container images list-tags "$image" \
      --filter='-tags:*' \
      --sort-by='~TIMESTAMP' \
      --format='value(digest)' 2>/dev/null || true
  )
}

echo "Cloud cleanup plan"
echo "  Apply:   $APPLY"
echo "  Project: $PROJECT_ID"
echo "  Region:  $REGION"
echo "  Bucket:  gs://$BUCKET"
echo "  Service: $SERVICE_NAME"

current_image="$(
  gcloud run services describe "$SERVICE_NAME" \
    --project "$PROJECT_ID" \
    --region "$REGION" \
    --format='value(spec.template.spec.containers[0].image)' 2>/dev/null || true
)"

echo ""
echo "Serving state"
echo "KEEP: current Cloud Run image: ${current_image:-unknown}"
echo "KEEP: serving model artifacts under gs://${BUCKET}/models/price_prediction_model_no_list_price*"
echo "KEEP: serving model artifacts under gs://${BUCKET}/models/price_prediction_model_with_list_price*"
gcloud storage ls "gs://${BUCKET}/models/price_prediction_model_no_list_price*" 2>/dev/null || true
gcloud storage ls "gs://${BUCKET}/models/price_prediction_model_with_list_price*" 2>/dev/null || true

prune_gcs_listing \
  "Vertex model run directories (keep latest 3)" \
  3 \
  true \
  "gs://${BUCKET}/vertex-ai/models/"

prune_gcs_listing \
  "Raw archive snapshots (keep latest 3)" \
  3 \
  false \
  "gs://${BUCKET}/raw/archive/*"

echo ""
echo "Derived files"
echo "KEEP: current derived files under gs://${BUCKET}/derived/"
gcloud storage ls "gs://${BUCKET}/derived/" 2>/dev/null || true

prune_gcr_untagged \
  "Cloud Run app image untagged digests (keep latest 1 untagged plus tagged/current images)" \
  "$APP_IMAGE" \
  1

echo ""
echo "Vertex trainer image review"
echo "KEEP: lgbm-trainer:latest and previous two trainer digests"
gcloud artifacts docker images list "$TRAINER_IMAGE" \
  --include-tags \
  --sort-by='~UPDATE_TIME' \
  --limit=10 2>/dev/null || true
echo "Review the trainer image list before deleting older untagged Artifact Registry digests."

echo ""
echo "Cloud Run source bucket zips (keep latest 2)"
if gcloud storage buckets describe "gs://${SOURCE_BUCKET}" >/dev/null 2>&1; then
  count=0
  while IFS= read -r uri; do
    [[ -z "$uri" ]] && continue
    count=$((count + 1))
    if (( count <= 2 )); then
      echo "KEEP: $uri"
    else
      run_or_print gcloud storage rm "$uri"
    fi
  done < <(gcloud storage ls "gs://${SOURCE_BUCKET}/**" 2>/dev/null | grep '\.zip$' | sort -r || true)
else
  echo "No source bucket found: gs://${SOURCE_BUCKET}"
fi

echo ""
echo "BigQuery"
echo "KEEP: ${PROJECT_ID}.booli_raw and ${PROJECT_ID}.booli_features"
echo "Hidden/temp datasets are audit-only here. Delete only if confirmed empty:"
bq ls -a --project_id "$PROJECT_ID" 2>/dev/null | awk '/^_/ {print "AUDIT: " $1}' || true
