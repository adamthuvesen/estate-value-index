"""The one ingestion path: fetch sold-date windows, process them, and load BigQuery.

``evi backfill`` and ``.github/workflows/ml-pipeline.yml`` both call ``ingest_listings``.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from estate_value_index.ingestion.bigquery_upload import upload_to_bigquery
from estate_value_index.ingestion.booli.api import fetch_booli_api_window
from estate_value_index.ingestion.geocoding import geocode_new_addresses
from estate_value_index.ingestion.processing import process_pipeline
from estate_value_index.ingestion.sync import (
    PRODUCTION_LISTINGS_FILE,
    backup_listings_to_gcs,
    sync_bigquery_to_local,
    verify_sync,
)
from estate_value_index.utils.approval import require_approval

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_FILE = Path(__file__).parent / "config" / "booli_all_locations.json"
DEFAULT_OUTPUT_ROOT = Path("data/raw/booli")
DEFAULT_START_DATE = date(2025, 12, 22)
REQUIRED_LISTING_FIELDS = ("listing_id", "sold_price", "living_area", "area")


@dataclass(frozen=True)
class DateWindow:
    start: date
    end: date

    @property
    def label(self) -> str:
        return self.start.isoformat()


def date_windows(start: date, end: date, window_days: int) -> Iterator[DateWindow]:
    if window_days < 1:
        raise ValueError("window_days must be >= 1")
    if start > end:
        raise ValueError("start date must be <= end date")

    current = start
    step = timedelta(days=window_days)
    while current <= end:
        window_end = min(current + step - timedelta(days=1), end)
        yield DateWindow(start=current, end=window_end)
        current = window_end + timedelta(days=1)


def write_window_config(base_config_file: Path, output_file: Path, window: DateWindow) -> None:
    if not base_config_file.exists():
        raise FileNotFoundError(f"Booli base config not found: {base_config_file}")
    try:
        config = json.loads(base_config_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid Booli base config JSON: {base_config_file}") from exc
    if not isinstance(config, dict):
        raise ValueError(f"Booli base config must be a JSON object: {base_config_file}")

    search_parameters = config.setdefault("search_parameters", {})
    if not isinstance(search_parameters, dict):
        raise ValueError(
            f"Booli base config search_parameters must be an object: {base_config_file}"
        )
    search_parameters["minSoldDate"] = window.start.isoformat()
    search_parameters["maxSoldDate"] = window.end.isoformat()

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def count_jsonl_records(path: Path) -> int:
    with path.open(encoding="utf-8") as file:
        return sum(1 for line in file if line.strip())


def validate_jsonl_file(path: Path) -> dict[str, Any]:
    total = 0
    valid = 0
    missing_fields: set[str] = set()
    invalid_json = 0

    with path.open(encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            total += 1
            try:
                listing = json.loads(line)
            except json.JSONDecodeError:
                invalid_json += 1
                continue

            missing = [
                field
                for field in REQUIRED_LISTING_FIELDS
                if field not in listing
                or listing[field] is None
                or (isinstance(listing[field], str) and not listing[field].strip())
            ]
            if missing:
                missing_fields.update(missing)
                continue
            valid += 1

    return {
        "total_listings": total,
        "valid_listings": valid,
        "invalid_listings": total - valid,
        "validation_rate": valid / total if total else 0.0,
        "missing_fields": sorted(missing_fields),
        "invalid_json": invalid_json,
    }


def merge_deduped_jsonl(input_files: Iterable[Path], output_file: Path) -> dict[str, Any]:
    seen_listing_ids: set[str] = set()
    month_counts: Counter[str] = Counter()
    source_counts: dict[str, int] = {}

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as output:
        for input_file in sorted(input_files):
            new_records = 0
            with input_file.open(encoding="utf-8") as source:
                for line in source:
                    if not line.strip():
                        continue
                    listing = json.loads(line)
                    listing_id = listing.get("listing_id")
                    if not listing_id or listing_id in seen_listing_ids:
                        continue

                    seen_listing_ids.add(listing_id)
                    output.write(line)
                    new_records += 1

                    sold_date = listing.get("sold_date")
                    if sold_date:
                        month_counts[str(sold_date)[:7]] += 1
            source_counts[input_file.name] = new_records

    return {
        "output_file": str(output_file),
        "total_unique": len(seen_listing_ids),
        "source_counts": source_counts,
        "month_counts": dict(sorted(month_counts.items())),
    }


def fetch_listing_windows(
    *,
    base_config_file: Path,
    output_dir: Path,
    start_date: date,
    end_date: date,
    window_days: int,
    max_pages: int,
    dry_run: bool,
    max_window_retries: int = 2,
    min_validation_rate: float = 0.5,
    fetch: Callable[..., Path] | None = None,
) -> dict[str, Any]:
    windows = list(date_windows(start_date, end_date, window_days))
    output_dir.mkdir(parents=True, exist_ok=True)

    if dry_run:
        return {
            "dry_run": True,
            "output_dir": str(output_dir),
            "windows": [
                {"start": window.start.isoformat(), "end": window.end.isoformat()}
                for window in windows
            ],
            "max_window_retries": max_window_retries,
            "min_validation_rate": min_validation_rate,
        }

    fetch_fn = fetch or fetch_booli_api_window

    listing_files: list[Path] = []
    window_counts: dict[str, int] = {}
    window_validation: dict[str, dict[str, Any]] = {}

    for window in windows:
        config_file = output_dir / f"config_{window.label}.json"
        output_file = output_dir / f"listings_{window.label}.jsonl"
        write_window_config(base_config_file, config_file, window)

        last_error: Exception | None = None
        fetched_file: Path | None = None
        for attempt in range(max_window_retries + 1):
            output_file.unlink(missing_ok=True)
            try:
                fetched_file = Path(
                    fetch_fn(
                        max_pages=max_pages,
                        config_file=str(config_file),
                        output_file=output_file,
                    )
                )
                validation = validate_jsonl_file(fetched_file)
                window_validation[window.label] = validation
                if validation["total_listings"] == 0:
                    raise RuntimeError(f"zero fetched rows for window {window.label}")
                if validation["validation_rate"] < min_validation_rate:
                    raise RuntimeError(
                        "validation rate "
                        f"{validation['validation_rate']:.1%} below "
                        f"{min_validation_rate:.1%} for window {window.label}"
                    )
                break
            except Exception as exc:
                last_error = exc
                if attempt >= max_window_retries:
                    raise

        if fetched_file is None:
            raise RuntimeError(f"Backfill window {window.label} failed") from last_error

        listing_files.append(fetched_file)
        window_counts[window.label] = count_jsonl_records(fetched_file)

    merged_file = output_dir / "all_dedup.jsonl"
    merge_summary = merge_deduped_jsonl(listing_files, merged_file)
    merged_validation = validate_jsonl_file(merged_file)
    if merged_validation["total_listings"] == 0:
        raise RuntimeError("zero merged rows after backfill")

    return {
        "dry_run": False,
        "output_dir": str(output_dir),
        "window_counts": window_counts,
        "window_validation": window_validation,
        "merge": merge_summary,
        "validation": merged_validation,
    }


def ingest_listings(
    *,
    base_config_file: Path,
    output_dir: Path,
    start_date: date,
    end_date: date,
    window_days: int,
    max_pages: int,
    dry_run: bool,
    max_window_retries: int = 2,
    min_validation_rate: float = 0.5,
    process: bool = False,
    load: bool = False,
    production_file: Path = PRODUCTION_LISTINGS_FILE,
    geocode_batch_size: int = 200,
    approved: bool = False,
    fetch: Callable[..., Path] | None = None,
) -> dict[str, Any]:
    """Fetch listings by sold-date window, then optionally process and load them.

    - ``process`` merges the fetched rows into ``production_file`` (clean areas, impute).
    - ``load`` implies ``process``, then writes BigQuery (listings, geocodes), syncs
      ``production_file`` back from BigQuery, checks it, and backs it up to GCS.
      It needs ``approved``; the check runs before any fetch.
    """
    process = process or load
    if load and not dry_run:
        require_approval("write listings and geocodes to BigQuery", approved)

    summary = fetch_listing_windows(
        base_config_file=base_config_file,
        output_dir=output_dir,
        start_date=start_date,
        end_date=end_date,
        window_days=window_days,
        max_pages=max_pages,
        dry_run=dry_run,
        max_window_retries=max_window_retries,
        min_validation_rate=min_validation_rate,
        fetch=fetch,
    )
    if dry_run or not process:
        return summary

    merged_file = Path(summary["merge"]["output_file"])
    if process_pipeline(
        input_file=merged_file,
        production_file=production_file,
        output_file=production_file,
    ):
        raise RuntimeError(f"Processing failed for {merged_file}")
    summary["processed_file"] = str(production_file)
    if not load:
        return summary

    summary["bigquery"] = upload_to_bigquery(production_file, approved=approved)
    summary["geocoding"] = geocode_new_addresses(batch_size=geocode_batch_size, approved=approved)
    summary["synced_rows"] = sync_bigquery_to_local(production_file)
    summary["verification"] = verify_sync(production_file)
    summary["gcs_backup"] = backup_listings_to_gcs(production_file, approved=approved)
    return summary
