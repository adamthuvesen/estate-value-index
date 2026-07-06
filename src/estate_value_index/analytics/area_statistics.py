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
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from estate_value_index.ingestion.processing import load_jsonl_file as load_jsonl
from estate_value_index.ml.area_names import get_display_name
from estate_value_index.ml.preprocessing import normalize_area_for_model

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AreaStatisticsPaths:
    feature_context: Path
    value_analysis: Path
    raw_listings: Path
    output: Path


def load_json(filepath: Path) -> dict:
    with open(filepath, encoding="utf-8") as f:
        return json.load(f)


def _latest_sold_date(raw_listings: list[dict]) -> str | None:
    """Newest sold_date (YYYY-MM-DD) across the listings, or None if undated."""
    dates = [
        normalized
        for listing in raw_listings
        if (normalized := _normalize_sold_date(listing.get("sold_date")))
    ]
    return max(dates) if dates else None


def resolve_generated_at(
    raw_listings: list[dict], feature_context: dict, value_analysis: dict
) -> str:
    """Resolve a best-effort "data as of" date for metadata.

    Prefer the newest sold_date in the data — that is what "Updated" and the
    staleness banner mean. The model's reference_date is the training cutoff and
    lags the data whenever listings are refreshed without a retrain, so it's only
    a fallback.
    """
    candidates = [
        _latest_sold_date(raw_listings),
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


# Living-area buckets (m²) for the size -> price histogram: inclusive lower,
# exclusive upper, with an open-ended final bucket.
_SIZE_BUCKETS: list[tuple[str, float, float]] = [
    ("<40", 0, 40),
    ("40–50", 40, 50),
    ("50–60", 50, 60),
    ("60–70", 60, 70),
    ("70–80", 70, 80),
    ("80–90", 80, 90),
    ("90–100", 90, 100),
    ("100–120", 100, 120),
    ("120+", 120, float("inf")),
]


def calculate_price_by_size(properties: list[dict]) -> list[dict]:
    """Median sold price per living-area bucket, for the size -> price histogram.

    Returns an ordered list of ``{bucket, median_price, count}`` for the buckets
    that hold at least one property, so the x-axis reads small -> large m².
    """
    bucket_prices: dict[str, list[float]] = {label: [] for label, _, _ in _SIZE_BUCKETS}

    for prop in properties:
        living_area = prop.get("living_area")
        sold_price = prop.get("sold_price")
        if not living_area or not sold_price:
            continue
        for label, low, high in _SIZE_BUCKETS:
            if low <= living_area < high:
                bucket_prices[label].append(sold_price)
                break

    return [
        {
            "bucket": label,
            "median_price": round(statistics.median(bucket_prices[label])),
            "count": len(bucket_prices[label]),
        }
        for label, _, _ in _SIZE_BUCKETS
        if bucket_prices[label]
    ]


def calculate_size_distribution(properties: list[dict]) -> dict[str, Any]:
    living_areas = [p.get("living_area") for p in properties if p.get("living_area")]
    rooms = [p.get("rooms") for p in properties if p.get("rooms")]

    room_counts = defaultdict(int)
    for r in rooms:
        bucket = _room_bucket(r)
        if bucket:
            room_counts[bucket] += 1

    return {
        "living_area": {
            "median": round(statistics.median(living_areas)) if living_areas else None,
            "mean": round(statistics.mean(living_areas)) if living_areas else None,
            "min": round(min(living_areas)) if living_areas else None,
            "max": round(max(living_areas)) if living_areas else None,
        },
        "room_distribution": dict(room_counts),
    }


def _room_bucket(rooms: int | float | None) -> str | None:
    if rooms == 1:
        return "1"
    if rooms == 2:
        return "2"
    if rooms == 3:
        return "3"
    if rooms is not None and rooms >= 4:
        return "4+"
    return None


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
    days_on_market_values = _positive_days_on_market(properties)
    price_changes = _price_change_values(properties)
    price_per_sqm_values = _price_per_sqm_values(properties)

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


def _positive_days_on_market(properties: list[dict]) -> list[float]:
    return [
        prop.get("days_on_market")
        for prop in properties
        if prop.get("days_on_market") is not None and prop.get("days_on_market") > 0
    ]


def _price_change_values(properties: list[dict]) -> list[float]:
    values = []
    for prop in properties:
        price_change = prop.get("price_change")
        if price_change is not None:
            values.append(price_change)
            continue

        sold_price = prop.get("sold_price")
        listing_price = prop.get("listing_price")
        if sold_price and listing_price:
            values.append(sold_price - listing_price)
    return values


def _price_per_sqm_values(properties: list[dict]) -> list[float]:
    values = []
    for prop in properties:
        value = _price_per_sqm_value(prop)
        if value is not None:
            values.append(value)
    return values


def _price_per_sqm_value(prop: dict) -> float | None:
    price_per_sqm = prop.get("price_per_sqm")
    if price_per_sqm is not None:
        return price_per_sqm

    sold_price = prop.get("sold_price")
    living_area = prop.get("living_area")
    if sold_price and living_area and living_area > 0:
        return sold_price / living_area
    return None


def filter_properties_by_room_count(properties: list[dict], room_filter: str) -> list[dict]:
    """Filter by room count: "all", "1", "2", "3", or "4+"."""
    if room_filter == "all":
        return properties

    filtered = []
    for prop in properties:
        if _room_bucket(prop.get("rooms")) == room_filter:
            filtered.append(prop)

    return filtered


def _mean_price_or_feature_value(
    properties: list[dict],
    property_key: str,
    feature_context: dict,
    feature_key: str,
    area_key: str,
) -> int:
    prices = [p.get(property_key, 0) for p in properties if p.get(property_key)]
    fallback = feature_context.get(feature_key, {}).get(area_key, 0)
    return round(statistics.mean(prices) if prices else fallback)


def _value_insights(value_properties: list[dict]) -> dict[str, Any]:
    undervalued_count = sum(1 for p in value_properties if p.get("is_undervalued", False))
    value_scores = [p.get("value_score", 50) for p in value_properties]
    prediction_deltas = [p.get("prediction_delta_absolute", 0) for p in value_properties]

    return {
        "undervalued_count": undervalued_count,
        "undervalued_pct": round(undervalued_count / len(value_properties) * 100, 1)
        if value_properties
        else 0,
        "avg_value_score": round(statistics.mean(value_scores), 1) if value_scores else 50.0,
        "median_value_score": round(statistics.median(value_scores), 1) if value_scores else 50.0,
        "avg_prediction_delta": round(statistics.mean(prediction_deltas))
        if prediction_deltas
        else 0,
        "value_tier_distribution": calculate_value_tier_distribution(value_properties),
    }


def _room_filtered_overview(
    filtered_raw: list[dict],
    market_dynamics: dict[str, Any],
    feature_context: dict,
    area_key: str,
) -> dict[str, Any]:
    return {
        "avg_listing_price": _mean_price_or_feature_value(
            filtered_raw, "listing_price", feature_context, "area_avg_price", area_key
        ),
        "avg_sold_price": _mean_price_or_feature_value(
            filtered_raw, "sold_price", feature_context, "area_target_mean", area_key
        ),
        "avg_price_per_sqm": market_dynamics.get("avg_price_per_sqm"),
        "listing_count": len(filtered_raw),
        "inventory": len(filtered_raw),
        # Monthly/volume series intentionally skipped for room-filtered views
        "median_price_3m": None,
        "median_price_6m": None,
        "median_price_12m": None,
    }


def _room_filtered_market_dynamics(
    filtered_raw: list[dict],
    market_dynamics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "volatility": market_dynamics["volatility"],
        "days_on_market_median": market_dynamics["days_on_market_median"],
        "price_change_mean": market_dynamics["price_change_mean"],
        "sales_volume_3m": 0,
        "sales_volume_6m": 0,
        "sales_volume_12m": 0,
        "liquidity": round(len(filtered_raw) / max(market_dynamics["days_on_market_median"], 1), 2),
    }


def calculate_room_filtered_statistics(
    raw_props: list[dict],
    value_props: list[dict],
    room_filter: str,
    feature_context: dict,
    area_key: str,
) -> dict[str, Any] | None:
    """All statistics for a specific room-count filter; returns None if no properties match."""
    filtered_raw = filter_properties_by_room_count(raw_props, room_filter)
    filtered_value = filter_properties_by_room_count(value_props, room_filter)

    if not filtered_raw:
        return None

    market_dynamics_filtered = calculate_market_dynamics(filtered_raw)

    return {
        "overview": _room_filtered_overview(
            filtered_raw, market_dynamics_filtered, feature_context, area_key
        ),
        "market_dynamics": _room_filtered_market_dynamics(filtered_raw, market_dynamics_filtered),
        "value_insights": _value_insights(filtered_value),
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


def _resolve_area_statistics_paths(
    feature_context_path: Path | None,
    value_analysis_path: Path | None,
    raw_listings_path: Path | None,
    output_path: Path | None,
) -> AreaStatisticsPaths:
    project_root = Path(__file__).resolve().parents[3]
    return AreaStatisticsPaths(
        feature_context=feature_context_path
        or project_root / "web" / "models" / "price_prediction_model_no_list_feature_context.json",
        value_analysis=value_analysis_path
        or project_root / "data" / "enrichment" / "value_analysis.json",
        raw_listings=raw_listings_path
        or project_root / "data" / "raw" / "booli" / "booli_listings_prod.json",
        output=output_path or project_root / "data" / "enrichment" / "area_statistics.json",
    )


def _group_by_area(properties: list[dict]) -> defaultdict[str, list[dict]]:
    grouped: defaultdict[str, list[dict]] = defaultdict(list)
    for prop in properties:
        area_key = normalize_area_for_model(prop.get("area", ""))
        grouped[area_key].append(prop)
    return grouped


def _room_count_statistics(
    raw_props: list[dict],
    value_props: list[dict],
    feature_context: dict,
    area_key: str,
) -> dict[str, Any]:
    by_room_count = {}
    for room_filter in ["all", "1", "2", "3", "4+"]:
        room_stats = calculate_room_filtered_statistics(
            raw_props, value_props, room_filter, feature_context, area_key
        )
        if room_stats:
            by_room_count[room_filter] = room_stats
    return by_room_count


def _area_overview(
    area_key: str,
    raw_props: list[dict],
    feature_context: dict,
    market_dynamics: dict[str, Any],
    monthly_prices: dict[str, Any],
) -> dict[str, Any]:
    return {
        "avg_listing_price": round(feature_context.get("area_avg_price", {}).get(area_key, 0)),
        "avg_sold_price": round(feature_context.get("area_target_mean", {}).get(area_key, 0)),
        "avg_price_per_sqm": market_dynamics.get("avg_price_per_sqm"),
        "listing_count": len(raw_props),
        "inventory": market_dynamics["inventory"],
        "median_price_3m": feature_context.get("area_median_price_3m", {}).get(area_key),
        "median_price_6m": feature_context.get("area_median_price_6m", {}).get(area_key),
        "median_price_12m": feature_context.get("area_median_price_12m", {}).get(area_key),
        "monthly_prices": monthly_prices,
    }


def _area_market_dynamics(
    area_key: str,
    feature_context: dict,
    market_dynamics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "volatility": market_dynamics["volatility"],
        "days_on_market_median": market_dynamics["days_on_market_median"],
        "price_change_mean": market_dynamics["price_change_mean"],
        "sales_volume_3m": feature_context.get("area_sales_volume_3m", {}).get(area_key, 0),
        "sales_volume_6m": feature_context.get("area_sales_volume_6m", {}).get(area_key, 0),
        "sales_volume_12m": feature_context.get("area_sales_volume_12m", {}).get(area_key, 0),
        "liquidity": round(
            market_dynamics["inventory"] / max(market_dynamics["days_on_market_median"], 1),
            2,
        ),
    }


def _area_statistics_entry(
    area_key: str,
    raw_props: list[dict],
    value_props: list[dict],
    feature_context: dict,
) -> dict[str, Any]:
    market_dynamics = calculate_market_dynamics(raw_props)
    monthly_prices = calculate_monthly_median_prices(raw_props, months=12)

    return {
        "area_name": area_key,
        "display_name": get_display_name(area_key),
        "price_tier": feature_context.get("area_price_tier", {}).get(area_key, "medium"),
        "overview": _area_overview(
            area_key, raw_props, feature_context, market_dynamics, monthly_prices
        ),
        "market_dynamics": _area_market_dynamics(area_key, feature_context, market_dynamics),
        "value_insights": _value_insights(value_props),
        "size_analysis": {
            "price_per_sqm_by_rooms": calculate_price_per_sqm_by_rooms(raw_props),
            "price_by_size": calculate_price_by_size(raw_props),
            "size_distribution": calculate_size_distribution(raw_props),
        },
        "property_characteristics": calculate_amenity_prevalence(raw_props),
        "construction_era": calculate_construction_era_distribution(raw_props),
        "recent_properties": get_recent_properties(raw_props, limit=10),
        "by_room_count": _room_count_statistics(raw_props, value_props, feature_context, area_key),
        "has_limited_data": len(raw_props) < 10,
        "sample_size": len(raw_props),
    }


def _build_area_statistics(
    feature_context: dict,
    raw_listings: list[dict],
    value_properties: list[dict],
) -> dict[str, Any]:
    listings_by_area = _group_by_area(raw_listings)
    value_props_by_area = _group_by_area(value_properties)
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

        area_stats[area_key] = _area_statistics_entry(
            area_key, raw_props, value_props, feature_context
        )

    return area_stats


def _area_statistics_output(
    *,
    feature_context: dict,
    value_analysis: dict,
    raw_listings: list[dict],
    raw_listings_source: str,
    paths: AreaStatisticsPaths,
    area_stats: dict[str, Any],
) -> dict[str, Any]:
    return {
        "metadata": {
            "generated_at": resolve_generated_at(raw_listings, feature_context, value_analysis),
            "total_areas": len(area_stats),
            "total_properties": len(raw_listings),
            "data_sources": {
                "feature_context": str(paths.feature_context.name),
                "value_analysis": str(paths.value_analysis.name),
                "raw_listings": str(raw_listings_source),
            },
        },
        "areas": area_stats,
    }


def _write_area_statistics(output_data: dict[str, Any], output_path: Path) -> None:
    logger.info("Writing output to %s...", output_path)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)


def _log_area_summary(area_stats: dict[str, Any], output_path: Path) -> None:
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


def generate_area_statistics(
    *,
    data_source: str = "bigquery",
    feature_context_path: Path | None = None,
    value_analysis_path: Path | None = None,
    raw_listings_path: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Main function to generate area statistics."""
    paths = _resolve_area_statistics_paths(
        feature_context_path,
        value_analysis_path,
        raw_listings_path,
        output_path,
    )

    logger.info("Loading data sources...")

    feature_context = load_json(paths.feature_context)
    value_analysis = load_json(paths.value_analysis)
    raw_listings, raw_listings_source = load_raw_listings(data_source, paths.raw_listings)

    logger.info("Loaded %d raw listings", len(raw_listings))
    logger.info("Loaded %d value analysis properties", len(value_analysis.get("properties", [])))

    area_stats = _build_area_statistics(
        feature_context,
        raw_listings,
        value_analysis.get("properties", []),
    )
    output_data = _area_statistics_output(
        feature_context=feature_context,
        value_analysis=value_analysis,
        raw_listings=raw_listings,
        raw_listings_source=raw_listings_source,
        paths=paths,
        area_stats=area_stats,
    )

    _write_area_statistics(output_data, paths.output)
    _log_area_summary(area_stats, paths.output)
    return output_data
