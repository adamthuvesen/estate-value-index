#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

args=(
  backfill
  --start-date "${BACKFILL_START:-2025-12-22}"
  --end-date "${BACKFILL_END:-$(date +%Y-%m-%d)}"
  --window-days "${BACKFILL_WINDOW_DAYS:-7}"
  --max-pages "${BACKFILL_MAX_PAGES:-20}"
  --concurrent "${BACKFILL_CONCURRENT:-1}"
  --delay "${BACKFILL_DELAY:-1.0}"
  --max-window-retries "${BACKFILL_MAX_WINDOW_RETRIES:-2}"
  --min-validation-rate "${BACKFILL_MIN_VALIDATION_RATE:-0.5}"
)

uv run python -m estate_value_index.cli "${args[@]}" "$@"
