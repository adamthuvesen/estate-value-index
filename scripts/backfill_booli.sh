#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

args=(
  backfill
  --start-date "${BACKFILL_START:-2025-12-22}"
  --end-date "${BACKFILL_END:-$(date +%Y-%m-%d)}"
  --window-days "${BACKFILL_WINDOW_DAYS:-7}"
)

uv run python -m estate_value_index.cli "${args[@]}" "$@"
