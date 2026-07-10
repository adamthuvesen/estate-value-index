#!/usr/bin/env bash
# Run the estate-value-index web app locally.
#
# Starts the FastAPI model server (:8000) and the Next.js dev server (:3000),
# and regenerates the web app's derived data (value analysis, area statistics,
# overall statistics)
# from the model in web/models/ and the local dataset.
#
#   ./scripts/dev_web.sh                 start; regenerate derived data if missing
#   ./scripts/dev_web.sh --refresh-data  force-regenerate derived data first
#   ./scripts/dev_web.sh --skip-data     start servers only, reuse existing data
#
# Needs a trained model in web/models/. Produce one with:
#   uv run python -m estate_value_index.cli train-production-models --data-source bigquery
# (the command writes to web/models/ by default.)
#
# Env overrides: WEB_DATA_FILE, API_PORT, WEB_PORT.
set -euo pipefail
cd "$(dirname "$0")/.."

DATA_FILE="${WEB_DATA_FILE:-data/raw/booli/booli_listings_prod.json}"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"
MODEL="web/models/price_prediction_model_no_list_price.joblib"
VALUE_JSON="data/derived/value_analysis.json"
AREA_JSON="data/derived/area_statistics.json"
OVERALL_JSON="data/derived/overall_statistics.json"

refresh=false
skip_data=false
for arg in "$@"; do
  case "$arg" in
    --refresh-data) refresh=true ;;
    --skip-data) skip_data=true ;;
    -h | --help)
      sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "unknown option: $arg (try --help)" >&2
      exit 2
      ;;
  esac
done

if [[ ! -f "$MODEL" ]]; then
  echo "error: no model at $MODEL" >&2
  echo "train first: uv run python -m estate_value_index.cli train-production-models --data-source bigquery" >&2
  exit 1
fi
if [[ ! -f "$DATA_FILE" ]]; then
  echo "error: dataset not found at $DATA_FILE (set WEB_DATA_FILE to override)" >&2
  exit 1
fi

if ! $skip_data && { $refresh || [[ ! -f "$VALUE_JSON" ]] || [[ ! -f "$AREA_JSON" ]] || [[ ! -f "$OVERALL_JSON" ]]; }; then
  echo ">> regenerating derived data from $DATA_FILE + web/models ..."
  uv run python -m estate_value_index.cli value-analysis \
    --data-file "$DATA_FILE" --models-dir web/models --model-type no_list_price \
    --output "$VALUE_JSON"
  uv run python -m estate_value_index.cli areas \
    --data-source json --raw-listings "$DATA_FILE" \
    --value-analysis "$VALUE_JSON" --output "$AREA_JSON"
  uv run python -m estate_value_index.cli overall-stats \
    --data-source json --raw-listings "$DATA_FILE" \
    --value-analysis "$VALUE_JSON" --output "$OVERALL_JSON"
else
  echo ">> using existing derived data (pass --refresh-data to regenerate)"
fi

pids=()
cleanup() {
  trap - EXIT INT TERM
  echo
  echo ">> stopping servers ..."
  kill "${pids[@]}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo ">> starting FastAPI model server on :$API_PORT ..."
uv run uvicorn api_server:app --host 127.0.0.1 --port "$API_PORT" &
pids+=($!)

echo ">> starting Next.js dev server on :$WEB_PORT ..."
(cd web && PREDICTION_API_URL="http://127.0.0.1:$API_PORT" npm run dev) &
pids+=($!)

echo
echo ">> web app:  http://localhost:$WEB_PORT"
echo ">> api docs: http://localhost:$API_PORT/docs"
echo ">> Ctrl-C to stop both."
wait
