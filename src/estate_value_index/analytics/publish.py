"""Publish the derived web JSON files to GCS, where the Cloud Run app reads them."""

from __future__ import annotations

import logging
from pathlib import Path

from estate_value_index.utils.approval import require_approval
from estate_value_index.utils.clients import get_storage_client

logger = logging.getLogger(__name__)

DERIVED_DIR = Path("data/derived")


def upload_enrichment_to_gcs(
    local_dir: Path, gcs_bucket: str, gcs_prefix: str = "derived/", *, approved: bool = False
) -> list[str]:
    """Upload every ``*.json`` in ``local_dir`` to ``gs://<bucket>/<prefix>``. Returns the URIs."""
    require_approval("upload enrichment data to GCS", approved)

    files = sorted(local_dir.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"No enrichment files in {local_dir}")

    bucket = get_storage_client().bucket(gcs_bucket)
    uris = []
    for file_path in files:
        blob_name = f"{gcs_prefix}{file_path.name}"
        bucket.blob(blob_name).upload_from_filename(str(file_path))
        uris.append(f"gs://{gcs_bucket}/{blob_name}")
        logger.info("Uploaded %s", uris[-1])
    return uris
