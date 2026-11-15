"""The BigQuery raw-listings row contract, checked before every load.

Mirrors ``schemas/bq_raw_listings.json``. ``tests/ingestion/test_listing_row.py``
fails when the two drift apart.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from estate_value_index.exceptions import DataValidationError


class BigQueryListingRow(BaseModel):
    """One row of the raw listings table, in the JSON shape the load job sends."""

    model_config = ConfigDict(extra="forbid", strict=True)

    listing_id: str
    url: str | None
    # The load job sends ISO strings; dates parse in lax mode, everything else is strict.
    scraped_at: datetime = Field(strict=False)
    scraped_at_date: date = Field(strict=False)
    listing_price: int | None
    sold_price: int | None
    address: str | None
    area: str | None
    area_original: str | None
    municipality: str | None
    latitude: float | None
    longitude: float | None
    living_area: float | int | None
    rooms: int | None
    property_type: str | None
    construction_year: int | None
    monthly_fee: int | None
    price_per_sqm: int | None
    floor: int | None
    elevator: bool | None
    balcony: bool | None
    sold_date: date | None = Field(strict=False)
    days_on_market: int | None
    price_change: int | None
    description: str | None
    images: list[str]
    source_page: str | None


def validate_listing_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return ``rows`` unchanged when every row matches the contract.

    Raises ``DataValidationError`` with the count of bad rows and the first few
    errors. Nothing is dropped: one bad row stops the whole load.
    """
    rows = list(rows)
    failures: list[str] = []
    for index, row in enumerate(rows):
        try:
            BigQueryListingRow.model_validate(row)
        except ValidationError as exc:
            failures.append(f"row {index} (listing_id={row.get('listing_id')!r}): {exc}")
    if failures:
        raise DataValidationError(
            f"{len(failures)} of {len(rows)} listing rows fail the BigQuery row contract",
            context={"first_errors": failures[:3]},
        )
    return rows
