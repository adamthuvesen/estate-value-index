"""Booli field extraction (spider mixin)."""

from __future__ import annotations

import re

_FLOOR_PATTERNS = (
    r"våning\s*(\d+)",
    r"(\d+)\s*tr",
    r"(\d+):\s*an",
    r"plan\s*(\d+)",
    r"etage\s*(\d+)",
    r"(\d+)\s*våningar?\s+upp",
)
_GROUND_FLOOR_PATTERN = r"entr[ée]plan|bottenplan|markplan|gatuplan"
_FLOOR_INFO_KEYS = ("floor", "våning")


class BooliPropertyMixin:
    def extract_living_area(self, response):
        try:
            page_text = self._get_cached_page_text(response)
            area_match = re.search(r"(\d+(?:,\d+)?)\s*m²", page_text)
            if area_match:
                return float(area_match.group(1).replace(",", "."))
        except Exception as e:
            self.logger.debug(f"Could not extract living area: {e}")
        return None

    def extract_rooms(self, response):
        try:
            page_text = self._get_cached_page_text(response)
            rooms_match = re.search(r"(\d+)\s+rum", page_text)
            if rooms_match:
                return int(rooms_match.group(1))
        except Exception as e:
            self.logger.debug(f"Could not extract rooms: {e}")
        return None

    def extract_property_type(self, response):
        try:
            title = response.css("title::text").get()
            if title:
                if "Lägenhet" in title:
                    return "Lägenhet"
                elif "Villa" in title:
                    return "Villa"
                elif "Radhus" in title:
                    return "Radhus"
        except Exception as e:
            self.logger.debug(f"Could not extract property type: {e}")
        return None

    def extract_construction_year(self, response):
        try:
            page_text = self._get_cached_page_text(response)
            year_match = re.search(r"byggår\s+(\d{4})", page_text, re.IGNORECASE)
            if year_match:
                return int(year_match.group(1))
        except Exception as e:
            self.logger.debug(f"Could not extract construction year: {e}")
        return None

    def extract_monthly_fee(self, response):
        try:
            property_data = self._get_property_data(response)
            if property_data:
                fee = self._extract_int_from_value(property_data.get("rent"))
                if fee is not None:
                    return fee

            for normalized in self._get_info_point_texts(response):
                if "avgift" in normalized:
                    match = re.search(r"(\d[\d\s]*)", normalized)
                    if match:
                        return int(match.group(1).replace(" ", ""))

            page_text = self._get_cached_page_text(response)
            match = re.search(r"avgift.*?(\d[\d\s]*)", page_text, re.IGNORECASE)
            if match:
                return int(match.group(1).replace(" ", ""))
        except Exception as e:
            self.logger.debug(f"Could not extract monthly fee: {e}")
        return None

    def extract_floor(self, response):
        """Extract the floor number (våning)."""
        try:
            property_data = self._get_property_data(response)

            for extractor in (
                self._floor_from_structured_value,
                self._floor_from_structured_info_points,
            ):
                floor = extractor(property_data)
                if floor is not None:
                    return floor

            info_text = " ".join(self._get_info_point_texts(response))
            floor = self._floor_from_text(info_text)
            if floor is not None:
                return floor

            return self._floor_from_text(self._get_cached_page_text(response))
        except Exception as e:
            self.logger.debug(f"Could not extract floor information: {e}")
        return None

    def _floor_from_structured_value(self, property_data):
        if not property_data:
            return None

        floor_value = property_data.get("floor") or property_data.get("floorNumber")
        return self._extract_int_from_value(floor_value)

    def _floor_from_structured_info_points(self, property_data):
        if not property_data:
            return None

        for point in self._iter_info_points(property_data):
            key = (point.get("key") or "").lower()
            if key not in _FLOOR_INFO_KEYS:
                continue

            for text in self._info_point_text_candidates(point):
                floor = self._floor_from_text(text)
                if floor is not None:
                    return floor
        return None

    def _info_point_text_candidates(self, point):
        label = point.get("label")
        if label:
            yield label

        value = point.get("value")
        if isinstance(value, str):
            yield value

        display = point.get("displayText")
        if isinstance(display, dict):
            markdown = display.get("markdown")
            if markdown:
                yield markdown

    def _floor_from_text(self, text):
        normalized = self._normalize_text(text)
        if not normalized:
            return None

        if re.search(_GROUND_FLOOR_PATTERN, normalized, re.IGNORECASE):
            return 0

        for pattern in _FLOOR_PATTERNS:
            match = re.search(pattern, normalized, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return None
