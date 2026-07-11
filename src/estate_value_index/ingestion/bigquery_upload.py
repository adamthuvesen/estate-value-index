"""Convert normalized listings to the BigQuery row schema."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def _clean_listing_id(value: Any) -> str:
    listing_id = "" if value is None else str(value).strip()
    if not listing_id or listing_id.lower() == "none":
        raise ValueError("listing_id is required and cannot be blank")
    return listing_id


def prepare_bq_row(item: dict[str, Any]) -> dict[str, Any]:
    """Convert a normalized listing to a BigQuery-compatible row."""
    scraped_at_value = item.get("scraped_at")
    if isinstance(scraped_at_value, str):
        try:
            scraped_at = datetime.fromisoformat(scraped_at_value)
        except ValueError:
            scraped_at = datetime.now(UTC)
    else:
        scraped_at = datetime.now(UTC)

    def to_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None

    def to_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    return {
        "listing_id": _clean_listing_id(item.get("listing_id")),
        "url": item.get("url"),
        "scraped_at": scraped_at.isoformat(),
        "scraped_at_date": scraped_at.date().isoformat(),
        "listing_price": to_int(item.get("listing_price")),
        "sold_price": to_int(item.get("sold_price")),
        "address": item.get("address"),
        "area": item.get("area"),
        "area_original": item.get("area_original"),
        "municipality": item.get("municipality"),
        "latitude": to_float(item.get("latitude", item.get("lat"))),
        "longitude": to_float(item.get("longitude", item.get("lon"))),
        "living_area": item.get("living_area"),
        "rooms": to_int(item.get("rooms")),
        "property_type": item.get("property_type"),
        "construction_year": to_int(item.get("construction_year")),
        "monthly_fee": to_int(item.get("monthly_fee")),
        "price_per_sqm": to_int(item.get("price_per_sqm")),
        "floor": to_int(item.get("floor")),
        "elevator": item.get("elevator"),
        "balcony": item.get("balcony"),
        "sold_date": item.get("sold_date"),
        "days_on_market": to_int(item.get("days_on_market")),
        "price_change": to_int(item.get("price_change")),
        "description": item.get("description"),
        "images": item.get("images", []) or [],
        "source_page": item.get("source_page"),
    }
