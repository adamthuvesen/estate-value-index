"""Booli field extraction (spider mixin)."""

from __future__ import annotations

import re

from estate_value_index.ingestion.booli.normalization import (
    is_generic_token,
)


class BooliAreaMixin:
    def extract_address(self, response):
        """Extract property address"""
        try:
            # Try h1 first (often contains address)
            address_text = response.css("h1::text").get()
            if address_text:
                # Clean up the address (remove "Lägenhet" etc.)
                address_text = re.sub(
                    r"^(Lägenhet|Villa|Radhus|Bostadsrätt)\s+(till salu\s+)?på\s+", "", address_text
                )
                return address_text.strip()
        except Exception as e:
            self.logger.debug(f"Could not extract address: {e}")
        return None

    def extract_area(self, response):
        """Extract area/neighborhood robustly.

        Priority:
          1) Structured property data (Next.js __APOLLO_STATE__)
          2) Preamble line under heading (e.g., "Lägenhet · Vasastan · Stockholm")
          3) Breadcrumbs
        """
        try:
            # 1) Structured data
            try:
                property_data = self._get_property_data(response)
            except Exception:
                property_data = None

            if isinstance(property_data, dict) and property_data:
                # Try common keys that often contain neighborhood/area names
                for key in (
                    "neighborhoodName",
                    "neighbourhoodName",
                    "districtName",
                    "areaName",
                    "area",
                    "locationName",
                ):
                    value = property_data.get(key)
                    if isinstance(value, str) and value.strip():
                        area = self._normalize_text(value)
                        if self._is_specific_area(area):
                            return area

                # Nested location object
                location = property_data.get("location")
                if isinstance(location, dict):
                    for key in ("neighborhood", "district", "area", "name"):
                        value = location.get(key)
                        if isinstance(value, str) and value.strip():
                            area = self._normalize_text(value)
                            if self._is_specific_area(area):
                                return area

            # 2) Preamble line beneath the title
            # Examples:
            #   "Lägenhet · Kungsholmen"
            #   "Lägenhet · Vasastan · Stockholm"
            preamble_texts = []
            try:
                preamble_texts += response.css(".object-card__preamble::text").getall() or []
            except Exception:
                pass
            try:
                preamble_texts += (
                    response.xpath(
                        "//*[contains(@class,'text-content-secondary') and contains(@class,'text-sm')]/text()"
                    ).getall()
                    or []
                )
            except Exception:
                pass

            for raw in preamble_texts:
                text = self._normalize_text(raw)
                if not text:
                    continue
                tokens = [t.strip() for t in text.split("·") if t.strip()]
                # Drop generic tokens like property type / municipality
                cleaned = [t for t in tokens if not self._is_generic_token(t)]
                # Prefer the most specific token (usually the middle if 3, else last)
                if cleaned:
                    candidate = cleaned[0] if len(cleaned) == 1 else cleaned[-1]
                    if self._is_specific_area(candidate):
                        return candidate

            # 3) Breadcrumbs as a last resort
            breadcrumb_candidates = []
            for selector in (
                "//nav//a/text()",
                "//*[contains(@class, 'breadcrumb')]//a/text()",
            ):
                try:
                    breadcrumb_candidates += response.xpath(selector).getall() or []
                except Exception:
                    continue

            for raw in breadcrumb_candidates:
                text = self._normalize_text(raw)
                if not text:
                    continue
                if self._is_specific_area(text):
                    return text

        except Exception as e:
            self.logger.debug(f"Could not extract area: {e}")
        return None

    def _is_generic_token(self, token):
        """Delegates to the shared ``is_generic_token`` helper."""
        return is_generic_token(token)

    def _is_specific_area(self, token):
        """Heuristic: an area should not be generic region/municipality or property type."""
        if not token:
            return False
        return not is_generic_token(token)

    def extract_municipality(self, response):
        """Extract municipality"""
        try:
            # Usually Stockholm for area ID 1
            return "Stockholm"
        except Exception as e:
            self.logger.debug(f"Could not extract municipality: {e}")
        return None
