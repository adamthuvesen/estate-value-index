#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Build and push the Vertex AI training container to Artifact Registry.

Usage:
  ./vertex_ai/build_and_push.sh --project PROJECT [--region REGION] [--image NAME] [--tag TAG] [--repo REPO] [--dry-run]

Flags:
  --project PROJECT  GCP project ID (default: $GCP_PROJECT_ID)
  --region REGION    Artifact Registry / Cloud Build region (default: $GCP_REGION or europe-north1)
  --image NAME    Container image name (default: lgbm-trainer)
  --tag TAG       Container tag (default: latest)
  --repo REPO     Artifact Registry repo (default: vertex-training)
  --dry-run       Print commands without executing them
USAGE
}

IMAGE_NAME="lgbm-trainer"
IMAGE_TAG="latest"
REPO_NAME="vertex-training"
DRY_RUN=false
PROJECT_ID="${GCP_PROJECT_ID:-}"
REGION="${GCP_REGION:-europe-north1}"

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
    --image)
      IMAGE_NAME=${2:?"--image requires a value"}
      shift 2
      ;;
    --tag)
      IMAGE_TAG=${2:?"--tag requires a value"}
      shift 2
      ;;
    --repo)
      REPO_NAME=${2:?"--repo requires a value"}
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown flag: $1" >&2
      usage
      exit 1
      ;;
  esac
done

: "${PROJECT_ID:?GCP project is required; pass --project or set GCP_PROJECT_ID}"
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:${IMAGE_TAG}"

CMD=(gcloud builds submit --project "$PROJECT_ID" --region "$REGION" --config vertex_ai/cloudbuild.yaml --substitutions "_IMAGE_URI=${IMAGE_URI}" .)

echo "Building and pushing image: $IMAGE_URI"

if [[ "$DRY_RUN" == true ]]; then
  printf 'DRY RUN: '
  printf '%q ' "${CMD[@]}"
  printf '\n'
else
  "${CMD[@]}"
fi
