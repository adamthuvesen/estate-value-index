"""``evi upload-enrichment``: publish the derived web JSON files to GCS."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from estate_value_index.analytics.publish import DERIVED_DIR, upload_enrichment_to_gcs
from estate_value_index.utils.settings import get_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="evi upload-enrichment",
        description="Upload data/derived/*.json to gs://<GCS_BUCKET>/derived/ for Cloud Run.",
    )
    parser.add_argument("--dir", type=Path, default=DERIVED_DIR)
    parser.add_argument("--prefix", default="derived/")
    parser.add_argument("--approved", action="store_true", help="Allow the GCS write.")
    args = parser.parse_args(argv)

    uris = upload_enrichment_to_gcs(
        args.dir, get_settings().require_gcs_bucket(), args.prefix, approved=args.approved
    )
    print(json.dumps({"uploaded": uris}, indent=2))
    return 0
