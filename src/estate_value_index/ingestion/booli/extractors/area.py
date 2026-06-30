"""Booli field extraction (spider mixin)."""

from __future__ import annotations

import re

from estate_value_index.ingestion.booli.normalization import (
    is_generic_token,
)

_STRUCTURED_AREA_KEYS = (
    "neighborhoodName",
    "neighbourhoodName",
    "districtName",
    "areaName",
    "area",
    "locationName",
)
_LOCATION_AREA_KEYS = ("neighborhood", "district", "area", "name")
_BREADCRUMB_SELECTORS = (
    "//nav//a/text()",
    "//*[contains(@class, 'breadcrumb')]//a/text()",
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
            for extractor in (
                self._extract_area_from_property_data,
                self._extract_area_from_preamble,
                self._extract_area_from_breadcrumbs,
            ):
                area = extractor(response)
                if area:
                    return area

        except Exception as e:
            self.logger.debug(f"Could not extract area: {e}")
        return None

    def _extract_area_from_property_data(self, response):
        try:
            property_data = self._get_property_data(response)
        except Exception:
            return None

        if not isinstance(property_data, dict) or not property_data:
            return None

        for value in self._property_area_candidates(property_data):
            area = self._normalize_text(value)
            if self._is_specific_area(area):
                return area
        return None

    def _property_area_candidates(self, property_data):
        for key in _STRUCTURED_AREA_KEYS:
            value = property_data.get(key)
            if isinstance(value, str) and value.strip():
                yield value

        location = property_data.get("location")
        if isinstance(location, dict):
            for key in _LOCATION_AREA_KEYS:
                value = location.get(key)
                if isinstance(value, str) and value.strip():
                    yield value

    def _extract_area_from_preamble(self, response):
        for raw in self._preamble_texts(response):
            candidate = self._area_from_preamble_text(raw)
            if self._is_specific_area(candidate):
                return candidate
        return None

    def _preamble_texts(self, response):
        texts = []
        try:
            texts.extend(response.css(".object-card__preamble::text").getall() or [])
        except Exception:
            pass
        try:
            texts.extend(
                response.xpath(
                    "//*[contains(@class,'text-content-secondary') and contains(@class,'text-sm')]/text()"
                ).getall()
                or []
            )
        except Exception:
            pass
        return texts

    def _area_from_preamble_text(self, raw):
        text = self._normalize_text(raw)
        if not text:
            return None

        tokens = [token.strip() for token in text.split("·") if token.strip()]
        cleaned = [token for token in tokens if not self._is_generic_token(token)]
        if not cleaned:
            return None
        return cleaned[0] if len(cleaned) == 1 else cleaned[-1]

    def _extract_area_from_breadcrumbs(self, response):
        for raw in self._breadcrumb_texts(response):
            area = self._normalize_text(raw)
            if self._is_specific_area(area):
                return area
        return None

    def _breadcrumb_texts(self, response):
        candidates = []
        for selector in _BREADCRUMB_SELECTORS:
            try:
                candidates.extend(response.xpath(selector).getall() or [])
            except Exception:
                continue
        return candidates

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
