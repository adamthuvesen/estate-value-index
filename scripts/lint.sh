#!/bin/bash
# Run shellcheck against the in-scope deployment / GCP scripts.
# Fails on any warning. SC1091 is suppressed because the optional shared
# preamble lib at scripts/lib/preamble.sh isn't always followable.

set -euo pipefail
IFS=$'\n\t'

# Resolve the repo root from this script's location, so it works from any CWD.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$REPO_ROOT"

IN_SCOPE=(
  scripts/cloud_run_disable.sh
  scripts/cloud_run_enable.sh
  scripts/deploy_cloud_run.sh
  scripts/setup_bigquery.sh
  scripts/setup_gcp.sh
  scripts/create_predictions_table.sh
)

if ! command -v shellcheck &> /dev/null; then
  echo "ERROR: shellcheck not installed. Install with: brew install shellcheck" >&2
  echo "       or apt-get install shellcheck" >&2
  exit 1
fi

echo "Running shellcheck on ${#IN_SCOPE[@]} script(s)..."
shellcheck -e SC1091 "${IN_SCOPE[@]}"
echo "shellcheck: clean"
