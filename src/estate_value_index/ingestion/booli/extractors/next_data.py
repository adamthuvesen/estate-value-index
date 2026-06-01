"""Booli field extraction (spider mixin)."""

from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlencode

from estate_value_index.ingestion.booli.parsers import (
    apollo_state_from_next,
    extract_next_data_html,
    listing_links_from_next_payload,
    resolve_property_record,
)
from estate_value_index.ingestion.booli.urls import extract_listing_id


class BooliNextDataMixin:
    def _get_next_data(self, response):
        """Parse and cache the Next.js data payload for the current response"""
        if "_booli_next_data" in response.meta:
            return response.meta["_booli_next_data"]

        next_data = extract_next_data_html(response)
        if next_data is None:
            self.logger.debug("No __NEXT_DATA__ script found on page; falling back to DOM scraping")
        elif isinstance(next_data, dict):
            build_id = next_data.get("buildId")
            if build_id:
                self.build_id = build_id
                self._store_cached_build_id(build_id)

        response.meta["_booli_next_data"] = next_data
        return next_data

    def _get_apollo_state(self, response):
        """Return the parsed Apollo state dictionary for the current page."""
        if "_booli_apollo_state" in response.meta:
            return response.meta["_booli_apollo_state"]

        apollo_state: dict[str, object] = {}
        next_data = self._get_next_data(response)

        if next_data is None:
            self.logger.debug("No Next.js data available for property extraction")
        elif isinstance(next_data, dict):
            apollo_state = apollo_state_from_next(next_data)
            if not apollo_state:
                self.logger.debug("__APOLLO_STATE__ missing or empty in Next.js data")

        response.meta["_booli_apollo_state"] = apollo_state
        return apollo_state

    def _get_property_data(self, response):
        """Extract the structured property data block if available"""
        if "_booli_property_data" in response.meta:
            return response.meta["_booli_property_data"]

        listing_id = response.meta.get("listing_id") or extract_listing_id(response.url)
        listing_id_str = str(listing_id) if listing_id is not None else ""
        property_data = None

        if listing_id_str:
            apollo_state = self._get_apollo_state(response)
            if apollo_state:
                property_data = resolve_property_record(apollo_state, listing_id_str)
                if property_data is None:
                    sample_keys = list(apollo_state)[:5]
                    self.logger.debug(
                        f"Apollo state did not contain record for {listing_id_str}. Sample keys: {sample_keys}"
                    )
                else:
                    self.logger.debug(f"Resolved property data for id {listing_id_str}")

        response.meta["_booli_property_data"] = property_data
        return property_data

    def _get_amenity_keys(self, response, property_data):
        """Return a set of amenity keys resolved from the Apollo state."""
        amenity_keys = set()
        if not property_data:
            return amenity_keys

        amenities = property_data.get("amenities")
        if not isinstance(amenities, list):
            return amenity_keys

        apollo_state = self._get_apollo_state(response)

        for amenity in amenities:
            if isinstance(amenity, dict):
                key = amenity.get("key")
                if key:
                    amenity_keys.add(str(key).lower())
                    continue

                ref = amenity.get("__ref")
                if ref and isinstance(apollo_state, dict):
                    resolved = apollo_state.get(ref)
                    if isinstance(resolved, dict):
                        resolved_key = resolved.get("key")
                        if resolved_key:
                            amenity_keys.add(str(resolved_key).lower())

        return amenity_keys

    def _iter_info_points(self, property_data):
        """Yield info point dictionaries from structured property data."""
        if not property_data:
            return

        sections = property_data.get("infoSections")
        if not isinstance(sections, list):
            return

        for section in sections:
            if not isinstance(section, dict):
                continue
            content = section.get("content")
            if not isinstance(content, dict):
                continue
            points = content.get("infoPoints")
            if not isinstance(points, list):
                continue
            for point in points:
                if isinstance(point, dict):
                    yield point

    def _extract_info_texts(self, property_data):
        """Collect textual snippets from info points for keyword analysis."""
        texts = []
        for point in self._iter_info_points(property_data):
            label = point.get("label")
            if label:
                texts.append(self._normalize_text(label))

            value = point.get("value")
            if isinstance(value, str):
                texts.append(self._normalize_text(value))

            display = point.get("displayText")
            if isinstance(display, dict):
                markdown = display.get("markdown")
                if markdown:
                    texts.append(self._normalize_text(markdown))

        return [text for text in texts if text]

    def _get_cached_page_text(self, response):
        """Return normalized page text with per-response caching."""
        if "_booli_page_text" in response.meta:
            return response.meta["_booli_page_text"]

        text_nodes = response.css("body *::text").getall()
        normalized = self._normalize_text(" ".join(text_nodes)) if text_nodes else ""
        response.meta["_booli_page_text"] = normalized
        return normalized

    def _get_info_point_texts(self, response):
        """Return normalized text content from .info-point elements."""
        cache_key = "_booli_info_points"
        if cache_key in response.meta:
            return response.meta[cache_key]

        texts = []
        for element in response.css(".info-point"):
            raw_text = " ".join(element.css("*::text").getall())
            normalized = self._normalize_text(raw_text)
            if normalized:
                texts.append(normalized.lower())

        # Debug logging for troubleshooting
        if self.logger.isEnabledFor(10) or self.debug_extraction:  # DEBUG level
            self.logger.debug(f"Extracted {len(texts)} info-point texts: {texts[:3]}...")

        response.meta[cache_key] = texts
        return texts

    def _default_http_headers(self):
        """Headers used for fallback HTTP requests."""
        return {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:128.0) Gecko/20100101 Firefox/128.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
            "DNT": "1",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
        }

    def _load_cached_build_id(self):
        """Load a previously stored Next.js build ID, if available."""
        try:
            with open(self.build_id_cache_path, encoding="utf-8") as fh:
                cached = fh.read().strip()
        except FileNotFoundError:
            return None
        except OSError as e:
            self.logger.debug(f"Failed to read cached build ID: {e}")
            return None
        if cached:
            self.logger.info(f"Using cached Next.js build ID: {cached}")
            self.build_id = cached
            return cached
        return None

    def _store_cached_build_id(self, build_id):
        """Persist the build ID for reuse across runs."""
        try:
            cache_path = Path(self.build_id_cache_path)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(build_id, encoding="utf-8")
        except OSError as e:
            self.logger.debug(f"Failed to persist build ID cache: {e}")

    def _invalidate_build_id_cache(self):
        self.build_id = None
        try:
            os.remove(self.build_id_cache_path)
        except FileNotFoundError:
            pass
        except OSError as e:
            self.logger.debug(f"Failed to remove cached build ID: {e}")

    def _ensure_build_id(self, force_refresh=False):
        """Ensure we have the current Next.js build ID for API fallback."""
        if not force_refresh and self.build_id:
            return self.build_id

        if not force_refresh:
            cached = self._load_cached_build_id()
            if cached:
                return cached

        fallback_url = self._build_search_url(page=1)
        headers = self._default_http_headers()

        try:
            req = urllib.request.Request(fallback_url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                html = resp.read().decode("utf-8", "ignore")
            start = html.find('<script id="__NEXT_DATA__"')
            if start != -1:
                start = html.find(">", start) + 1
                end = html.find("</script>", start)
                if end != -1:
                    data = json.loads(html[start:end])
                    build_id = data.get("buildId")
                    if build_id:
                        self.build_id = build_id
                        self._store_cached_build_id(build_id)
                        self.logger.info(f"Resolved Next.js build ID for API fallback: {build_id}")
                        return build_id
        except Exception as e:
            self.logger.warning(f"Failed to resolve build ID via fallback request: {e}")

        return None

    def _fetch_listings_from_next_data(self, page):
        """Fallback: retrieve listing URLs from Next.js data endpoint."""
        build_id = self._ensure_build_id()
        if not build_id:
            self.logger.warning("Missing Next.js build ID; cannot use API fallback")
            return []

        params = dict(self.search_params)
        params["page"] = page
        query_string = urlencode(params)
        next_url = f"https://www.booli.se/_next/data/{build_id}/sok/slutpriser.json?{query_string}"

        headers = dict(self._default_http_headers())
        headers["Accept"] = "application/json"

        def _request_payload(active_build_id):
            url = next_url.replace(build_id, active_build_id)
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                payload = resp.read().decode("utf-8", "ignore")
            return payload

        attempts = 0
        data = None
        active_build_id = build_id

        while attempts < 2 and data is None:
            attempts += 1
            try:
                payload = _request_payload(active_build_id)
                trimmed = payload.strip()
                if not trimmed or not trimmed.startswith("{"):
                    self.logger.warning(
                        f"Next.js fallback returned non-JSON payload on page {page} (attempt {attempts}); "
                        "refreshing build ID"
                    )
                    self._invalidate_build_id_cache()
                    time.sleep(1)
                    active_build_id = self._ensure_build_id(force_refresh=True)
                    if not active_build_id:
                        return []
                    continue

                data = json.loads(trimmed)
            except Exception as e:
                self.logger.warning(
                    f"Failed to fetch Next.js search data for page {page} (attempt {attempts}): {e}"
                )
                self._invalidate_build_id_cache()
                time.sleep(1)
                active_build_id = self._ensure_build_id(force_refresh=True)
                if not active_build_id:
                    return []

        if data is None:
            return []

        listing_links = listing_links_from_next_payload(data)
        if not listing_links:
            self.logger.warning(f"Next.js fallback returned no listings for page {page}")
            return []

        self.logger.info(
            f"Recovered {len(listing_links)} listings from Next.js fallback for page {page}"
        )

        return listing_links
