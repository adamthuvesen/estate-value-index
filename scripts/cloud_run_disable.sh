#!/bin/bash
# Disable Cloud Run service by deleting it completely
# Note: Container images remain in GCR for fast redeployment
#
# Usage:
#   ./scripts/cloud_run_disable.sh           # interactive (prompts)
#   ./scripts/cloud_run_disable.sh --yes     # non-interactive (CI / automation)

set -euo pipefail
IFS=$'\n\t'

AUTO_YES=0
for arg in "$@"; do
  case "$arg" in
    --yes|-y) AUTO_YES=1 ;;
    -h|--help)
      sed -n '2,7p' "$0"
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

PROJECT_ID="${GCP_PROJECT_ID:-estate-value-index}"
REGION="${GCP_REGION:-europe-north1}"
SERVICE_NAME="estate-value-index-app"

: "${SERVICE_NAME:?SERVICE_NAME is required}"
: "${REGION:?REGION is required}"
: "${PROJECT_ID:?PROJECT_ID is required}"

echo "=========================================="
echo "Disabling Cloud Run Service"
echo "=========================================="
echo "Project: $PROJECT_ID"
echo "Region:  $REGION"
echo "Service: $SERVICE_NAME"
echo ""
echo "WARNING: this will DELETE the service."
echo "Container images remain in GCR for redeployment."
echo "=========================================="
echo ""

# Show what's about to be deleted (best-effort; missing service is fine).
if gcloud run services describe "$SERVICE_NAME" \
    --region "$REGION" \
    --project "$PROJECT_ID" \
    --format='value(metadata.name,status.url)' 2>/dev/null; then
  :
else
  echo "(service not found — describe failed; proceeding to confirmation anyway)"
fi
echo ""

if [[ "$AUTO_YES" -eq 1 ]]; then
  echo "--yes passed; skipping interactive confirmation."
elif [[ -t 0 ]]; then
  read -rp "Continue? (y/N) " -n 1 REPLY
  echo
  if [[ ! "$REPLY" =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 1
  fi
else
  echo "ERROR: refusing to delete in non-interactive mode without --yes" >&2
  exit 2
fi

# Delete the service completely
gcloud run services delete "$SERVICE_NAME" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --quiet

echo ""
echo "=========================================="
echo "Service Deleted"
echo "=========================================="
echo ""
echo "The service has been completely removed."
echo "Cost: \$0 (container images: ~\$0.02/month in GCR)"
echo ""
echo "To redeploy: ./scripts/cloud_run_enable.sh"
echo "Redeployment uses cached images (~2 min)"
echo "=========================================="
