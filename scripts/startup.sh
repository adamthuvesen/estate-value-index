#!/bin/bash
set -euo pipefail

echo "[STARTUP] Starting Estate Value Index services..."

# Configuration
GCS_ENABLED="${GCS_ENABLED:-false}"
MODEL_DIR="${MODEL_DIR:-/app/web/models}"
ENRICHMENT_DIR="${ENRICHMENT_DIR:-/app/data/derived}"
START_SERVICES="${START_SERVICES:-true}"
REQUIRED_MODELS=(
    "price_prediction_model_no_list_price.joblib"
    "price_prediction_model_with_list_price.joblib"
)

# Function to download from GCS.
#
# Args:
#   $1 — GCS prefix (e.g. "models/")
#   $2 — local destination directory
#   $3 — human-readable description
#   $4 — "required" or "optional" (default: "optional")
#
# Behaviour:
#   - "required": on rsync failure, log a single FATAL: line and exit 1.
#   - "optional": on rsync failure, log a warning and return non-zero (caller
#                 may continue).
download_from_gcs() {
    local gcs_path="$1"
    local local_dir="$2"
    local description="$3"
    local requirement="${4:-optional}"

    echo "[STARTUP] Downloading ${description} from gs://${GCS_BUCKET}/${gcs_path}..."

    if gsutil -m rsync -r "gs://${GCS_BUCKET}/${gcs_path}" "${local_dir}" 2>&1; then
        echo "[STARTUP] ${description} downloaded successfully"
        return 0
    fi

    if [ "${requirement}" = "required" ]; then
        echo "FATAL: required ${description} download failed (gs://${GCS_BUCKET}/${gcs_path}). Refusing to start." >&2
        exit 1
    fi

    echo "[STARTUP] WARNING: optional ${description} download failed; continuing without it" >&2
    return 1
}

# Create directories if they don't exist.
mkdir -p "${MODEL_DIR}"
mkdir -p "${ENRICHMENT_DIR}"

if [ "${GCS_ENABLED}" = "true" ]; then
    : "${GCS_BUCKET:?GCS_BUCKET is required when GCS_ENABLED=true}"

    # Download model artifacts from GCS — required.
    download_from_gcs "models/" "${MODEL_DIR}" "model artifacts" "required"

    # Download enrichment data from GCS — optional (degrade gracefully).
    download_from_gcs "derived/" "${ENRICHMENT_DIR}" "enrichment data" "optional" || true
else
    echo "[STARTUP] GCS_ENABLED=false; using local runtime artifacts"
fi

# List downloaded files for verification.
echo "[STARTUP] Model files:"
ls -lh "${MODEL_DIR}" || echo "  (empty)"

echo "[STARTUP] Enrichment files:"
ls -lh "${ENRICHMENT_DIR}" || echo "  (empty)"

sha256_file() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | cut -d' ' -f1
    else
        shasum -a 256 "$1" | cut -d' ' -f1
    fi
}

bad_sidecars=()
for model_name in "${REQUIRED_MODELS[@]}"; do
    joblib_file="${MODEL_DIR}/${model_name}"
    sidecar="${joblib_file}.sha256"
    if [ ! -f "${joblib_file}" ]; then
        bad_sidecars+=("${model_name}: model missing")
        continue
    fi
    if [ ! -f "${sidecar}" ]; then
        bad_sidecars+=("${model_name}: sidecar missing")
        continue
    fi
    expected="$(cut -d' ' -f1 <"${sidecar}")"
    observed="$(sha256_file "${joblib_file}")"
    if [ "${expected}" != "${observed}" ]; then
        bad_sidecars+=("${model_name}: sha256 mismatch (sidecar ${expected:0:12}..., file ${observed:0:12}...)")
    fi
done

if [ "${#bad_sidecars[@]}" -gt 0 ]; then
    echo "FATAL: required production model artifact problem(s):" >&2
    for bad in "${bad_sidecars[@]}"; do
        echo "  - ${bad}" >&2
    done
    echo "Re-run the deployment upload step or roll back to a previous artefact." >&2
    exit 1
fi

echo "[STARTUP] Preflight OK: ${#REQUIRED_MODELS[@]} required model artefact(s) with verified sidecars"
echo "[STARTUP] Data download complete, starting services..."

if [ "${START_SERVICES}" = "false" ]; then
    echo "[STARTUP] START_SERVICES=false; preflight complete"
    exit 0
fi

# Start supervisor to run Next.js and FastAPI.
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
