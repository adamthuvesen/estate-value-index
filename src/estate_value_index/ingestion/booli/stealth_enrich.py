"""Fast, parallel detail-page enrichment for stealth-backfilled Booli records.

LOCAL BRANCH ONLY — do not commit / push.

The search-page backfill (stealth_backfill.py) misses three model features that
only live on each listing's own detail page: ``construction_year``,
``monthly_fee`` and ``listing_price``. Driving a browser to 3,500 detail pages
would take hours. Instead:

  1. Solve Cloudflare *once* in a real browser and lift the ``cf_clearance``
     cookie + User-Agent out of the profile.
  2. Fetch detail pages with ``curl_cffi`` impersonating Chrome's TLS/JA3
     fingerprint, so Cloudflare accepts the cookie from a plain HTTP client
     (~0.4s/page, no rendering) — run in a thread pool.
  3. Read the three fields straight off the detail page's ``__APOLLO_STATE__``.

Records are matched to the right sale by ``booliId`` (== our ``listing_id``),
not the URL slug, because a ``/bostad/<slug>`` page is an address that can carry
a different (newer) sale.
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from curl_cffi import requests as cffi

from estate_value_index.ingestion.booli.normalization import to_int
from estate_value_index.ingestion.booli.stealth_backfill import find_apollo_store, parse_next_data

_ENRICH_FIELDS = ("construction_year", "monthly_fee", "listing_price")


class ChallengedError(RuntimeError):
    """Cloudflare served a challenge instead of the page (clearance stale)."""


# --------------------------------------------------------------------------
# Cloudflare clearance
# --------------------------------------------------------------------------
def solve_clearance(profile_dir: str, *, channel: str = "chrome") -> tuple[dict[str, str], str]:
    """Open the solved browser profile and return (booli cookies, user-agent)."""
    from patchright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=profile_dir, headless=False, channel=channel, no_viewport=True
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(
            "https://www.booli.se/sok/slutpriser?areaIds=115347&page=1",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            title = (page.title() or "").lower()
            if "vänta" not in title and "just a moment" not in title:
                break
            page.wait_for_timeout(1000)
        ua = page.evaluate("() => navigator.userAgent")
        cookies = {c["name"]: c["value"] for c in ctx.cookies() if "booli" in c["domain"]}
        ctx.close()
    if "cf_clearance" not in cookies:
        raise ChallengedError("could not obtain cf_clearance from the browser profile")
    return cookies, ua


# --------------------------------------------------------------------------
# Detail-page parsing
# --------------------------------------------------------------------------
def _raw(value: Any) -> int | None:
    if isinstance(value, dict):
        return to_int(value.get("raw"))
    return to_int(value)


def parse_detail_fields(html: str, listing_id: str) -> dict[str, Any] | None:
    """Return the enrichment fields for the SoldProperty whose booliId matches."""
    if "just a moment" in html[:4000].lower() or "vänta</title>" in html[:4000].lower():
        raise ChallengedError("detail response was a Cloudflare challenge")
    data = parse_next_data(html)
    if data is None:
        return None
    store = find_apollo_store(data)
    if not store:
        return None
    # Booli moved these fields onto ResidenceWithSoldProperty; the SoldProperty
    # object is now a near-empty stub. Prefer the residence object, fall back to
    # the old SoldProperty for pages still on the old schema.
    def _find(typename: str) -> dict[str, Any] | None:
        for value in store.values():
            if (
                isinstance(value, dict)
                and value.get("__typename") == typename
                and str(value.get("booliId") or value.get("id")) == str(listing_id)
            ):
                return value
        return None

    match = _find("ResidenceWithSoldProperty") or _find("SoldProperty")
    if match is None:
        return None
    return {
        "construction_year": to_int(match.get("constructionYear")),
        "monthly_fee": _raw(match.get("rent")) or _raw(match.get("operatingCost")),
        "listing_price": _raw(match.get("listPrice")),
    }


def fetch_detail(url: str, cookies: dict[str, str], ua: str, *, timeout: int = 30) -> str:
    resp = cffi.get(
        url,
        headers={"User-Agent": ua, "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8"},
        cookies=cookies,
        impersonate="chrome",
        timeout=timeout,
    )
    if resp.status_code in (403, 429, 503):
        raise ChallengedError(f"HTTP {resp.status_code}")
    return resp.text


# --------------------------------------------------------------------------
# Parallel enrichment
# --------------------------------------------------------------------------
def enrich_records(
    records: list[dict[str, Any]],
    cookies: dict[str, str],
    ua: str,
    *,
    workers: int = 8,
    per_request_delay: float = 0.15,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Fetch + parse detail pages concurrently.

    Returns (enrichment_by_id, challenged_records). Records that raise a
    Cloudflare challenge are returned separately so the caller can refresh the
    clearance and retry them.
    """
    results: dict[str, dict[str, Any]] = {}
    challenged: list[dict[str, Any]] = []
    lock = threading.Lock()

    def work(rec: dict[str, Any]) -> None:
        time.sleep(per_request_delay)
        lid = str(rec["listing_id"])
        try:
            html = fetch_detail(rec["url"], cookies, ua)
            fields = parse_detail_fields(html, lid)
        except ChallengedError:
            with lock:
                challenged.append(rec)
            return
        except Exception:
            return  # transient / parse miss → leave record unenriched
        if fields is not None:
            with lock:
                results[lid] = fields

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(work, rec) for rec in records]
        for _ in as_completed(futures):
            pass
    return results, challenged


def apply_enrichment(rec: dict[str, Any], fields: dict[str, Any]) -> None:
    for key in _ENRICH_FIELDS:
        if fields.get(key) is not None:
            rec[key] = fields[key]
    lp, sp = rec.get("listing_price"), rec.get("sold_price")
    if lp is not None and sp is not None:
        rec["price_change"] = sp - lp


def run_enrichment(
    *,
    input_jsonl: Path,
    output_jsonl: Path,
    profile_dir: str,
    workers: int = 8,
    per_request_delay: float = 0.15,
    limit: int | None = None,
    date_from: str | None = None,
    max_refreshes: int = 3,
) -> dict[str, Any]:
    records = [json.loads(line) for line in input_jsonl.read_text().splitlines() if line.strip()]
    if date_from:
        records = [r for r in records if (r.get("sold_date") or "") >= date_from]
    if limit:
        records = records[:limit]

    cookies, ua = solve_clearance(profile_dir)

    enrichment: dict[str, dict[str, Any]] = {}
    todo = records
    refreshes = 0
    while todo:
        t0 = time.monotonic()
        found, challenged = enrich_records(
            todo, cookies, ua, workers=workers, per_request_delay=per_request_delay
        )
        enrichment.update(found)
        rate = len(todo) / max(time.monotonic() - t0, 0.001)
        print(
            f"batch: {len(todo)} fetched, {len(found)} enriched, "
            f"{len(challenged)} challenged, {rate:.1f} req/s",
            flush=True,
        )
        if not challenged or refreshes >= max_refreshes:
            break
        refreshes += 1
        print(f"refreshing cf_clearance (refresh {refreshes})...", flush=True)
        cookies, ua = solve_clearance(profile_dir)
        todo = challenged

    for rec in records:
        fields = enrichment.get(str(rec["listing_id"]))
        if fields:
            apply_enrichment(rec, fields)

    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with output_jsonl.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    n = len(records)
    fill = {
        k: sum(1 for r in records if r.get(k) not in (None, "", [], {})) for k in _ENRICH_FIELDS
    }
    return {
        "records": n,
        "enriched": len(enrichment),
        "fill": {k: f"{v}/{n} ({100 * v // n if n else 0}%)" for k, v in fill.items()},
        "output": str(output_jsonl),
    }
