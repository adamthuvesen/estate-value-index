"""Generate comprehensive area statistics for the web UI.

Aggregates data from multiple sources:
- feature_context.json: Pre-computed area-level metrics from model training
- value_analysis.json: Property-level predictions and value scores
- booli_listings_prod.json: Raw listing data with property details

Output: area_statistics.json with analytics for each of the 36 Stockholm areas
"""

import json
import logging
import statistics
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from estate_value_index.ingestion.processing import load_jsonl_file as load_jsonl
from estate_value_index.ml.area_names import get_display_name
from estate_value_index.ml.preprocessing import normalize_area_for_model

logger = logging.getLogger(__name__)


def load_json(filepath: Path) -> dict:
    with open(filepath, encoding="utf-8") as f:
        return json.load(f)


def resolve_generated_at(feature_context: dict, value_analysis: dict) -> str:
    """Resolve a best-effort generated_at timestamp for metadata."""
    candidates = [
        feature_context.get("reference_date"),
        value_analysis.get("metadata", {}).get("generated_at"),
    ]

    for candidate in candidates:
        if not candidate:
            continue
        if isinstance(candidate, str):
            return candidate
        if hasattr(candidate, "isoformat"):
            return candidate.isoformat()
        return str(candidate)

    return datetime.now(UTC).isoformat()


def _normalize_sold_date(value: str | None) -> str | None:
    """Normalize sold_date to YYYY-MM-DD when possible."""
    if not value:
        return None
    if isinstance(value, str):
        return value[:10]
    if hasattr(value, "date"):
        return value.date().isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()[:10]
    return str(value)[:10]


def load_raw_listings(data_source: str, raw_listings_path: Path) -> tuple[list[dict], str]:
    """Load raw listings from BigQuery with a local-JSON fallback.

    An *empty* BigQuery result falls back to local JSON (intentional, for local
    dev). A BigQuery *failure* (auth/query error) is surfaced as ``BigQueryError``
    rather than silently swapping to a possibly stale/missing local file — a
    swallowed failure here would yield area statistics computed from the wrong
    data while reporting success.
    """
    if data_source == "bigquery":
        from estate_value_index.ml.data_loader import load_from_bigquery

        try:
            df = load_from_bigquery()
        except ImportError:
            # BigQuery client libraries not installed (local dev) — fall back.
            # A real query/auth failure raises BigQueryError, which propagates.
            logger.warning("BigQuery support not installed, falling back to local JSON")
        else:
            records = json.loads(df.to_json(orient="records", date_format="iso"))
            for record in records:
                sold_date = record.get("sold_date")
                if sold_date:
                    record["sold_date"] = _normalize_sold_date(sold_date)
            if records:
                logger.info("Loaded raw listings from BigQuery")
                return records, "bigquery"
            logger.warning("BigQuery returned no rows, falling back to local JSON")

    records = load_jsonl(raw_listings_path)
    logger.info("Loaded raw listings from local JSON: %s", raw_listings_path)
    return records, raw_listings_path.name


def calculate_price_per_sqm_by_rooms(properties: list[dict]) -> dict[str, dict]:
    """Calculate price-per-sqm stats by room count.

    Returns a dict keyed by "1", "2", "3", "4+" with median/mean/min/max/count.
    """
    room_groups = defaultdict(list)

    for prop in properties:
        rooms = prop.get("rooms")
        living_area = prop.get("living_area")
        sold_price = prop.get("sold_price")

        if not all([rooms, living_area, sold_price]):
            continue

        price_per_sqm = sold_price / living_area

        if rooms == 1:
            room_groups["1"].append(price_per_sqm)
        elif rooms == 2:
            room_groups["2"].append(price_per_sqm)
        elif rooms == 3:
            room_groups["3"].append(price_per_sqm)
        elif rooms >= 4:
            room_groups["4+"].append(price_per_sqm)

    result = {}
    for room_key, prices in room_groups.items():
        if prices:
            result[room_key] = {
                "median": round(statistics.median(prices)),
                "mean": round(statistics.mean(prices)),
                "min": round(min(prices)),
                "max": round(max(prices)),
                "count": len(prices),
            }

    return result


def calculate_amenity_prevalence(properties: list[dict]) -> dict[str, float]:
    total = len(properties)
    if total == 0:
        return {}

    elevator_count = sum(1 for p in properties if p.get("elevator") is True)
    balcony_count = sum(1 for p in properties if p.get("balcony") is True)

    return {
        "elevator_pct": round(elevator_count / total * 100, 1),
        "balcony_pct": round(balcony_count / total * 100, 1),
    }


def calculate_size_distribution(properties: list[dict]) -> dict[str, Any]:
    living_areas = [p.get("living_area") for p in properties if p.get("living_area")]
    rooms = [p.get("rooms") for p in properties if p.get("rooms")]

    room_counts = defaultdict(int)
    for r in rooms:
        if r == 1:
            room_counts["1"] += 1
        elif r == 2:
            room_counts["2"] += 1
        elif r == 3:
            room_counts["3"] += 1
        elif r >= 4:
            room_counts["4+"] += 1

    return {
        "living_area": {
            "median": round(statistics.median(living_areas)) if living_areas else None,
            "mean": round(statistics.mean(living_areas)) if living_areas else None,
            "min": round(min(living_areas)) if living_areas else None,
            "max": round(max(living_areas)) if living_areas else None,
        },
        "room_distribution": dict(room_counts),
    }


def calculate_value_tier_distribution(value_properties: list[dict]) -> dict[str, int]:
    tier_counts = defaultdict(int)
    for prop in value_properties:
        tier_counts[prop.get("value_tier", "Unknown")] += 1
    return dict(tier_counts)


def calculate_construction_era_distribution(properties: list[dict]) -> dict[str, Any]:
    """Bucket construction years into eras: Pre-1900, 1900-1950, 1950-1980, 1980-2000, 2000+."""
    construction_years = [
        p.get("construction_year") for p in properties if p.get("construction_year")
    ]

    if not construction_years:
        return {
            "median_year": None,
            "oldest": None,
            "newest": None,
            "era_distribution": {},
            "avg_age": None,
        }

    current_year = datetime.now().year

    era_counts = defaultdict(int)
    for year in construction_years:
        if year < 1900:
            era_counts["Pre-1900"] += 1
        elif year < 1950:
            era_counts["1900-1950"] += 1
        elif year < 1980:
            era_counts["1950-1980"] += 1
        elif year < 2000:
            era_counts["1980-2000"] += 1
        else:
            era_counts["2000+"] += 1

    ages = [current_year - year for year in construction_years]

    return {
        "median_year": round(statistics.median(construction_years)),
        "oldest": min(construction_years),
        "newest": max(construction_years),
        "era_distribution": dict(era_counts),
        "avg_age": round(statistics.mean(ages)),
    }


def calculate_monthly_median_prices(properties: list[dict], months: int = 12) -> dict[str, Any]:
    """Median sold price per month for the last N months. month_1 is the most recent."""
    from dateutil.relativedelta import relativedelta

    now = datetime.now()

    # Map (year, month) → "month_N" label so we can bucket every property in a
    # single pass instead of re-parsing each `sold_date` once per month window.
    target_labels: dict[tuple[int, int], str] = {}
    for month_back in range(1, months + 1):
        target_date = now - relativedelta(months=month_back)
        target_labels[(target_date.year, target_date.month)] = f"month_{month_back}"

    buckets: dict[str, list[float]] = {label: [] for label in target_labels.values()}

    for prop in properties:
        sold_date_str = prop.get("sold_date")
        sold_price = prop.get("sold_price")
        if not sold_date_str or not sold_price:
            continue
        try:
            sold_date = datetime.strptime(sold_date_str, "%Y-%m-%d")
        except (ValueError, TypeError):
            continue
        label = target_labels.get((sold_date.year, sold_date.month))
        if label is not None:
            buckets[label].append(sold_price)

    return {
        label: (round(statistics.median(prices)) if prices else None)
        for label, prices in buckets.items()
    }


def calculate_market_dynamics(properties: list[dict]) -> dict[str, Any]:
    """Compute days_on_market_median, price_change_mean, volatility (stdev of price/sqm), inventory."""
    days_on_market_values = []
    price_changes = []
    price_per_sqm_values = []

    for prop in properties:
        dom = prop.get("days_on_market")
        if dom is not None and dom > 0:
            days_on_market_values.append(dom)

        price_change = prop.get("price_change")
        if price_change is not None:
            price_changes.append(price_change)
        elif prop.get("sold_price") and prop.get("listing_price"):
            price_changes.append(prop.get("sold_price") - prop.get("listing_price"))

        price_per_sqm = prop.get("price_per_sqm")
        if price_per_sqm is not None:
            price_per_sqm_values.append(price_per_sqm)
        elif prop.get("sold_price") and prop.get("living_area") and prop.get("living_area") > 0:
            price_per_sqm_values.append(prop.get("sold_price") / prop.get("living_area"))

    volatility = (
        round(statistics.stdev(price_per_sqm_values)) if len(price_per_sqm_values) > 1 else 0
    )
    avg_price_per_sqm = (
        round(statistics.mean(price_per_sqm_values)) if price_per_sqm_values else None
    )

    return {
        "days_on_market_median": round(statistics.median(days_on_market_values))
        if days_on_market_values
        else 0,
        "price_change_mean": round(statistics.mean(price_changes)) if price_changes else 0,
        "volatility": volatility,
        "inventory": len(properties),
        "avg_price_per_sqm": avg_price_per_sqm,
    }


def filter_properties_by_room_count(properties: list[dict], room_filter: str) -> list[dict]:
    """Filter by room count: "all", "1", "2", "3", or "4+"."""
    if room_filter == "all":
        return properties

    filtered = []
    for prop in properties:
        rooms = prop.get("rooms")
        if rooms is None:
            continue

        if room_filter == "1" and rooms == 1:
            filtered.append(prop)
        elif room_filter == "2" and rooms == 2:
            filtered.append(prop)
        elif room_filter == "3" and rooms == 3:
            filtered.append(prop)
        elif room_filter == "4+" and rooms >= 4:
            filtered.append(prop)

    return filtered


def calculate_room_filtered_statistics(
    raw_props: list[dict],
    value_props: list[dict],
    room_filter: str,
    feature_context: dict,
    area_key: str,
) -> dict[str, Any]:
    """All statistics for a specific room-count filter; returns None if no properties match."""
    filtered_raw = filter_properties_by_room_count(raw_props, room_filter)
    filtered_value = filter_properties_by_room_count(value_props, room_filter)

    if not filtered_raw:
        return None

    market_dynamics_filtered = calculate_market_dynamics(filtered_raw)
    value_scores = [p.get("value_score", 50) for p in filtered_value]
    prediction_deltas = [p.get("prediction_delta_absolute", 0) for p in filtered_value]
    undervalued_count = sum(1 for p in filtered_value if p.get("is_undervalued", False))

    return {
        "overview": {
            "avg_listing_price": round(
                statistics.mean(
                    [p.get("listing_price", 0) for p in filtered_raw if p.get("listing_price")]
                )
                if any(p.get("listing_price") for p in filtered_raw)
                else feature_context.get("area_avg_price", {}).get(area_key, 0)
            ),
            "avg_sold_price": round(
                statistics.mean(
                    [p.get("sold_price", 0) for p in filtered_raw if p.get("sold_price")]
                )
                if any(p.get("sold_price") for p in filtered_raw)
                else feature_context.get("area_target_mean", {}).get(area_key, 0)
            ),
            "avg_price_per_sqm": market_dynamics_filtered.get("avg_price_per_sqm"),
            "listing_count": len(filtered_raw),
            "inventory": len(filtered_raw),
            # Monthly/volume series intentionally skipped for room-filtered views
            "median_price_3m": None,
            "median_price_6m": None,
            "median_price_12m": None,
        },
        "market_dynamics": {
            "volatility": market_dynamics_filtered["volatility"],
            "days_on_market_median": market_dynamics_filtered["days_on_market_median"],
            "price_change_mean": market_dynamics_filtered["price_change_mean"],
            "sales_volume_3m": 0,
            "sales_volume_6m": 0,
            "sales_volume_12m": 0,
            "liquidity": round(
                len(filtered_raw) / max(market_dynamics_filtered["days_on_market_median"], 1), 2
            ),
        },
        "value_insights": {
            "undervalued_count": undervalued_count,
            "undervalued_pct": round(undervalued_count / len(filtered_value) * 100, 1)
            if filtered_value
            else 0,
            "avg_value_score": round(statistics.mean(value_scores), 1) if value_scores else 50.0,
            "median_value_score": round(statistics.median(value_scores), 1)
            if value_scores
            else 50.0,
            "avg_prediction_delta": round(statistics.mean(prediction_deltas))
            if prediction_deltas
            else 0,
            "value_tier_distribution": calculate_value_tier_distribution(filtered_value),
        },
        "property_characteristics": calculate_amenity_prevalence(filtered_raw),
        "construction_era": calculate_construction_era_distribution(filtered_raw),
        "recent_properties": get_recent_properties(filtered_raw, limit=10),
        "property_count": len(filtered_raw),
    }


def get_recent_properties(properties: list[dict], limit: int = 10) -> list[dict]:
    """Most recent properties, sorted by sold_date descending."""
    dated_props = [p for p in properties if p.get("sold_date")]
    sorted_props = sorted(dated_props, key=lambda x: x.get("sold_date", ""), reverse=True)

    result = []
    for prop in sorted_props[:limit]:
        price_per_sqm = prop.get("price_per_sqm")
        if price_per_sqm is None:
            sold_price = prop.get("sold_price")
            living_area = prop.get("living_area")
            if sold_price and living_area and living_area > 0:
                price_per_sqm = round(sold_price / living_area)

        result.append(
            {
                "listing_id": prop.get("listing_id"),
                "url": prop.get("url"),
                "address": prop.get("address"),
                "sold_price": prop.get("sold_price"),
                "sold_date": prop.get("sold_date"),
                "living_area": prop.get("living_area"),
                "rooms": prop.get("rooms"),
                "price_per_sqm": price_per_sqm,
            }
        )

    return result


def generate_area_statistics(
    *,
    data_source: str = "bigquery",
    feature_context_path: Path | None = None,
    value_analysis_path: Path | None = None,
    raw_listings_path: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Main function to generate area statistics."""

    # Paths
    project_root = Path(__file__).resolve().parents[3]
    feature_context_path = feature_context_path or (
        project_root / "web" / "models" / "price_prediction_model_feature_context.json"
    )
    value_analysis_path = value_analysis_path or (
        project_root / "data" / "enrichment" / "value_analysis.json"
    )
    raw_listings_path = raw_listings_path or (
        project_root / "data" / "raw" / "booli" / "booli_listings_prod.json"
    )
    output_path = output_path or (project_root / "data" / "enrichment" / "area_statistics.json")

    logger.info("Loading data sources...")

    feature_context = load_json(feature_context_path)
    value_analysis = load_json(value_analysis_path)
    raw_listings, raw_listings_source = load_raw_listings(data_source, raw_listings_path)

    logger.info("Loaded %d raw listings", len(raw_listings))
    logger.info("Loaded %d value analysis properties", len(value_analysis.get("properties", [])))

    listings_by_area = defaultdict(list)
    for listing in raw_listings:
        area_key = normalize_area_for_model(listing.get("area", ""))
        listings_by_area[area_key].append(listing)

    value_props_by_area = defaultdict(list)
    for prop in value_analysis.get("properties", []):
        area_key = normalize_area_for_model(prop.get("area", ""))
        value_props_by_area[area_key].append(prop)

    area_stats = {}
    areas = feature_context.get("area_avg_price", {}).keys()

    logger.info("Generating statistics for %d areas...", len(areas))

    for area_key in sorted(areas):
        logger.debug("Processing %s...", area_key)

        raw_props = listings_by_area.get(area_key, [])
        value_props = value_props_by_area.get(area_key, [])

        if len(raw_props) < 2:
            logger.debug("Skipping %s - only %d properties", area_key, len(raw_props))
            continue

        # Calculate market dynamics directly from raw data (more accurate than feature_context)
        market_dynamics_raw = calculate_market_dynamics(raw_props)

        undervalued_count = sum(1 for p in value_props if p.get("is_undervalued", False))
        value_scores = [p.get("value_score", 50) for p in value_props]
        prediction_deltas = [p.get("prediction_delta_absolute", 0) for p in value_props]

        monthly_prices = calculate_monthly_median_prices(raw_props, months=12)

        by_room_count = {}
        for room_filter in ["all", "1", "2", "3", "4+"]:
            room_stats = calculate_room_filtered_statistics(
                raw_props, value_props, room_filter, feature_context, area_key
            )
            if room_stats:
                by_room_count[room_filter] = room_stats

        area_stats[area_key] = {
            "area_name": area_key,
            "display_name": get_display_name(area_key),
            "price_tier": feature_context.get("area_price_tier", {}).get(area_key, "medium"),
            # Overview metrics for "all rooms" — consumed by the area web UI.
            "overview": {
                "avg_listing_price": round(
                    feature_context.get("area_avg_price", {}).get(area_key, 0)
                ),
                "avg_sold_price": round(
                    feature_context.get("area_target_mean", {}).get(area_key, 0)
                ),
                "avg_price_per_sqm": market_dynamics_raw.get("avg_price_per_sqm"),
                "listing_count": len(raw_props),
                "inventory": market_dynamics_raw["inventory"],
                "median_price_3m": feature_context.get("area_median_price_3m", {}).get(area_key),
                "median_price_6m": feature_context.get("area_median_price_6m", {}).get(area_key),
                "median_price_12m": feature_context.get("area_median_price_12m", {}).get(area_key),
                "monthly_prices": monthly_prices,
            },
            "market_dynamics": {
                "volatility": market_dynamics_raw["volatility"],
                "days_on_market_median": market_dynamics_raw["days_on_market_median"],
                "price_change_mean": market_dynamics_raw["price_change_mean"],
                "sales_volume_3m": feature_context.get("area_sales_volume_3m", {}).get(area_key, 0),
                "sales_volume_6m": feature_context.get("area_sales_volume_6m", {}).get(area_key, 0),
                "sales_volume_12m": feature_context.get("area_sales_volume_12m", {}).get(
                    area_key, 0
                ),
                "liquidity": round(
                    market_dynamics_raw["inventory"]
                    / max(market_dynamics_raw["days_on_market_median"], 1),
                    2,
                ),
            },
            "value_insights": {
                "undervalued_count": undervalued_count,
                "undervalued_pct": round(undervalued_count / len(value_props) * 100, 1)
                if value_props
                else 0,
                "avg_value_score": round(statistics.mean(value_scores), 1)
                if value_scores
                else 50.0,
                "median_value_score": round(statistics.median(value_scores), 1)
                if value_scores
                else 50.0,
                "avg_prediction_delta": round(statistics.mean(prediction_deltas))
                if prediction_deltas
                else 0,
                "value_tier_distribution": calculate_value_tier_distribution(value_props),
            },
            "size_analysis": {
                "price_per_sqm_by_rooms": calculate_price_per_sqm_by_rooms(raw_props),
                "size_distribution": calculate_size_distribution(raw_props),
            },
            "property_characteristics": calculate_amenity_prevalence(raw_props),
            "construction_era": calculate_construction_era_distribution(raw_props),
            "recent_properties": get_recent_properties(raw_props, limit=10),
            "by_room_count": by_room_count,
            "has_limited_data": len(raw_props) < 10,
            "sample_size": len(raw_props),
        }

    output_data = {
        "metadata": {
            "generated_at": resolve_generated_at(feature_context, value_analysis),
            "total_areas": len(area_stats),
            "total_properties": len(raw_listings),
            "data_sources": {
                "feature_context": str(feature_context_path.name),
                "value_analysis": str(value_analysis_path.name),
                "raw_listings": str(raw_listings_source),
            },
        },
        "areas": area_stats,
    }

    logger.info("Writing output to %s...", output_path)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    logger.info("Generated statistics for %d areas -> %s", len(area_stats), output_path)

    logger.info("Area Summary:")
    for _, stats in sorted(area_stats.items(), key=lambda x: x[1]["sample_size"], reverse=True)[
        :10
    ]:
        flag = " LIMITED DATA" if stats["has_limited_data"] else ""
        logger.info(
            "  %-30s - %4d properties - %-8s%s",
            stats["display_name"],
            stats["sample_size"],
            stats["price_tier"],
            flag,
        )

    return output_data
