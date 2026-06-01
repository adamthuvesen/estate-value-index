#!/bin/bash
# Deploy Estate Value Index to Cloud Run.
# Builds and deploys the unified container (Next.js + FastAPI).

set -euo pipefail
IFS=$'\n\t'

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-}"
REGION="${GCP_REGION:-europe-north1}"
SERVICE_NAME="estate-value-index-app"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"
GCS_BUCKET="${GCS_BUCKET:-}"

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
echo "Configuration:"
echo "  - Health check: /api/health (verifies Next.js + FastAPI)"
echo "  - Startup grace period: 120s"
echo "  - CPU boost: enabled (faster model loading)"
echo "  - No CPU throttling (consistent performance)"
echo "=========================================="
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "ERROR: gcloud CLI not found" >&2
    exit 1
fi

# Set project
gcloud config set project "$PROJECT_ID"

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
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 2 \
  --memory 2Gi \
  --cpu 2 \
  --timeout 900s \
  --port 8080 \
  --set-env-vars "GCS_ENABLED=true,GCS_BUCKET=${GCS_BUCKET},NODE_ENV=production,PREDICTION_API_URL=http://127.0.0.1:8000,TRUST_PROXY_HEADERS=true" \
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
echo "  curl $SERVICE_URL"
echo ""
echo "View logs:"
echo "  gcloud run logs tail $SERVICE_NAME --region $REGION"
echo ""
echo "Update environment variables:"
echo "  CLOUD_RUN_URL=$SERVICE_URL"
echo ""
echo "=========================================="
