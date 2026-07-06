"""Cloudflare-bypassing Booli sold-price backfill via a real browser.

LOCAL BRANCH ONLY — do not commit / push.

Booli sits behind a Cloudflare managed challenge that a plain HTTP client
cannot pass. This module drives a real (headed) Chrome via patchright, which
solves the challenge once and persists ``cf_clearance`` in its profile, then
reads Booli's own ``__NEXT_DATA__`` Apollo cache straight off the *search*
pages — every sold record is embedded there, so we never touch individual
listing pages (far fewer requests, gentler on the site).

Records are mapped onto the same schema the Scrapy pipeline emits, so the
downstream processing / BigQuery load is unchanged.
"""

from __future__ import annotations

import json
import re
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from estate_value_index.cli.backfill_booli import date_windows, merge_deduped_jsonl
from estate_value_index.ingestion.booli.normalization import to_float, to_int

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)
_DISPLAY_ATTRS_KEY = 'displayAttributes({"queryContext":"SERP_LIST_LISTING"})'
_ROOMS_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*rum")
_SQM_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*m²")
_FLOOR_RE = re.compile(r"vån\s*(\d+)")
_INT_RE = re.compile(r"\d[\d\s ]*")


# --------------------------------------------------------------------------
# __NEXT_DATA__ / Apollo parsing
# --------------------------------------------------------------------------
def parse_next_data(html: str) -> dict[str, Any] | None:
    match = _NEXT_DATA_RE.search(html)
    if not match:
        return None
    return json.loads(match.group(1))


def find_apollo_store(node: Any) -> dict[str, Any] | None:
    """Locate the Apollo normalized cache regardless of the wrapping key name."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key.lower() in ("apollocache", "apollostate", "initialapollostate", "__apollo_state__"):
                if isinstance(value, dict):
                    return value
            found = find_apollo_store(value)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = find_apollo_store(item)
            if found is not None:
                return found
    return None


def _raw_amount(value: Any) -> int | None:
    """Booli wraps money as {'raw': 4750000, 'formatted': '4 750 000 kr'}."""
    if isinstance(value, dict):
        return to_int(value.get("raw"))
    return to_int(value)


def _parse_data_points(sold: dict[str, Any]) -> dict[str, Any]:
    """Pull living_area / rooms / floor / price_per_sqm / monthly_fee out of the
    human-readable data points (e.g. '81 m²', '2,5 rum', 'vån 4', '6 464 kr/mån')."""
    out: dict[str, Any] = {}
    attrs = sold.get(_DISPLAY_ATTRS_KEY) or {}
    for point in attrs.get("dataPoints", []):
        text = ((point.get("value") or {}).get("plainText") or "").strip()
        if not text:
            continue
        low = text.lower()
        if "m²" in low and "kr" not in low:
            m = _SQM_RE.search(text)
            if m:
                out["living_area"] = float(m.group(1).replace(",", "."))
        elif "rum" in low:
            m = _ROOMS_RE.search(text)
            if m:
                # Swedish half-rooms ("2,5 rum") floored to int, matching the schema.
                out["rooms"] = int(float(m.group(1).replace(",", ".")))
        elif "vån" in low:
            m = _FLOOR_RE.search(text)
            if m:
                out["floor"] = int(m.group(1))
        elif "kr/m²" in low or "kr/kvm" in low:
            m = _INT_RE.search(text)
            if m:
                out["price_per_sqm"] = int(m.group(0).replace(" ", "").replace(" ", ""))
        elif "kr/mån" in low:
            m = _INT_RE.search(text)
            if m:
                out["monthly_fee"] = int(m.group(0).replace(" ", "").replace(" ", ""))
    return out


def _amenity_keys(sold: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for ref in sold.get("amenities") or []:
        ref_id = ref.get("__ref", "") if isinstance(ref, dict) else ""
        m = re.search(r'"key":"([^"]+)"', ref_id)
        if m:
            keys.add(m.group(1))
    return keys


def sold_record_to_item(
    sold: dict[str, Any], listing_by_id: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    listing_id = str(sold.get("booliId") or sold.get("id") or "").strip()
    if not listing_id:
        return None

    dp = _parse_data_points(sold)
    amenities = _amenity_keys(sold)

    sold_price = _raw_amount(sold.get("soldPrice"))
    # listPrice is often null on the SoldProperty; fall back to the paired Listing.
    list_price = _raw_amount(sold.get("listPrice"))
    if list_price is None:
        paired = listing_by_id.get(listing_id)
        if paired:
            list_price = _raw_amount(paired.get("listPrice"))

    price_per_sqm = dp.get("price_per_sqm")
    living_area = dp.get("living_area")
    # Booli's price_per_sqm is exactly sold_price / living_area. Use it to catch
    # the ~1% of cards where the "m²" data point parses to a wrong small number
    # (e.g. a secondary/biarea figure): if the parsed area disagrees with the
    # implied area by >15%, trust the implied area.
    if sold_price and price_per_sqm:
        implied = sold_price / price_per_sqm
        if living_area is None or not (0.85 * implied <= living_area <= 1.15 * implied):
            living_area = round(implied)
    elif price_per_sqm is None and sold_price and living_area:
        price_per_sqm = int(round(sold_price / living_area))

    if sold_price is not None and list_price is not None:
        price_change: int | None = sold_price - list_price
    else:
        price_change = _raw_amount(sold.get("soldPriceAbsoluteDiff"))

    url = sold.get("url") or ""
    if url.startswith("/"):
        url = f"https://www.booli.se{url}"

    region = ((sold.get("location") or {}).get("region")) or {}

    return {
        "listing_id": listing_id,
        "url": url,
        "scraped_at": datetime.now(UTC).isoformat(),
        "listing_price": list_price,
        "sold_price": sold_price,
        "price_per_sqm": to_int(price_per_sqm),
        "monthly_fee": to_int(dp.get("monthly_fee")),
        "sold_date": sold.get("soldDate"),
        "days_on_market": to_int(sold.get("daysActive")),
        "price_change": price_change,
        "address": sold.get("streetAddress"),
        "area": sold.get("descriptiveAreaName"),
        "municipality": region.get("municipalityName"),
        "living_area": to_float(living_area),
        "rooms": dp.get("rooms"),
        "property_type": sold.get("objectType"),
        "floor": dp.get("floor"),
        "balcony": True if "balcony" in amenities else None,
        "elevator": True if "elevator" in amenities else None,
        "latitude": sold.get("latitude"),
        "longitude": sold.get("longitude"),
        "source": "stealth.next_data",
        "images": [],
        "description": None,
    }


def extract_sold_items(store: dict[str, Any]) -> list[dict[str, Any]]:
    sold_entries = [
        v for v in store.values() if isinstance(v, dict) and v.get("__typename") == "SoldProperty"
    ]
    listing_by_id = {
        str(v.get("booliId") or v.get("id")): v
        for v in store.values()
        if isinstance(v, dict) and v.get("__typename") == "Listing"
    }
    items = []
    for sold in sold_entries:
        item = sold_record_to_item(sold, listing_by_id)
        if item and item.get("sold_price") is not None:
            items.append(item)
    return items


def sold_items_from_html(html: str) -> list[dict[str, Any]]:
    data = parse_next_data(html)
    if data is None:
        return []
    store = find_apollo_store(data)
    if store is None:
        return []
    return extract_sold_items(store)


# --------------------------------------------------------------------------
# URL building
# --------------------------------------------------------------------------
def build_search_url(config: dict[str, Any], *, page: int, start: date, end: date) -> str:
    base = config.get("crawler_settings", {}).get(
        "base_url", "https://www.booli.se/sok/slutpriser"
    )
    params = dict(config.get("search_parameters", {}))
    params["minSoldDate"] = start.isoformat()
    params["maxSoldDate"] = end.isoformat()
    params["page"] = page
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{base}?{query}"


# --------------------------------------------------------------------------
# Browser fetcher
# --------------------------------------------------------------------------
class StealthFetcher:
    """Persistent headed Chrome that solves Cloudflare once and stays solved."""

    def __init__(self, profile_dir: str, *, channel: str = "chrome", solve_timeout: float = 30.0):
        self.profile_dir = profile_dir
        self.channel = channel
        self.solve_timeout = solve_timeout
        self._pw = None
        self._ctx = None
        self._page = None

    def __enter__(self) -> StealthFetcher:
        from patchright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(
            user_data_dir=self.profile_dir,
            headless=False,
            channel=self.channel,
            no_viewport=True,
        )
        self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        return self

    def __exit__(self, *exc: object) -> None:
        if self._ctx:
            self._ctx.close()
        if self._pw:
            self._pw.stop()

    @staticmethod
    def _challenged(page) -> bool:
        title = (page.title() or "").lower()
        return "vänta" in title or "just a moment" in title

    def fetch_html(self, url: str) -> str:
        page = self._page
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        deadline = time.monotonic() + self.solve_timeout
        while self._challenged(page) and time.monotonic() < deadline:
            page.wait_for_timeout(1000)
        page.wait_for_timeout(800)
        return page.content()


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------
def run_stealth_backfill(
    *,
    config_file: Path,
    output_dir: Path,
    start_date: date,
    end_date: date,
    window_days: int,
    max_pages: int,
    profile_dir: str,
    page_delay: float = 2.0,
) -> dict[str, Any]:
    config = json.loads(config_file.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    windows = list(date_windows(start_date, end_date, window_days))

    window_files: list[Path] = []
    window_counts: dict[str, int] = {}

    with StealthFetcher(profile_dir) as fetcher:
        for window in windows:
            out_file = output_dir / f"listings_{window.label}.jsonl"
            seen: set[str] = set()
            written = 0
            min_sold: str | None = None
            last_page = 0
            with out_file.open("w", encoding="utf-8") as fh:
                for page in range(1, max_pages + 1):
                    last_page = page
                    url = build_search_url(config, page=page, start=window.start, end=window.end)
                    html = fetcher.fetch_html(url)
                    items = sold_items_from_html(html)
                    fresh = [it for it in items if it["listing_id"] not in seen]
                    if not fresh:
                        break  # empty page or all duplicates → past the end
                    for it in fresh:
                        seen.add(it["listing_id"])
                        fh.write(json.dumps(it, ensure_ascii=False) + "\n")
                        written += 1
                        sd = it.get("sold_date")
                        if sd and (min_sold is None or sd < min_sold):
                            min_sold = sd
                    print(f"[{window.label}] page {page}: +{len(fresh)} (total {written})", flush=True)
                    time.sleep(page_delay)
            # Booli returns newest-first; if we exhausted max_pages on a full run
            # we likely didn't reach window.start — flag the silent truncation.
            truncated = last_page >= max_pages and written >= max_pages * 30
            if truncated and min_sold and min_sold > window.start.isoformat():
                print(
                    f"[{window.label}] WARNING truncated at page {max_pages}: "
                    f"only reached back to {min_sold}, window started {window.start}",
                    flush=True,
                )
            window_counts[window.label] = {
                "written": written,
                "min_sold_date": min_sold,
                "pages": last_page,
                "truncated": bool(truncated and min_sold and min_sold > window.start.isoformat()),
            }
            window_files.append(out_file)

    merged = output_dir / "all_dedup.jsonl"
    merge_summary = merge_deduped_jsonl(window_files, merged)
    return {"window_counts": window_counts, "merge": merge_summary}
