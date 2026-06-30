"""Booli field extraction (spider mixin)."""

from __future__ import annotations

import json
import time
import urllib.request
from urllib.parse import urlparse

from estate_value_index.ingestion.booli.parsers import (
    resolve_property_record,
)


def _property_path_from_listing_url(listing_url: str) -> str | None:
    parsed = urlparse(listing_url)
    path = (parsed.path or "").rstrip("/")
    return path or None


def _property_next_data_url(build_id: str, path: str) -> str:
    return f"https://www.booli.se/_next/data/{build_id}{path}.json"


def _request_next_payload(url: str, headers: dict[str, str]) -> str:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", "ignore")


def _json_payload(payload: str | None) -> object | None:
    trimmed = (payload or "").strip()
    if not trimmed or not trimmed.startswith("{"):
        return None
    return json.loads(trimmed)


def _apollo_state_from_property_payload(data: object) -> dict | None:
    if not isinstance(data, dict):
        return None
    page_props = data.get("pageProps")
    if not isinstance(page_props, dict):
        return None
    apollo_state = page_props.get("__APOLLO_STATE__")
    return apollo_state if isinstance(apollo_state, dict) else None


class BooliNextFetchMixin:
    def _fetch_property_data_from_next(self, listing_url, listing_id_str):
        """Fallback: load listing detail via Next.js JSON endpoint when HTML is blocked."""
        try:
            build_id = self._ensure_build_id()
            if not build_id:
                return None

            path = _property_path_from_listing_url(listing_url)
            if not path:
                return None

            next_url = _property_next_data_url(build_id, path)
            data = self._fetch_next_json_with_build_retry(next_url, build_id)
            apollo_state = _apollo_state_from_property_payload(data)
            if apollo_state is None:
                return None

            return resolve_property_record(apollo_state, listing_id_str)
        except Exception:
            return None

    def _json_http_headers(self):
        headers = dict(self._default_http_headers())
        headers["Accept"] = "application/json"
        return headers

    def _refresh_build_id(self):
        self._invalidate_build_id_cache()
        time.sleep(1)
        return self._ensure_build_id(force_refresh=True)

    def _fetch_next_json_with_build_retry(self, next_url: str, build_id: str) -> object | None:
        headers = self._json_http_headers()
        active_build_id = build_id

        for _ in range(2):
            try:
                url = next_url.replace(build_id, active_build_id)
                data = _json_payload(_request_next_payload(url, headers))
                if data is not None:
                    return data
            except Exception:
                pass

            active_build_id = self._refresh_build_id()
            if not active_build_id:
                return None

        return None
