#!/bin/bash
# GCP Setup Script for Estate Value Index project.
# Sets up the necessary GCP resources for production deployment.

set -euo pipefail
IFS=$'\n\t'

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-}"
REGION="${GCP_REGION:-europe-north1}"
BUCKET_NAME="${GCS_BUCKET:-}"
SERVICE_ACCOUNT_NAME="estate-value-index-service-acc"
SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

: "${PROJECT_ID:?PROJECT_ID is required}"
: "${REGION:?REGION is required}"
: "${BUCKET_NAME:?BUCKET_NAME is required}"
: "${SERVICE_ACCOUNT_NAME:?SERVICE_ACCOUNT_NAME is required}"

echo "=========================================="
echo "GCP Setup for Estate Value Index"
echo "=========================================="
echo "Project ID: $PROJECT_ID"
echo "Region:     $REGION"
echo "Bucket:     $BUCKET_NAME"
echo "=========================================="
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "ERROR: gcloud CLI not found. Install from: https://cloud.google.com/sdk/docs/install" >&2
    exit 1
fi

echo "gcloud CLI found"

# Set project
echo ""
echo "Setting active project..."
gcloud config set project "$PROJECT_ID"

# Enable required APIs
echo ""
echo "Enabling required Google Cloud APIs..."
gcloud services enable storage.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable cloudscheduler.googleapis.com
gcloud services enable secretmanager.googleapis.com
gcloud services enable artifactregistry.googleapis.com

echo "APIs enabled"

# Create GCS bucket
echo ""
echo "Creating Cloud Storage bucket..."
if gsutil ls -b "gs://${BUCKET_NAME}" &> /dev/null; then
    echo "Bucket gs://${BUCKET_NAME} already exists, skipping creation"
else
    gsutil mb -p "$PROJECT_ID" -l "$REGION" "gs://${BUCKET_NAME}"
    echo "Created bucket gs://${BUCKET_NAME}"
fi

# Set bucket lifecycle (delete old files to save costs)
echo ""
echo "Setting bucket lifecycle policy..."
LIFECYCLE_FILE="$(mktemp -t evi-lifecycle.XXXXXX.json)"
trap 'rm -f "$LIFECYCLE_FILE"' EXIT

cat > "$LIFECYCLE_FILE" <<'EOF'
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "Delete"},
        "condition": {
          "age": 90,
          "matchesPrefix": ["raw/"]
        }
      }
    ]
  }
}
EOF

gsutil lifecycle set "$LIFECYCLE_FILE" "gs://${BUCKET_NAME}"
echo "Lifecycle policy set (delete files in raw/ after 90 days)"

# Create bucket directories
echo ""
echo "Creating bucket directory structure..."
echo "" | gsutil cp - "gs://${BUCKET_NAME}/raw/.keep"
echo "" | gsutil cp - "gs://${BUCKET_NAME}/models/.keep"
echo "" | gsutil cp - "gs://${BUCKET_NAME}/derived/.keep"
echo "Directory structure created"

# Create service account for automation
echo ""
echo "Creating service account..."
if gcloud iam service-accounts describe "$SERVICE_ACCOUNT_EMAIL" &> /dev/null; then
    echo "Service account already exists, skipping creation"
else
    gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
        --display-name="Booli Service Account" \
        --description="Service account for automated data pipelines and Cloud Run"
    echo "Created service account: $SERVICE_ACCOUNT_EMAIL"
fi

# Grant necessary permissions
echo ""
echo "Granting permissions to service account..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/storage.objectAdmin" \
    --condition=None \
    --quiet

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/run.admin" \
    --condition=None \
    --quiet

echo "Permissions granted"

# Dedicated, least-privilege runtime identity for the public Cloud Run service.
# The API/web container only reads model artifacts from GCS — it never touches
# BigQuery — so this account gets object-read on the bucket and nothing else: no
# project Editor, no BigQuery. Running the public service under it means even a
# compromise of the request path cannot reach BigQuery, because the attached
# credentials cannot. deploy_cloud_run.sh attaches it via --service-account.
RUNTIME_SA_NAME="evi-cloud-run-runtime"
RUNTIME_SA_EMAIL="${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

echo ""
echo "Creating Cloud Run runtime service account (least privilege)..."
if gcloud iam service-accounts describe "$RUNTIME_SA_EMAIL" &> /dev/null; then
    echo "Runtime service account already exists, skipping creation"
else
    gcloud iam service-accounts create "$RUNTIME_SA_NAME" \
        --display-name="EVI Cloud Run runtime" \
        --description="Runtime identity for the public Cloud Run service; GCS read only, no BigQuery"
    echo "Created runtime service account: $RUNTIME_SA_EMAIL"
fi

echo "Granting bucket-scoped object read to the runtime SA (no project-wide roles)..."
gsutil iam ch "serviceAccount:${RUNTIME_SA_EMAIL}:roles/storage.objectViewer" "gs://${BUCKET_NAME}"

echo "Allowing the automation SA to deploy Cloud Run as the runtime SA..."
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA_EMAIL" \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/iam.serviceAccountUser" \
    --quiet

echo "Runtime service account ready (GCS read only; no BigQuery, no Editor)"

# Create service account key for local development
echo ""
echo "Creating service account key for local development..."
KEY_FILE="${HOME}/.gcp/${PROJECT_ID}-service-account-key.json"
mkdir -p "${HOME}/.gcp"

if [[ -f "$KEY_FILE" ]]; then
    echo "Key file already exists at $KEY_FILE"
    if [[ -t 0 ]]; then
        read -rp "Do you want to create a new key? (y/N) " -n 1 REPLY
        echo
        if [[ "$REPLY" =~ ^[Yy]$ ]]; then
            gcloud iam service-accounts keys create "$KEY_FILE" \
                --iam-account="$SERVICE_ACCOUNT_EMAIL"
            echo "New service account key created: $KEY_FILE"
        fi
    else
        echo "Non-interactive run; keeping existing key file."
    fi
else
    gcloud iam service-accounts keys create "$KEY_FILE" \
        --iam-account="$SERVICE_ACCOUNT_EMAIL"
    echo "Service account key created: $KEY_FILE"
fi

# Set environment variable
echo ""
echo "Setting up environment variables..."
echo ""
echo "Add these to your .env or shell profile:"
echo "----------------------------------------"
echo "export GOOGLE_APPLICATION_CREDENTIALS=\"$KEY_FILE\""
echo "export GCP_PROJECT_ID=\"$PROJECT_ID\""
echo "export GCS_BUCKET=\"$BUCKET_NAME\""
echo "export GCS_ENABLED=\"true\""
echo "export GCP_REGION=\"$REGION\""
echo "----------------------------------------"

# Create .env file
if [[ ! -f ".env" ]]; then
    cat > .env <<EOF
# GCP Configuration
GOOGLE_APPLICATION_CREDENTIALS=$KEY_FILE
GCP_PROJECT_ID=$PROJECT_ID
GCS_BUCKET=$BUCKET_NAME
GCS_ENABLED=true
GCP_REGION=$REGION

# Cloud Run Configuration (will be set after deployment)
# CLOUD_RUN_URL=https://estate-value-index-app-xxx.run.app
EOF
    echo ""
    echo "Created .env file with GCP configuration"
else
    echo ""
    echo ".env file already exists, skipping creation"
fi

# Setup budget alerts
echo ""
echo "Budget alerts recommendation:"
echo "Visit: https://console.cloud.google.com/billing/budgets?project=$PROJECT_ID"
echo "Create alerts at: \$5, \$10, \$20/month"

# Summary
echo ""
echo "=========================================="
echo "GCP Setup Complete"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Source the environment variables:"
echo "   source .env"
echo ""
echo "2. Test GCS access:"
echo "   gsutil ls gs://$BUCKET_NAME"
echo ""
echo "3. Upload training data to GCS:"
echo "   gsutil cp data/raw/booli/booli_listings_prod.json gs://$BUCKET_NAME/raw/"
echo ""
echo "4. Train model with GCS:"
echo "   GCS_ENABLED=true uv run python -m estate_value_index.cli train-production-models --data-source bigquery --model-dir web/models"
echo ""
echo "5. Setup budget alerts at:"
echo "   https://console.cloud.google.com/billing/budgets?project=$PROJECT_ID"
echo ""
echo "=========================================="
