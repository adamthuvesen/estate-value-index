"""Utility parsing helpers for Booli spiders."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any
from urllib.parse import urljoin

from scrapy.http import Response

from .urls import extract_listing_id


def unique(seq: Iterable[str]) -> list[str]:
    """Return items from ``seq`` preserving order while removing duplicates."""

    seen: set[str] = set()
    result: list[str] = []
    for item in seq:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def resolve_listing_links(response: Response) -> list[str]:
    """Extract absolute listing URLs from a search response."""

    hrefs = response.css("a[href*='/annons/']::attr(href)").getall()
    hrefs += response.css("a[href*='/bostad/']::attr(href)").getall()
    absolute = [response.urljoin(href) if href.startswith("/") else href for href in hrefs]
    return unique(absolute)


def listing_ids_from_links(links: Iterable[str]) -> list[str]:
    """Map listing URLs to their extracted identifiers, dropping empties."""

    ids: list[str] = []
    for link in links:
        listing_id = extract_listing_id(link)
        if listing_id:
            ids.append(listing_id)
    return ids


def extract_next_data_html(response: Response) -> dict[str, Any] | None:
    """Load the embedded ``__NEXT_DATA__`` JSON from an HTML response."""

    script_content = response.xpath("//script[@id='__NEXT_DATA__']/text()").get()
    if not script_content:
        return None
    try:
        return json.loads(script_content)
    except json.JSONDecodeError:
        return None


def apollo_state_from_next(next_payload: dict[str, Any]) -> dict[str, Any]:
    """Return the ``__APOLLO_STATE__`` block from a Next.js payload."""

    props = next_payload.get("props")
    if not isinstance(props, dict):
        return {}
    page_props = props.get("pageProps")
    if not isinstance(page_props, dict):
        return {}
    apollo = page_props.get("__APOLLO_STATE__")
    return apollo if isinstance(apollo, dict) else {}


def listing_links_from_next_payload(next_payload: dict[str, Any]) -> list[str]:
    """Extract listing URLs from a Next.js JSON search payload."""

    apollo_state = next_payload.get("pageProps", {}).get("__APOLLO_STATE__", {})
    if not isinstance(apollo_state, dict):
        return []

    links: list[str] = []
    for key, value in apollo_state.items():
        if not isinstance(key, str) or not key.startswith("Listing:"):
            continue
        if not isinstance(value, dict):
            continue

        url_path = value.get("url") or value.get("listingUrl")
        if not url_path:
            continue
        full_url = (
            url_path if url_path.startswith("http") else urljoin("https://www.booli.se", url_path)
        )
        links.append(full_url)

    return unique(links)


def resolve_property_record(apollo_state: dict[str, Any], listing_id: str) -> dict[str, Any] | None:
    """Find the property record inside an Apollo state blob."""

    if not listing_id:
        return None

    direct_key = f"SoldProperty:{listing_id}"
    candidate = apollo_state.get(direct_key)
    if isinstance(candidate, dict):
        return candidate

    for value in apollo_state.values():
        if not isinstance(value, dict):
            continue
        identifiers = (
            value.get("booliId"),
            value.get("listingId"),
            value.get("residenceId"),
        )
        if listing_id in {str(identifier) for identifier in identifiers if identifier is not None}:
            return value

    return None


__all__ = [
    "resolve_listing_links",
    "listing_ids_from_links",
    "extract_next_data_html",
    "apollo_state_from_next",
    "listing_links_from_next_payload",
    "resolve_property_record",
]
