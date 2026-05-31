#!/bin/bash
# Re-enable Cloud Run service by redeploying.
# Uses cached container images from GCR (fast deployment).

set -euo pipefail
IFS=$'\n\t'

# Resolve sibling scripts via absolute path so this works regardless of CWD.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_SCRIPT="${SCRIPT_DIR}/deploy_cloud_run.sh"

if [[ ! -x "$DEPLOY_SCRIPT" ]]; then
  echo "ERROR: deploy script not found or not executable: $DEPLOY_SCRIPT" >&2
  exit 1
fi

echo "=========================================="
echo "Re-enabling Cloud Run Service"
echo "=========================================="
echo ""
echo "This will redeploy the service using the"
echo "existing container image from GCR."
echo ""
echo "Estimated time: ~2 minutes"
echo "=========================================="
echo ""

# Run the standard deployment script
"$DEPLOY_SCRIPT" "$@"
