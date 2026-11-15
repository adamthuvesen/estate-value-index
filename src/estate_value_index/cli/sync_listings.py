"""``evi sync``: copy BigQuery listings to the local production file, check, and back up."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from estate_value_index.ingestion.sync import (
    PRODUCTION_LISTINGS_FILE,
    backup_listings_to_gcs,
    sync_bigquery_to_local,
    verify_sync,
)
from estate_value_index.utils.approval import require_approval
from estate_value_index.utils.settings import is_gcs_enabled


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="evi sync",
        description=(
            "Write the BigQuery listings table to the local production file, check that both "
            "hold the same listings, and back the file up to GCS when GCS is enabled."
        ),
    )
    parser.add_argument("--output", type=Path, default=PRODUCTION_LISTINGS_FILE)
    parser.add_argument(
        "--approved", action="store_true", help="Allow the GCS backup when GCS is enabled."
    )
    args = parser.parse_args(argv)

    if is_gcs_enabled():
        require_approval("back up listings to GCS", args.approved)
    synced = sync_bigquery_to_local(args.output)
    summary = verify_sync(args.output)
    backups = backup_listings_to_gcs(args.output, approved=args.approved)
    print(json.dumps({"synced_rows": synced, "verified": summary, "gcs_backup": backups}, indent=2))
    return 0
