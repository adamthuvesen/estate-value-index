#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Build and push the Vertex AI training container to Artifact Registry.

Usage:
  ./scripts/vertex_ai/build_and_push.sh [--image NAME] [--tag TAG] [--repo REPO] [--dry-run]

Flags:
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

while [[ $# -gt 0 ]]; do
  case "$1" in
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

PROJECT_ID=${GCP_PROJECT_ID:-estate-value-index}
REGION=${GCP_REGION:-europe-north1}
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
