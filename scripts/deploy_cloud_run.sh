#!/bin/bash
# Deploy Estate Value Index to Cloud Run.
# Builds and deploys the unified container (Next.js + FastAPI).

set -euo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/gcp_account.sh
source "${SCRIPT_DIR}/lib/gcp_account.sh"

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-}"
REGION="${GCP_REGION:-europe-north1}"
SERVICE_NAME="estate-value-index-app"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"
GCS_BUCKET="${GCS_BUCKET:-}"
# Dedicated least-privilege runtime identity (GCS read only, no BigQuery). Created
# by scripts/setup_gcp.sh. Override only to point at another GCS-read-only account.
RUNTIME_SERVICE_ACCOUNT="${RUNTIME_SERVICE_ACCOUNT:-evi-cloud-run-runtime@${PROJECT_ID}.iam.gserviceaccount.com}"

: "${PROJECT_ID:?PROJECT_ID is required}"
: "${REGION:?REGION is required}"
: "${SERVICE_NAME:?SERVICE_NAME is required}"
: "${GCS_BUCKET:?GCS_BUCKET is required}"

echo "=========================================="
echo "Cloud Run Deployment"
echo "=========================================="
echo "Project: $PROJECT_ID"
echo "Region:  $REGION"
echo "Service: $SERVICE_NAME"
echo "Image:   $IMAGE_NAME"
echo ""
echo "Runtime SA: $RUNTIME_SERVICE_ACCOUNT"
echo ""
echo "Configuration:"
echo "  - Health check: /api/health (verifies Next.js + FastAPI)"
echo "  - Startup grace period: 240s"
echo "  - CPU boost: enabled (faster model loading)"
echo "  - No CPU throttling (consistent performance)"
echo "=========================================="
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "ERROR: gcloud CLI not found" >&2
    exit 1
fi

require_personal_gcloud_account

# Set project
gcloud config set project "$PROJECT_ID"

# Refuse to deploy without the dedicated least-privilege runtime SA. Without
# --service-account, Cloud Run runs as the default compute SA (project Editor),
# which would give this public, unauthenticated service full BigQuery access it
# does not need. The runtime SA reads model artifacts from GCS and nothing else.
echo ""
echo "Verifying runtime service account exists..."
if ! gcloud iam service-accounts describe "$RUNTIME_SERVICE_ACCOUNT" &> /dev/null; then
    echo "ERROR: runtime service account '$RUNTIME_SERVICE_ACCOUNT' not found." >&2
    echo "Create it first (least privilege, GCS read only) by running" >&2
    echo "scripts/setup_gcp.sh, or set RUNTIME_SERVICE_ACCOUNT to an existing" >&2
    echo "account that has only GCS object-read on gs://${GCS_BUCKET}." >&2
    exit 1
fi

# Enable required APIs
echo "Ensuring required APIs are enabled..."
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable containerregistry.googleapis.com

# Build container image using Cloud Build
echo ""
echo "Building container image..."
gcloud builds submit --tag "$IMAGE_NAME"

# Deploy to Cloud Run
echo ""
echo "Deploying to Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
  --image "$IMAGE_NAME" \
  --platform managed \
  --region "$REGION" \
  --service-account "$RUNTIME_SERVICE_ACCOUNT" \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 2 \
  --memory 2Gi \
  --cpu 2 \
  --timeout 900s \
  --port 8080 \
  --ingress internal \
  --set-env-vars "GCS_ENABLED=true,GCS_BUCKET=${GCS_BUCKET},NODE_ENV=production,PREDICTION_API_URL=http://127.0.0.1:8000" \
  --no-cpu-throttling \
  --cpu-boost

# Get the service URL
SERVICE_URL="$(gcloud run services describe "$SERVICE_NAME" \
  --platform managed \
  --region "$REGION" \
  --format 'value(status.url)')"

echo ""
echo "=========================================="
echo "Deployment Complete"
echo "=========================================="
echo ""
echo "Service URL: $SERVICE_URL"
echo ""
echo "Test the deployment:"
echo "  Internal ingress is enabled; direct laptop curl is expected to fail."
echo "  Check readiness with Cloud Run logs or from an allowed internal network:"
echo "  gcloud run logs tail $SERVICE_NAME --region $REGION"
echo ""
echo "View logs:"
echo "  gcloud run logs tail $SERVICE_NAME --region $REGION"
echo ""
echo "Update environment variables:"
echo "  CLOUD_RUN_URL=$SERVICE_URL"
echo ""
echo "=========================================="
