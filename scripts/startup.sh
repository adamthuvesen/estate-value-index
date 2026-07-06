#!/bin/bash
set -euo pipefail

echo "[STARTUP] Starting Estate Value Index services..."

# Configuration
: "${GCS_BUCKET:?GCS_BUCKET is required when syncing runtime artifacts from GCS}"
MODEL_DIR="/app/web/models"
ENRICHMENT_DIR="/app/data/derived"

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

# Download model artifacts from GCS — required.
download_from_gcs "models/" "${MODEL_DIR}" "model artifacts" "required"

# Download enrichment data from GCS — optional (degrade gracefully).
download_from_gcs "derived/" "${ENRICHMENT_DIR}" "enrichment data" "optional" || true

# List downloaded files for verification.
echo "[STARTUP] Model files:"
ls -lh "${MODEL_DIR}" || echo "  (empty)"

echo "[STARTUP] Enrichment files:"
ls -lh "${ENRICHMENT_DIR}" || echo "  (empty)"

# Preflight: at least one *.joblib must be present, and every *.joblib must
# have a matching *.joblib.sha256 sidecar. A missing sidecar means the upload
# pipeline is broken; surface that loudly here rather than letting the API
# server boot into a no-models 503 loop.
shopt -s nullglob
joblib_files=("${MODEL_DIR}"/*.joblib)
shopt -u nullglob

if [ "${#joblib_files[@]}" -eq 0 ]; then
    echo "FATAL: no *.joblib files present in ${MODEL_DIR} after rsync (gs://${GCS_BUCKET}/models/). Refusing to start." >&2
    exit 1
fi

bad_sidecars=()
for joblib_file in "${joblib_files[@]}"; do
    sidecar="${joblib_file}.sha256"
    if [ ! -f "${sidecar}" ]; then
        bad_sidecars+=("${joblib_file##*/}: sidecar missing")
        continue
    fi
    # Verify content, not just existence: a stale sidecar (e.g. a joblib promoted
    # without its sidecar) otherwise boots into a no-models 503 loop.
    expected="$(cut -d' ' -f1 <"${sidecar}")"
    observed="$(sha256sum "${joblib_file}" | cut -d' ' -f1)"
    if [ "${expected}" != "${observed}" ]; then
        bad_sidecars+=("${joblib_file##*/}: sha256 mismatch (sidecar ${expected:0:12}..., file ${observed:0:12}...)")
    fi
done

if [ "${#bad_sidecars[@]}" -gt 0 ]; then
    echo "FATAL: SHA256 sidecar problem(s) for required model artefact(s):" >&2
    for bad in "${bad_sidecars[@]}"; do
        echo "  - ${bad}" >&2
    done
    echo "Re-run the deployment upload step or roll back to a previous artefact." >&2
    exit 1
fi

echo "[STARTUP] Preflight OK: ${#joblib_files[@]} model artefact(s) with verified sidecars"
echo "[STARTUP] Data download complete, starting services..."

# Start supervisor to run Next.js and FastAPI.
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
