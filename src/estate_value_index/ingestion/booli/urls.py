"""URL utilities for Booli ingestion modules."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse


def extract_listing_id(url: str | None) -> str | None:
    """Extract a Booli listing identifier from URL path or query parameters."""

    if not url:
        return None

    parsed = urlparse(url)
    path = parsed.path or ""

    match = re.search(r"/(?:annons|bostad)/(?:[^/]+/)*?(\d+)", path)
    if match:
        return match.group(1)

    for segment in reversed([segment for segment in path.split("/") if segment]):
        if segment.isdigit():
            return segment

    query_params = {key.lower(): values for key, values in parse_qs(parsed.query).items()}
    for key in ("booliid", "listingid", "objectid", "id"):
        values = query_params.get(key)
        if not values:
            continue
        for candidate in values:
            match = re.search(r"(\d+)", candidate or "")
            if match:
                return match.group(1)

    return None


__all__ = ["extract_listing_id"]
