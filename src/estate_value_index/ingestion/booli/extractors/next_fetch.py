"""Booli field extraction (spider mixin)."""

from __future__ import annotations

import json
import time
import urllib.request

from estate_value_index.ingestion.booli.parsers import (
    resolve_property_record,
)


class BooliNextFetchMixin:
    def _fetch_property_data_from_next(self, listing_url, listing_id_str):
        """Fallback: load listing detail via Next.js JSON endpoint when HTML is blocked."""
        try:
            build_id = self._ensure_build_id()
            if not build_id:
                return None

            from urllib.parse import urlparse

            parsed = urlparse(listing_url)
            path = (parsed.path or "").rstrip("/")
            if not path:
                return None

            next_url = f"https://www.booli.se/_next/data/{build_id}{path}.json"

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
                    trimmed = (payload or "").strip()
                    if not trimmed or not trimmed.startswith("{"):
                        self._invalidate_build_id_cache()
                        time.sleep(1)
                        active_build_id = self._ensure_build_id(force_refresh=True)
                        if not active_build_id:
                            return None
                        continue
                    data = json.loads(trimmed)
                except Exception:
                    self._invalidate_build_id_cache()
                    time.sleep(1)
                    active_build_id = self._ensure_build_id(force_refresh=True)
                    if not active_build_id:
                        return None

            if not isinstance(data, dict):
                return None
            page_props = data.get("pageProps")
            if not isinstance(page_props, dict):
                return None
            apollo_state = page_props.get("__APOLLO_STATE__")
            if not isinstance(apollo_state, dict):
                return None

            return resolve_property_record(apollo_state, listing_id_str)
        except Exception:
            return None
