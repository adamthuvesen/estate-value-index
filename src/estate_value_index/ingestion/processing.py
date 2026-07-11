"""Data processing utilities for Booli listings.

This module provides functions for:
- Loading JSONL files
- Merging and deduplicating listings
- Cleaning and standardizing area names
- Imputing days_on_market values
"""

from __future__ import annotations

import json
import logging
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from estate_value_index.ingestion.booli.normalization import (
    extract_area_token as extract_area_from_format,
)

logger = logging.getLogger(__name__)


def load_jsonl_file(file_path: Path) -> list[dict]:
    """Load listings from JSONL file (supports both line-delimited and array format)."""
    listings = []

    if not file_path.exists():
        return listings

    with open(file_path, encoding="utf-8") as f:
        content = f.read().strip()

        # Try JSON array format first
        if content.startswith("["):
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    listings = [item for item in data if isinstance(item, dict)]
                    return listings
            except json.JSONDecodeError:
                pass

        # Fall back to line-delimited JSON
        for line_num, line in enumerate(content.split("\n"), 1):
            line = line.strip()
            if not line:
                continue
            try:
                listing = json.loads(line)
                if isinstance(listing, dict):
                    listings.append(listing)
            except json.JSONDecodeError as e:
                logger.warning("Invalid JSON on line %d: %s", line_num, e)

    return listings


def _pick_newer(existing: dict, new: dict) -> dict:
    """Resolve a listing-id collision between an existing and a new record.

    Conflict resolution rule:
    1. If exactly one record has a non-null ``sold_price``, that one wins.
       (A newly-known sold price always replaces a record that didn't have it.)
    2. Otherwise, whichever record has the more recent ``scraped_at`` wins.
    3. If ``scraped_at`` cannot be parsed on either side, prefer the existing
       record (defensive default — don't silently overwrite on bad metadata).
    """
    existing_sold = existing.get("sold_price")
    new_sold = new.get("sold_price")

    if existing_sold is not None and new_sold is None:
        return existing
    if new_sold is not None and existing_sold is None:
        return new

    # Timestamps mix tz-aware and naive ISO forms (both UTC); drop the offset
    # so comparing across the two can't raise TypeError.
    try:
        existing_scraped = datetime.fromisoformat(str(existing.get("scraped_at"))).replace(
            tzinfo=None
        )
    except (TypeError, ValueError):
        return existing
    try:
        new_scraped = datetime.fromisoformat(str(new.get("scraped_at"))).replace(tzinfo=None)
    except (TypeError, ValueError):
        return existing

    return new if new_scraped > existing_scraped else existing


def merge_listings(
    new_listings: list[dict], existing_listings: list[dict]
) -> tuple[list[dict], dict[str, int]]:
    """Merge new listings with existing, deduplicating on ``listing_id``.

    All records with a ``listing_id`` are retained (newly-listed properties
    legitimately have ``sold_price=None``). On a duplicate ``listing_id``,
    ``_pick_newer`` decides the winner: prefer the record with a non-null
    ``sold_price``, then break ties on the more recent ``scraped_at``
    (existing wins if either ``scraped_at`` fails to parse).

    Returns:
        Tuple of (merged_listings, stats)
    """
    listings_by_id: dict[str, dict] = {}
    stats = {
        "existing_count": len(existing_listings),
        "new_count": len(new_listings),
        "duplicates": 0,
        "duplicates_replaced": 0,
        "corrupted": 0,
        "added": 0,
        "existing_missing_id": 0,
        "existing_corrupted": 0,
    }

    # Load existing listings first (filter invalid entries)
    for listing in existing_listings:
        listing_id = listing.get("listing_id")
        if not listing_id:
            stats["existing_missing_id"] += 1
            continue
        if listing.get("address") == "JavaScript is disabled":
            stats["existing_corrupted"] += 1
            continue
        listings_by_id[listing_id] = listing

    # Merge new listings
    for listing in new_listings:
        listing_id = listing.get("listing_id")

        # Skip listings without ID
        if not listing_id:
            logger.warning("Listing without listing_id, skipping")
            continue

        # Skip corrupted listings
        if listing.get("address") == "JavaScript is disabled":
            stats["corrupted"] += 1
            continue

        if listing_id in listings_by_id:
            stats["duplicates"] += 1
            existing = listings_by_id[listing_id]
            winner = _pick_newer(existing, listing)
            if winner is not existing:
                listings_by_id[listing_id] = winner
                stats["duplicates_replaced"] += 1
        else:
            listings_by_id[listing_id] = listing
            stats["added"] += 1

    stats["final_count"] = len(listings_by_id)

    return list(listings_by_id.values()), stats


def clean_area_name(area_field: str) -> str:
    """Clean and standardize an area name."""
    area = extract_area_from_format(area_field)

    if not area:
        return ""

    # Remove quotes
    area = area.strip('"').strip()

    # Area consolidation mappings (apply first)
    area_consolidations = {
        "Solna kommun": "Solna",
        "Frösunda": "Solna",
        "Sundbyberg/Duvbo": "Sundbyberg",
        "Sundbybergs kommun": "Sundbyberg",
        "Rissne/Ursvik": "Sundbyberg",
        "Kristineberg": "Kungsholmen",
    }

    for original, consolidated in area_consolidations.items():
        if area == original:
            area = consolidated
            break

    # Fix common spelling errors
    spelling_fixes = {
        "Vasasatan": "Vasastan",
        "Kungholmen": "Kungsholmen",
        "Östemalm": "Östermalm",
        "Strockholm": "Stockholm",
        "Hagastan": "Hagastaden",
    }

    for wrong, correct in spelling_fixes.items():
        if wrong in area:
            area = area.replace(wrong, correct)

    # Handle "Söder" abbreviation
    if area == "Söder" or area.startswith("Söder "):
        area = area.replace("Söder", "Södermalm", 1)

    # Standardize compound areas
    if "/" in area:
        parts = area.split("/")
        major_districts = [
            "Vasastan",
            "Kungsholmen",
            "Södermalm",
            "Östermalm",
            "Norrmalm",
        ]
        for district in reversed(major_districts):
            if any(district in p for p in parts):
                return district

    return area


def consolidate_sparse_areas(area_counts: Counter, min_count: int = 5) -> dict[str, str]:
    """Create mapping for sparse variations to parent areas."""
    consolidation_map = {}

    # Explicit semantic mappings
    explicit_mappings = {
        "Vasastan Birkastan": "Birkastan",
        "Maria": "Södermalm Maria",
        "Sofia": "Södermalm Sofia",
        "Stockholm Södermalm": "Södermalm",
        "Gärdet Östermalm": "Gärdet",
        "Nedre Gärdet": "Gärdet",
        "Nedre Gärdet Östermalm": "Gärdet",
        "Nacka Kommun": "Nacka",
        "Fridhemsplan": "Kungsholmen Fridhemsplan",
        "Mariaberget": "Södermalm",
        "Nytorget": "Södermalm",
        "Sofo": "Södermalm Sofia",
        "Thorildsplan": "Kungsholmen",
        "City": "Norrmalm",
        "Hägersten-Liljeholmen": "Liljeholmen",
        "Kungsholmstorg": "Kungsholmen",
        "Mariatorget": "Södermalm Maria",
        "Katarina": "Södermalm Katarina",
        "Norr Mälarstrand": "Kungsholmen",
        "Odenplan": "Vasastan Odenplan",
        "Alvik": "Bromma",
        "Rådhusparken": "Kungsholmen",
        "Årstaberg": "Årsta",
        "Traneberg": "Bromma",
        "Minneberg": "Bromma",
        "Gullmarsplan": "Johanneshov",
        "Atlas": "Vasastan",
        "Globen": "Årsta",
        "Hjorthagen": "Gärdet",
        "Högst Upp": "Södermalm",
        "Högalid": "Södermalm Högalid",
        "Kronobergsparken": "Kungsholmen",
        "Lindhagen": "Kungsholmen",
        "Mosebacke": "Södermalm",
        "Norra Djurgården": "Gärdet",
        "Norra Djurgårdstaden": "Norra Djurgårdsstaden",
        "Nybodahöjden": "Södermalm",
        "Ruddammen": "Bromma",
        "Rådhuset": "Kungsholmen",
        "Röda Bergen": "Vasastan",
        "Rödabergen": "Vasastan",
        "Vasastan Rödabergen": "Vasastan",
        "Rörstrand": "Vasastan",
        "Sibirien": "Vasastan",
        "Sibrien": "Vasastan",
        "Eget": "Hammarby Sjöstad",
        "Centrum": "Norrmalm",
        "Stadshagen": "Kungsholmen",
        "Sveakvarteren": "Vasastan",
        "Södra Station": "Södermalm",
        "Stockholm": "Stockholms län",
        "Kungsholmen Kungsholms Strand": "Kungsholmen",
        "Kungsholmen Nedre": "Kungsholmen",
        "Nedre Kungsholmen": "Kungsholmen",
    }

    # Major parent areas
    parent_areas = {
        "Vasastan",
        "Kungsholmen",
        "Södermalm",
        "Östermalm",
        "Norrmalm",
        "Bromma",
        "Gärdet",
        "Hammarby Sjöstad",
    }

    for area, count in area_counts.items():
        # Apply explicit mappings first
        if area in explicit_mappings:
            consolidation_map[area] = explicit_mappings[area]
        elif count < min_count:
            # For sparse areas, check if sub-area of major district
            for parent in parent_areas:
                if parent in area and area != parent:
                    consolidation_map[area] = parent
                    break

    return consolidation_map


def apply_area_cleaning(
    listings: list[dict], min_area_count: int = 5
) -> tuple[list[dict], dict[str, int]]:
    """Apply area cleaning and consolidation to all listings.

    Returns:
        Tuple of (cleaned_listings, stats)
    """
    cleaned_cache: dict[str, str] = {}

    def _cached_clean(value: str) -> str:
        if value not in cleaned_cache:
            cleaned_cache[value] = clean_area_name(value)
        return cleaned_cache[value]

    # First pass: count areas after initial cleaning
    area_counts: Counter[str] = Counter()
    for listing in listings:
        cleaned_area = _cached_clean(listing.get("area", ""))
        if cleaned_area:
            area_counts[cleaned_area] += 1

    # Create consolidation map and apply cleaning + consolidation in a single second pass.
    consolidation_map = consolidate_sparse_areas(area_counts, min_area_count)

    cleaned_listings: list[dict] = []
    final_area_counts: Counter[str] = Counter()
    for listing in listings:
        original_area = listing.get("area", "")
        cleaned_area = _cached_clean(original_area)
        final_area = consolidation_map.get(cleaned_area, cleaned_area)

        listing["area"] = final_area
        listing["area_original"] = original_area
        cleaned_listings.append(listing)
        final_area_counts[final_area] += 1

    stats = {
        "unique_areas_before": len(area_counts),
        "unique_areas_after": len(final_area_counts),
        "consolidated_areas": len(consolidation_map),
        "top_areas": final_area_counts.most_common(35),
    }

    return cleaned_listings, stats


def calculate_area_medians(listings: list[dict], days_threshold: int = 1000) -> dict[str, int]:
    """Calculate median days_on_market for each area (only valid values <= threshold)."""
    area_days = defaultdict(list)

    for listing in listings:
        area = extract_area_from_format(listing.get("area", ""))
        days_on_market = listing.get("days_on_market")

        if days_on_market is not None and days_on_market <= days_threshold:
            area_days[area].append(days_on_market)

    area_medians = {}
    for area, days_list in area_days.items():
        if days_list:
            area_medians[area] = round(statistics.median(days_list))

    return area_medians


def calculate_overall_median(listings: list[dict], days_threshold: int = 1000) -> int:
    """Calculate overall median days_on_market from all valid records."""
    valid_days = []

    for listing in listings:
        days_on_market = listing.get("days_on_market")
        if days_on_market is not None and days_on_market <= days_threshold:
            valid_days.append(days_on_market)

    return round(statistics.median(valid_days)) if valid_days else 30


def impute_days_on_market(
    listings: list[dict], days_threshold: int = 1000
) -> tuple[list[dict], dict[str, int]]:
    """Impute days_on_market values > threshold using area-based medians.

    Returns:
        Tuple of (imputed_listings, stats)
    """
    area_medians = calculate_area_medians(listings, days_threshold)
    overall_median = calculate_overall_median(listings, days_threshold)

    stats = {
        "overall_median": overall_median,
        "area_medians_count": len(area_medians),
        "area_imputed": 0,
        "overall_imputed": 0,
        "null_days": 0,
    }

    imputed_listings = []
    for listing in listings:
        days_on_market = listing.get("days_on_market")

        if days_on_market is None:
            stats["null_days"] += 1
            imputed_listings.append(listing)
        elif days_on_market > days_threshold:
            old_value = days_on_market
            area = extract_area_from_format(listing.get("area", ""))
            area_median = area_medians.get(area)

            if area_median is not None:
                listing["days_on_market"] = area_median
                listing["days_on_market_imputed"] = True
                listing["days_on_market_imputation_type"] = "area median"
                listing["days_on_market_area"] = area
                stats["area_imputed"] += 1
            else:
                listing["days_on_market"] = overall_median
                listing["days_on_market_imputed"] = True
                listing["days_on_market_imputation_type"] = "overall median"
                stats["overall_imputed"] += 1

            listing["days_on_market_original"] = old_value
            imputed_listings.append(listing)
        else:
            imputed_listings.append(listing)

    return imputed_listings, stats


def process_pipeline(
    input_file: Path,
    production_file: Path,
    output_file: Path,
    min_area_count: int = 5,
    days_threshold: int = 1000,
    dry_run: bool = False,
) -> int:
    """Run the complete data processing pipeline.

    Args:
        input_file: Path to a new ingested listings file
        production_file: Path to existing production data
        output_file: Path to write final processed data
        min_area_count: Minimum listings per area (default: 5)
        days_threshold: Threshold for days_on_market imputation (default: 1000)
        dry_run: If True, don't write output file

    Returns:
        0 on success, 1 on failure
    """
    started_at = datetime.now()
    logger.info(
        "Starting Booli listings data processing pipeline (input=%s, production=%s, output=%s, "
        "min_area_count=%d, days_threshold=%d, dry_run=%s)",
        input_file,
        production_file,
        output_file,
        min_area_count,
        days_threshold,
        dry_run,
    )

    # STEP 1: MERGE & DEDUPLICATE
    logger.info("Step 1/3: merge and deduplicate")
    new_listings = load_jsonl_file(input_file)
    logger.info("Loaded %d new listings", len(new_listings))
    existing_listings = load_jsonl_file(production_file)
    logger.info("Loaded %d existing listings", len(existing_listings))

    merged_listings, merge_stats = merge_listings(new_listings, existing_listings)
    logger.info(
        "Merge summary: existing=%d, new=%d, duplicates=%d (replaced=%d), corrupted=%d, "
        "added=%d, final=%d",
        merge_stats["existing_count"],
        merge_stats["new_count"],
        merge_stats["duplicates"],
        merge_stats["duplicates_replaced"],
        merge_stats["corrupted"],
        merge_stats["added"],
        merge_stats["final_count"],
    )
    if merge_stats.get("existing_missing_id") or merge_stats.get("existing_corrupted"):
        logger.info(
            "Existing filtered: missing_id=%d, corrupted=%d",
            merge_stats.get("existing_missing_id", 0),
            merge_stats.get("existing_corrupted", 0),
        )

    # STEP 2: CLEAN AREAS
    logger.info("Step 2/3: clean and standardize areas")
    cleaned_listings, area_stats = apply_area_cleaning(merged_listings, min_area_count)
    logger.info(
        "Area cleaning summary: unique_before=%d, unique_after=%d, consolidated=%d",
        area_stats["unique_areas_before"],
        area_stats["unique_areas_after"],
        area_stats["consolidated_areas"],
    )

    # STEP 3: IMPUTE DAYS_ON_MARKET
    logger.info("Step 3/3: impute days_on_market values > %d", days_threshold)
    final_listings, impute_stats = impute_days_on_market(cleaned_listings, days_threshold)
    logger.info(
        "Imputation summary: overall_median=%d, area_medians=%d areas, area_imputed=%d, "
        "overall_imputed=%d, null=%d, total_imputed=%d",
        impute_stats["overall_median"],
        impute_stats["area_medians_count"],
        impute_stats["area_imputed"],
        impute_stats["overall_imputed"],
        impute_stats["null_days"],
        impute_stats["area_imputed"] + impute_stats["overall_imputed"],
    )

    # WRITE OUTPUT
    if dry_run:
        logger.info("Dry run: would write %d listings to %s", len(final_listings), output_file)
    else:
        logger.info("Writing %d listings to %s", len(final_listings), output_file)
        with open(output_file, "w", encoding="utf-8") as f:
            for listing in final_listings:
                f.write(json.dumps(listing, ensure_ascii=False) + "\n")
        logger.info("Successfully wrote %d listings", len(final_listings))

    # FINAL SUMMARY
    elapsed = (datetime.now() - started_at).total_seconds()
    logger.info(
        "Pipeline complete in %.1fs: input=%d new + %d existing → output=%d "
        "(net change %+d, %d unique areas, imputed %d)",
        elapsed,
        len(new_listings),
        len(existing_listings),
        len(final_listings),
        len(final_listings) - len(existing_listings),
        area_stats["unique_areas_after"],
        impute_stats["area_imputed"] + impute_stats["overall_imputed"],
    )

    return 0
