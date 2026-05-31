"""Booli field extraction (spider mixin)."""

from __future__ import annotations

import re


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
            floor_patterns = [
                r"våning\s*(\d+)",
                r"(\d+)\s*tr",
                r"(\d+):\s*an",
                r"plan\s*(\d+)",
                r"etage\s*(\d+)",
                r"(\d+)\s*våningar?\s+upp",
            ]
            ground_regex = r"entr[ée]plan|bottenplan|markplan|gatuplan"

            if property_data:
                floor_value = property_data.get("floor") or property_data.get("floorNumber")
                floor_number = self._extract_int_from_value(floor_value)
                if floor_number is not None:
                    return floor_number

                for point in self._iter_info_points(property_data):
                    key = (point.get("key") or "").lower()
                    if key not in ("floor", "våning"):
                        continue

                    text_candidates = []
                    label = point.get("label")
                    if label:
                        text_candidates.append(label)
                    value = point.get("value")
                    if isinstance(value, str):
                        text_candidates.append(value)
                    display = point.get("displayText")
                    if isinstance(display, dict):
                        markdown = display.get("markdown")
                        if markdown:
                            text_candidates.append(markdown)

                    for text in text_candidates:
                        normalized = self._normalize_text(text)
                        if not normalized:
                            continue
                        if re.search(ground_regex, normalized, re.IGNORECASE):
                            return 0
                        for pattern in floor_patterns:
                            match = re.search(pattern, normalized, re.IGNORECASE)
                            if match:
                                return int(match.group(1))

            info_text = " ".join(self._get_info_point_texts(response))
            if info_text:
                if re.search(ground_regex, info_text, re.IGNORECASE):
                    return 0
                for pattern in floor_patterns:
                    match = re.search(pattern, info_text, re.IGNORECASE)
                    if match:
                        return int(match.group(1))

            page_text = self._get_cached_page_text(response)
            if re.search(ground_regex, page_text, re.IGNORECASE):
                return 0
            for pattern in floor_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    return int(match.group(1))
        except Exception as e:
            self.logger.debug(f"Could not extract floor information: {e}")
        return None
