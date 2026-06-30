#!/usr/bin/env python3
"""Batch scraper for Booli listings with local staging and optional BigQuery upload.

Usage:
    uv run python -m estate_value_index.cli batch --batches 10 --max-pages 5 --start-page-min 1 --start-page-max 200
    uv run python -m estate_value_index.cli batch --batches 8 --max-pages 10 --promote --upload-bq
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from argparse import Namespace

from estate_value_index.ingestion.processing import (
    load_jsonl_file,
    merge_listings,
    process_pipeline,
)
from estate_value_index.pipelines.core.data_pipeline import run_scrapy_spider


def _task_fn(task: Any) -> Any:
    """Unwrap a Prefect task to its plain callable (or pass through if already plain)."""
    return getattr(task, "fn", task)


def _write_jsonl(records: Iterable[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


@dataclass
class ValidationSummary:
    production_count: int
    candidate_count: int
    unique_count: int
    duplicate_count: int
    new_count: int
    removed_count: int
    missing_listing_id: int
    null_listing_price: int
    null_sold_price: int
    valid: bool


@dataclass(frozen=True)
class BatchRunContext:
    run_id: str
    base_dir: Path
    production_file: Path


@dataclass(frozen=True)
class CandidateArtifacts:
    combined_new_file: Path
    candidate_file: Path
    merge_stats: dict[str, Any]


def _validate_candidate(candidate_file: Path, production_file: Path) -> ValidationSummary:
    production = load_jsonl_file(production_file)
    candidate = load_jsonl_file(candidate_file)

    prod_ids = [str(item.get("listing_id")) for item in production if item.get("listing_id")]
    cand_ids = [str(item.get("listing_id")) for item in candidate if item.get("listing_id")]

    prod_set = set(prod_ids)
    cand_set = set(cand_ids)

    unique_count = len(cand_set)
    duplicate_count = len(cand_ids) - unique_count
    new_count = len(cand_set - prod_set)
    removed_count = len(prod_set - cand_set)

    missing_listing_id = sum(1 for item in candidate if not item.get("listing_id"))
    null_listing_price = sum(1 for item in candidate if item.get("listing_price") is None)
    null_sold_price = sum(1 for item in candidate if item.get("sold_price") is None)

    valid = (
        duplicate_count == 0
        and removed_count == 0
        and missing_listing_id == 0
        and null_listing_price == 0
        and null_sold_price == 0
    )

    return ValidationSummary(
        production_count=len(production),
        candidate_count=len(candidate),
        unique_count=unique_count,
        duplicate_count=duplicate_count,
        new_count=new_count,
        removed_count=removed_count,
        missing_listing_id=missing_listing_id,
        null_listing_price=null_listing_price,
        null_sold_price=null_sold_price,
        valid=valid,
    )


def _save_summary(run_dir: Path, summary: dict) -> None:
    summary_path = run_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)


def _print_validation_summary(validation: ValidationSummary, *, json_mode: bool = False) -> None:
    """Print validation summary in consistent format."""
    if json_mode:
        print(json.dumps({"validation": validation.__dict__}, ensure_ascii=False, indent=2))
    else:
        print("Validation summary:")
        print(f"  Production count: {validation.production_count}")
        print(f"  Candidate count: {validation.candidate_count}")
        print(f"  Unique count: {validation.unique_count}")
        print(f"  Duplicate count: {validation.duplicate_count}")
        print(f"  New listings: {validation.new_count}")
        print(f"  Removed listings: {validation.removed_count}")
        print(f"  Missing listing_id: {validation.missing_listing_id}")
        print(f"  Null listing_price: {validation.null_listing_price}")
        print(f"  Null sold_price: {validation.null_sold_price}")


def _run_promotion_workflow(
    candidate_file: Path,
    production_file: Path,
    run_id: str,
    base_dir: Path,
    upload_bq: bool,
    materialize: bool,
    sync_after: bool,
    allow_no_new: bool,
    promote: bool,
    *,
    json_mode: bool = False,
) -> int:
    """Validate the candidate, promote it, and optionally upload to BigQuery."""
    validation = _validate_candidate(candidate_file, production_file)
    _print_validation_summary(validation, json_mode=json_mode)

    if not validation.valid:
        print(
            "Validation failed: duplicates, missing IDs, null prices, or removed listings detected."
        )
        return 1

    if validation.new_count == 0 and not allow_no_new:
        print("No new listings detected. Skipping promotion (use --allow-no-new to override).")
        return 1

    if not promote:
        print("Promotion skipped. Review candidate file before uploading.")
        return 1

    backup_file = base_dir / f"booli_listings_prod_backup_{run_id}.jsonl"
    if production_file.exists():
        shutil.copy2(production_file, backup_file)

    shutil.copy2(candidate_file, production_file)
    print(f"Promoted candidate to production file: {production_file}")

    if upload_bq:
        from estate_value_index.pipelines.tasks import (
            materialize_features_task,
            sync_bigquery_to_local_task,
            upload_to_bigquery_task,
        )

        upload_fn = _task_fn(upload_to_bigquery_task)
        upload_result = upload_fn(processed_file=production_file, truncate=False)
        print(f"Uploaded to BigQuery: {upload_result}")

        if materialize:
            materialize_fn = _task_fn(materialize_features_task)
            materialize_result = materialize_fn(truncate=True)
            print(f"Materialized features: {materialize_result}")

        if sync_after:
            sync_fn = _task_fn(sync_bigquery_to_local_task)
            sync_result = sync_fn(output_file=production_file, backup_existing=True)
            print(f"Synced BigQuery to local: {sync_result}")
    else:
        print("Upload skipped. Use --upload-bq to push to BigQuery.")

    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch scrape Booli listings with staging.")
    parser.add_argument("--batches", type=int, default=None, help="Number of scrape batches to run")
    parser.add_argument("--max-pages", type=int, default=5, help="Max pages per batch scrape")
    parser.add_argument(
        "--start-page-min", type=int, default=1, help="Minimum start page (inclusive)"
    )
    parser.add_argument(
        "--start-page-max", type=int, default=200, help="Maximum start page (inclusive)"
    )
    parser.add_argument(
        "--seed", type=int, default=None, help="Random seed for start page selection"
    )
    parser.add_argument(
        "--sequential",
        action="store_true",
        help="Use sequential start pages in steps of max-pages (e.g., 1, 6, 11...)",
    )
    parser.add_argument("--delay", type=float, default=0.5, help="Download delay in seconds")
    parser.add_argument("--concurrency", type=int, default=2, help="Concurrent requests per batch")
    parser.add_argument(
        "--cooldown-seconds", type=float, default=10.0, help="Pause between batches"
    )
    parser.add_argument(
        "--config-file", type=str, default=None, help="Optional scraper config file"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Simulate without scraping or uploads"
    )
    parser.add_argument(
        "--promote", action="store_true", help="Promote candidate to production file"
    )
    parser.add_argument(
        "--upload-bq", action="store_true", help="Upload to BigQuery (requires --promote)"
    )
    parser.add_argument(
        "--materialize-features", action="store_true", help="Materialize features after BQ upload"
    )
    parser.add_argument(
        "--sync-after-upload", action="store_true", help="Sync BigQuery back to local after upload"
    )
    parser.add_argument(
        "--allow-no-new", action="store_true", help="Allow promote even if no new listings found"
    )
    parser.add_argument("--min-area-count", type=int, default=5, help="Min area count for cleaning")
    parser.add_argument(
        "--days-threshold", type=int, default=1000, help="Days on market imputation threshold"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directory for batch outputs (default: data/raw/booli/batch_runs/<timestamp>)",
    )
    parser.add_argument(
        "--promote-from",
        type=str,
        default=None,
        help="Promote an existing candidate JSONL without scraping (path to candidate file)",
    )
    parser.add_argument(
        "--production-file",
        type=str,
        default="data/raw/booli/booli_listings_prod.json",
        help="Production listings file to merge against",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output structured JSON instead of human-readable text",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Increase output verbosity",
    )

    return parser


def _validate_args(args: Namespace, parser: argparse.ArgumentParser) -> int | None:
    if args.max_pages < 0:
        parser.error("--max-pages must be >= 0")
    if args.delay < 0:
        parser.error("--delay must be >= 0")
    if args.concurrency < 1:
        parser.error("--concurrency must be >= 1")
    if args.start_page_min > args.start_page_max:
        parser.error("start-page-min must be <= start-page-max")
    if args.upload_bq and not args.promote:
        print("Upload requires --promote. Refusing to upload without promotion.")
        return 1

    if args.materialize_features and not args.upload_bq:
        print("Materialization requested without BigQuery upload. Skipping materialization.")
        args.materialize_features = False

    return None


def _build_run_context(args: Namespace) -> BatchRunContext:
    production_file = Path(args.production_file)
    production_file.parent.mkdir(parents=True, exist_ok=True)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_dir = (
        Path(args.output_dir) if args.output_dir else Path("data/raw/booli/batch_runs") / run_id
    )
    base_dir.mkdir(parents=True, exist_ok=True)

    return BatchRunContext(
        run_id=run_id,
        base_dir=base_dir,
        production_file=production_file,
    )


def _run_promote_from(args: Namespace, context: BatchRunContext) -> int:
    candidate_file = Path(args.promote_from)
    if not candidate_file.exists():
        print(f"Candidate file not found: {candidate_file}")
        return 1

    candidate_base_dir = candidate_file.parent
    validation = _validate_candidate(candidate_file, context.production_file)
    summary = {
        "run_id": context.run_id,
        "candidate_file": str(candidate_file),
        "production_file": str(context.production_file),
        "validation": validation.__dict__,
        "mode": "promote_from",
    }
    _save_summary(candidate_base_dir, summary)

    return _run_promotion_workflow(
        candidate_file=candidate_file,
        production_file=context.production_file,
        run_id=context.run_id,
        base_dir=candidate_base_dir,
        upload_bq=args.upload_bq,
        materialize=args.materialize_features,
        sync_after=args.sync_after_upload,
        allow_no_new=args.allow_no_new,
        promote=args.promote,
        json_mode=args.json,
    )


def _select_start_pages(args: Namespace) -> list[int] | None:
    if args.sequential:
        start_pages = list(range(args.start_page_min, args.start_page_max + 1, args.max_pages))
    else:
        batches = args.batches or 10
        rng = random.Random(args.seed)
        start_pages = [
            rng.randint(args.start_page_min, args.start_page_max) for _ in range(batches)
        ]

    if args.batches is not None:
        if args.batches < 1:
            print("Batches must be >= 1.")
            return None
        start_pages = start_pages[: args.batches]

    return start_pages


def _print_batch_header(args: Namespace, context: BatchRunContext, start_pages: list[int]) -> None:
    if args.json:
        return

    print(f"Running batch scrape: batches={len(start_pages)}, max_pages={args.max_pages}")
    print(f"Start pages: {start_pages}")
    print(f"Output dir: {context.base_dir}")
    print(f"Dry run: {args.dry_run}")


def _run_dry_run(args: Namespace, context: BatchRunContext, start_pages: list[int]) -> int:
    summary = {
        "run_id": context.run_id,
        "batches": args.batches,
        "max_pages": args.max_pages,
        "start_pages": start_pages,
        "dry_run": True,
    }
    _save_summary(context.base_dir, summary)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _scrape_batches(args: Namespace, base_dir: Path, start_pages: list[int]) -> list[Path]:
    batch_files: list[Path] = []
    scrape_fn = _task_fn(run_scrapy_spider)
    total_batches = len(start_pages)

    for idx, start_page in enumerate(start_pages, start=1):
        batch_file = base_dir / f"batch_{idx:02d}_start_{start_page}.jsonl"
        if not args.json:
            print(f"Batch {idx}/{total_batches}: start_page={start_page}, output={batch_file}")
        output_path = scrape_fn(
            max_pages=args.max_pages,
            concurrent_requests=args.concurrency,
            delay=args.delay,
            config_file=args.config_file,
            start_page=start_page,
            output_file=batch_file,
        )
        batch_files.append(Path(output_path))
        if idx < total_batches and args.cooldown_seconds > 0:
            time.sleep(args.cooldown_seconds)

    return batch_files


def _load_batch_listings(batch_files: list[Path]) -> list[dict]:
    new_listings: list[dict] = []
    for batch_file in batch_files:
        new_listings.extend(load_jsonl_file(batch_file))
    return new_listings


def _build_candidate_file(
    args: Namespace,
    context: BatchRunContext,
    batch_files: list[Path],
) -> CandidateArtifacts:
    combined_new_file = context.base_dir / "new_listings_combined.jsonl"

    deduped_new, new_stats = merge_listings(_load_batch_listings(batch_files), [])
    _write_jsonl(deduped_new, combined_new_file)

    candidate_file = context.base_dir / f"booli_listings_prod_candidate_{context.run_id}.jsonl"
    process_pipeline(
        input_file=combined_new_file,
        production_file=context.production_file,
        output_file=candidate_file,
        min_area_count=args.min_area_count,
        days_threshold=args.days_threshold,
        dry_run=False,
    )

    return CandidateArtifacts(
        combined_new_file=combined_new_file,
        candidate_file=candidate_file,
        merge_stats=new_stats,
    )


def _save_scrape_summary(
    args: Namespace,
    context: BatchRunContext,
    start_pages: list[int],
    batch_files: list[Path],
    artifacts: CandidateArtifacts,
    validation: ValidationSummary,
) -> None:
    summary = {
        "run_id": context.run_id,
        "batches": args.batches,
        "max_pages": args.max_pages,
        "start_pages": start_pages,
        "batch_files": [str(path) for path in batch_files],
        "combined_new_file": str(artifacts.combined_new_file),
        "candidate_file": str(artifacts.candidate_file),
        "merge_stats": artifacts.merge_stats,
        "validation": validation.__dict__,
    }
    _save_summary(context.base_dir, summary)


def _run_scrape_workflow(
    args: Namespace,
    context: BatchRunContext,
    start_pages: list[int],
) -> int:
    batch_files = _scrape_batches(args, context.base_dir, start_pages)
    artifacts = _build_candidate_file(args, context, batch_files)
    validation = _validate_candidate(artifacts.candidate_file, context.production_file)
    _save_scrape_summary(args, context, start_pages, batch_files, artifacts, validation)

    return _run_promotion_workflow(
        candidate_file=artifacts.candidate_file,
        production_file=context.production_file,
        run_id=context.run_id,
        base_dir=context.base_dir,
        upload_bq=args.upload_bq,
        materialize=args.materialize_features,
        sync_after=args.sync_after_upload,
        allow_no_new=args.allow_no_new,
        promote=args.promote,
        json_mode=args.json,
    )


def main(argv: list[str] | None = None, *, args: Namespace | None = None) -> int:
    """Run the batch scraper. ``args`` takes precedence over ``argv`` when given."""
    parser = _build_parser()
    if args is None:
        args = parser.parse_args(argv)

    validation_exit = _validate_args(args, parser)
    if validation_exit is not None:
        return validation_exit

    context = _build_run_context(args)

    if args.promote_from:
        return _run_promote_from(args, context)

    start_pages = _select_start_pages(args)
    if start_pages is None:
        return 1

    _print_batch_header(args, context, start_pages)

    if args.dry_run:
        return _run_dry_run(args, context, start_pages)

    return _run_scrape_workflow(args, context, start_pages)


if __name__ == "__main__":
    sys.exit(main())
