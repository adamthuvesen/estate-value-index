#!/usr/bin/env python3
"""One-shot: write `<artefact>.joblib.sha256` sidecars for every existing
``*.joblib`` under ``gs://${GCS_BUCKET}/models/``.

The sidecars are required by the production ``api_server`` integrity check
(``_verify_model_integrity``) and the container preflight in
``scripts/startup.sh``. Run this once after rolling out the upload-side change
that writes sidecars for *new* artefacts. After that, all live artefacts will
have a matching sidecar and strict verification can be enabled.

Usage:

    GCS_BUCKET=your-gcs-bucket \\
    python scripts/backfill_model_hashes.py [--prefix models/] [--dry-run]

The script is idempotent: artefacts that already have a `.sha256` sidecar in
GCS are skipped unless ``--force`` is passed.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from src.estate_value_index.utils.gcs import GCSClient, compute_sha256


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bucket",
        default=os.getenv("GCS_BUCKET"),
        required=os.getenv("GCS_BUCKET") is None,
        help="GCS bucket name (default: $GCS_BUCKET).",
    )
    parser.add_argument(
        "--prefix",
        default="models/",
        help="GCS prefix to scan for *.joblib (default: models/).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-write sidecars even if one already exists in GCS.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the artefacts that would get sidecars; don't upload anything.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    # The backfill must always run against real GCS — force the env var on for this process.
    os.environ.setdefault("GCS_ENABLED", "true")
    os.environ["GCS_BUCKET"] = args.bucket

    client = GCSClient(bucket_name=args.bucket)
    if not client.enabled:
        print(
            "ERROR: GCS is not enabled in this environment. Set GCS_ENABLED=true.",
            file=sys.stderr,
        )
        return 2

    blobs = client.list_files(prefix=args.prefix)
    joblib_blobs = [b for b in blobs if b.endswith(".joblib")]
    sidecar_blobs = {b for b in blobs if b.endswith(".sha256")}

    if not joblib_blobs:
        print(f"No *.joblib artefacts under gs://{args.bucket}/{args.prefix}.")
        return 0

    print(f"Found {len(joblib_blobs)} *.joblib artefact(s) under gs://{args.bucket}/{args.prefix}.")

    written = 0
    skipped = 0
    failed = 0
    for blob_path in joblib_blobs:
        sidecar_path = f"{blob_path}.sha256"

        if sidecar_path in sidecar_blobs and not args.force:
            print(f"  skip   {blob_path} (sidecar already present)")
            skipped += 1
            continue

        if args.dry_run:
            print(f"  would  {blob_path} -> {sidecar_path}")
            written += 1
            continue

        try:
            with tempfile.TemporaryDirectory() as tmp:
                local = Path(tmp) / Path(blob_path).name
                client.download_file(blob_path, local)
                digest = compute_sha256(local)
                sidecar_local = local.with_suffix(local.suffix + ".sha256")
                sidecar_local.write_text(f"{digest}  {local.name}\n", encoding="utf-8")
                client.upload_file(sidecar_local, sidecar_path)
            print(f"  wrote  {sidecar_path} ({digest[:16]}...)")
            written += 1
        except Exception as exc:  # pragma: no cover - depends on live GCS
            print(f"  FAIL   {blob_path}: {exc}", file=sys.stderr)
            failed += 1

    print(f"\nDone. wrote={written} skipped={skipped} failed={failed} dry_run={args.dry_run}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
