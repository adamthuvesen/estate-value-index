"""Signed Booli API client and mappers.

The public Booli HTML pages are now Cloudflare-challenged for automated
clients. Booli's documented API path uses callerId/private-key signing; this
module keeps that authorized path separate from the Scrapy spider.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from estate_value_index.ingestion.booli.normalization import clean_text, to_float, to_int

BOOLI_API_BASE_URL = "https://api.booli.se"
BOOLI_API_ACCEPT = "application/vnd.booli-v2+json"
BOOLI_API_PAGE_SIZE = 500


@dataclass(frozen=True)
class BooliApiCredentials:
    caller_id: str
    private_key: str

    @classmethod
    def from_env(cls) -> BooliApiCredentials:
        caller_id = os.getenv("BOOLI_API_CALLER_ID")
        private_key = os.getenv("BOOLI_API_PRIVATE_KEY")
        missing = [
            name
            for name, value in (
                ("BOOLI_API_CALLER_ID", caller_id),
                ("BOOLI_API_PRIVATE_KEY", private_key),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Booli API credentials are required for --source api: " + ", ".join(missing)
            )
        return cls(caller_id=caller_id or "", private_key=private_key or "")


def signed_api_params(
    credentials: BooliApiCredentials,
    params: Mapping[str, Any],
    *,
    timestamp: int | None = None,
    unique: str | None = None,
) -> dict[str, str]:
    """Return Booli API query params signed as SHA1(callerId + time + key + unique)."""

    api_time = str(timestamp if timestamp is not None else int(time.time()))
    api_unique = unique or secrets.token_hex(8)
    signature = hashlib.sha1(
        f"{credentials.caller_id}{api_time}{credentials.private_key}{api_unique}".encode()
    ).hexdigest()

    signed = _stringify_params(params)
    signed.update(
        {
            "callerId": credentials.caller_id,
            "time": api_time,
            "unique": api_unique,
            "hash": signature,
        }
    )
    return signed


def _stringify_params(params: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in params.items():
        if value is None or value == "":
            continue
        if isinstance(value, (list, tuple, set)):
            result[str(key)] = ",".join(str(item) for item in value)
        else:
            result[str(key)] = str(value)
    return result


def _api_value(value: object) -> object:
    if isinstance(value, dict):
        for key in ("raw", "value", "name", "formatted"):
            if key in value and value[key] not in (None, ""):
                return value[key]
    return value


def _first_value(record: Mapping[str, Any], *keys: str) -> object:
    for key in keys:
        value: object = record
        found = True
        for part in key.split("."):
            if isinstance(value, Mapping) and part in value:
                value = value[part]
            else:
                found = False
                break
        if found and value not in (None, ""):
            return _api_value(value)
    return None


def _location_area(location: Mapping[str, Any]) -> str | None:
    for key in ("namedAreas", "areas", "addressAreas"):
        value = location.get(key)
        if isinstance(value, list):
            for area in value:
                if isinstance(area, Mapping):
                    name = clean_text(_api_value(area.get("name")))
                    if name:
                        return name
                else:
                    name = clean_text(area)
                    if name:
                        return name

    for key in ("areaName", "cityName", "district"):
        name = clean_text(_api_value(location.get(key)))
        if name:
            return name
    return None


def booli_api_record_to_listing(record: Mapping[str, Any], *, source: str) -> dict[str, Any]:
    """Map one Booli API sold record into the local raw-listing JSONL schema."""

    location = record.get("location") if isinstance(record.get("location"), Mapping) else {}
    location = location if isinstance(location, Mapping) else {}

    listing_id = clean_text(_first_value(record, "booliId", "id", "listingId", "residenceId"))
    sold_price = to_int(_first_value(record, "soldPrice", "sold.price"))
    listing_price = to_int(_first_value(record, "listPrice", "listingPrice", "price"))
    living_area = to_float(_first_value(record, "livingArea", "size", "soldSize"))
    sold_date = clean_text(_first_value(record, "soldDate", "sold.date"))

    price_per_sqm = to_int(_first_value(record, "soldSqmPrice", "sqmPrice", "pricePerSqm"))
    if price_per_sqm is None and sold_price is not None and living_area:
        price_per_sqm = int(round(sold_price / living_area))

    url = clean_text(_first_value(record, "url", "soldUrl", "listingUrl"))
    if url and url.startswith("/"):
        url = f"https://www.booli.se{url}"
    if not url and listing_id:
        url = f"https://www.booli.se/bostad/{listing_id}"

    return {
        "listing_id": listing_id,
        "url": url,
        "scraped_at": datetime.now(UTC).isoformat(),
        "listing_price": listing_price,
        "sold_price": sold_price,
        "address": clean_text(
            _first_value(record, "location.streetAddress", "address", "streetAddress")
        ),
        "area": _location_area(location) or clean_text(_first_value(record, "area")),
        "municipality": clean_text(
            _first_value(
                record,
                "location.region.municipalityName",
                "location.municipalityName",
                "municipality",
            )
        ),
        "living_area": living_area,
        "rooms": to_int(_first_value(record, "rooms", "roomCount")),
        "property_type": clean_text(_first_value(record, "objectType", "propertyType", "type")),
        "construction_year": to_int(
            _first_value(record, "constructionYear", "buildYear", "yearBuilt")
        ),
        "monthly_fee": to_int(_first_value(record, "rent", "monthlyFee", "fee")),
        "price_per_sqm": price_per_sqm,
        "floor": to_int(_first_value(record, "floor")),
        "elevator": None,
        "balcony": None,
        "sold_date": sold_date,
        "days_on_market": to_int(_first_value(record, "daysActive", "daysOnMarket")),
        "price_change": sold_price - listing_price
        if sold_price is not None and listing_price is not None
        else None,
        "description": clean_text(_first_value(record, "description")),
        "images": [],
        "source_page": source,
    }


class BooliApiClient:
    def __init__(
        self,
        credentials: BooliApiCredentials,
        *,
        base_url: str = BOOLI_API_BASE_URL,
        opener=urllib.request.urlopen,
    ) -> None:
        self.credentials = credentials
        self.base_url = base_url.rstrip("/")
        self._opener = opener

    def get(self, path: str, params: Mapping[str, Any]) -> dict[str, Any]:
        signed = signed_api_params(self.credentials, params)
        query = urllib.parse.urlencode(signed)
        url = f"{self.base_url}/{path.lstrip('/')}?{query}"
        request = urllib.request.Request(
            url,
            headers={
                "Accept": BOOLI_API_ACCEPT,
                "User-Agent": "estate-value-index (+https://github.com/adamthuvesen/estate-value-index)",
            },
        )
        try:
            with self._opener(request, timeout=45) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Booli API {path} failed with HTTP {exc.code}: {body}") from exc

        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise RuntimeError(f"Booli API {path} returned non-object JSON")
        return payload

    def iter_sold(
        self,
        params: Mapping[str, Any],
        *,
        max_pages: int,
        page_size: int = BOOLI_API_PAGE_SIZE,
    ) -> Iterator[dict[str, Any]]:
        for page in range(max_pages):
            page_params = dict(params)
            page_params["limit"] = page_size
            page_params["offset"] = page * page_size
            payload = self.get("sold", page_params)
            records = payload.get("sold")
            if not isinstance(records, list) or not records:
                return
            for record in records:
                if isinstance(record, dict):
                    yield record
            if len(records) < page_size:
                return


def scrape_booli_api_window(
    *,
    config_file: str | Path,
    output_file: str | Path,
    max_pages: int,
    concurrent_requests: int | None = None,
    delay: float | None = None,
    credentials: BooliApiCredentials | None = None,
    client: BooliApiClient | None = None,
) -> Path:
    """Fetch one sold-date window from Booli's signed API into JSONL."""

    del concurrent_requests, delay

    config = json.loads(Path(config_file).read_text(encoding="utf-8"))
    params = config.get("search_parameters", {})
    if not isinstance(params, dict):
        raise RuntimeError(f"Booli API config search_parameters must be an object: {config_file}")

    resolved_credentials = credentials or BooliApiCredentials.from_env()
    resolved_client = client or BooliApiClient(resolved_credentials)
    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    with path.open("w", encoding="utf-8") as file:
        for record in resolved_client.iter_sold(params, max_pages=max_pages):
            listing = booli_api_record_to_listing(record, source="api.booli.se/sold")
            if not listing.get("listing_id"):
                continue
            file.write(json.dumps(listing, ensure_ascii=False) + "\n")
            written += 1

    if written == 0:
        raise RuntimeError(f"Booli API returned no sold listings for {config_file}")
    return path
