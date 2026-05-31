#!/bin/bash
#
# Quick script to scrape Solna and Sundbyberg areas
#
# Usage:
#   ./scripts/scrape_solna_sundbyberg.sh [max_pages] [--tune] [--dry-run]
#
# Examples:
#   ./scripts/scrape_solna_sundbyberg.sh           # Default: 10 pages, no tuning
#   ./scripts/scrape_solna_sundbyberg.sh 20        # 20 pages
#   ./scripts/scrape_solna_sundbyberg.sh 20 --tune # 20 pages with tuning
#   ./scripts/scrape_solna_sundbyberg.sh 5 --dry-run # Test run

set -e

# Default values
MAX_PAGES=${1:-10}
CONFIG_FILE="src/estate_value_index/ingestion/config/booli_solna_sundbyberg.json"

# Additional arguments
EXTRA_ARGS=""
shift || true
while [[ $# -gt 0 ]]; do
    EXTRA_ARGS="$EXTRA_ARGS $1"
    shift
done

echo "=========================================="
echo "Scraping Solna & Sundbyberg"
echo "=========================================="
echo "Config: $CONFIG_FILE"
echo "Max Pages: $MAX_PAGES"
echo "Extra Args: $EXTRA_ARGS"
echo "=========================================="
echo ""

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    echo "Activating virtual environment..."
    source .venv/bin/activate
fi

# Run the pipeline
python src/estate_value_index/pipelines/core/complete_pipeline.py \
  --config-file "$CONFIG_FILE" \
  --max-pages "$MAX_PAGES" \
  $EXTRA_ARGS

echo ""
echo "=========================================="
echo "Pipeline complete!"
echo "=========================================="
echo ""
echo "To verify scraped areas:"
echo "  cat data/raw/booli/booli_listings_*.jsonl | jq -r '.area' | sort | uniq -c"
echo ""
echo "To query BigQuery:"
echo "  bq query --use_legacy_sql=false 'SELECT area, COUNT(*) FROM \`estate-value-index.booli_raw.listings\` GROUP BY area'"
echo ""
