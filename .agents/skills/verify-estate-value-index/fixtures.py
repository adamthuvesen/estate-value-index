"""Synthetic listing frame for the verify drives. Seeded; no real listing appears here."""

import random
from datetime import date, timedelta
from typing import Any

SEED = 20261112
ROWS = 400
AREAS = (
    ("Södermalm", "Stockholm", 59.315, 18.07, 1.35),
    ("Östermalm", "Stockholm", 59.337, 18.08, 1.6),
    ("Vasastan", "Stockholm", 59.343, 18.05, 1.3),
    ("Kungsholmen", "Stockholm", 59.333, 18.03, 1.25),
    ("Hägersten", "Stockholm", 59.296, 18.0, 0.9),
    ("Solna", "Solna", 59.36, 18.0, 1.0),
)
FIRST_SOLD = date(2024, 1, 8)
SOLD_SPAN_DAYS = 700


def synthetic_listings(rows: int = ROWS, seed: int = SEED) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    listings: list[dict[str, Any]] = []
    for index in range(rows):
        area, municipality, lat, lon, factor = rng.choice(AREAS)
        living_area = round(rng.uniform(45, 130), 1)
        rooms = max(1, min(6, round(living_area / 28 + rng.uniform(-0.6, 0.6))))
        construction_year = rng.randint(1900, 2022)
        monthly_fee = int(living_area * rng.uniform(40, 60))
        floor = rng.randint(0, 9)
        elevator = floor > 2 and rng.random() < 0.8
        balcony = rng.random() < 0.5
        sold_date = FIRST_SOLD + timedelta(days=rng.randint(0, SOLD_SPAN_DAYS))
        trend = 1 + 0.03 * (sold_date - FIRST_SOLD).days / 365
        sold_price = int(
            living_area
            * 100_000
            * factor
            * trend
            * (1 + 0.04 * elevator + 0.03 * balcony)
            * rng.uniform(0.9, 1.1)
        )
        listing_price = int(sold_price * rng.uniform(0.95, 1.05))
        days_on_market = rng.randint(3, 60)
        scraped = sold_date - timedelta(days=days_on_market)
        listings.append(
            {
                "listing_id": f"SYN-{index:05d}",
                "url": None,
                "scraped_at": f"{scraped.isoformat()}T08:00:00",
                "scraped_at_date": scraped.isoformat(),
                "listing_price": listing_price,
                "sold_price": sold_price,
                "address": f"Syntetgatan {index % 90 + 1}",
                "area": area,
                "area_original": area,
                "municipality": municipality,
                "latitude": round(lat + rng.uniform(-0.01, 0.01), 5),
                "longitude": round(lon + rng.uniform(-0.01, 0.01), 5),
                "living_area": living_area,
                "rooms": rooms,
                "property_type": "Lägenhet",
                "construction_year": construction_year,
                "monthly_fee": monthly_fee,
                "price_per_sqm": int(sold_price / living_area),
                "floor": floor,
                "elevator": elevator,
                "balcony": balcony,
                "sold_date": sold_date.isoformat(),
                "days_on_market": days_on_market,
                "price_change": sold_price - listing_price,
                "description": None,
                "images": [],
                "source_page": "synthetic",
            }
        )
    return listings
