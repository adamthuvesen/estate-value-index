"""Booli field extraction (spider mixin)."""

from __future__ import annotations


class BooliAmenitiesMixin:
    def extract_elevator(self, response):
        """Extract elevator availability (hiss) as True/False/None."""
        try:
            property_data = self._get_property_data(response)
            amenity_keys = (
                self._get_amenity_keys(response, property_data) if property_data else set()
            )

            if property_data:
                elevator_flag = self._coerce_bool(property_data.get("hasElevator"))
                if elevator_flag is not None:
                    return elevator_flag

            if "elevator" in amenity_keys:
                return True
            if "noelevator" in amenity_keys:
                return False

            info_texts = self._extract_info_texts(property_data) if property_data else []
            positive_patterns = [
                r"med\s+hiss",
                r"hiss\s+finns",
                r"tillgång\s+till\s+hiss",
                r"hiss\s+i\s+huset",
                r"hiss\s+i\s+fastigheten",
                r"fastighetens\s+hiss",
                r"gemensam\s+hiss",
                r"hiss\s+i\s+trapphuset",
                r"hiss\s+till\s+l[äa]genheten",
                r"\bhiss\b",
            ]
            negative_patterns = [
                r"utan\s+hiss",
                r"saknar\s+hiss",
                r"ingen\s+hiss",
                r"ingen\s+hiss\s+finns",
                r"hiss\s*saknas",
                r"hiss\s+saknas\s+i",
                r"utan\s+tillgång\s+till\s+hiss",
                r"ej\s+hiss",
                r"ej\s+hiss\s+i\s+fastigheten",
            ]

            for text in info_texts:
                result = self._infer_boolean_from_text(text, positive_patterns, negative_patterns)
                if result is not None:
                    return result

            page_text = self._get_cached_page_text(response)
            result = self._infer_boolean_from_text(page_text, positive_patterns, negative_patterns)
            if result is not None:
                return result
        except Exception as e:
            self.logger.debug(f"Could not extract elevator information: {e}")
        return None

    def extract_balcony(self, response):
        """Extract balcony availability as True/False/None."""
        try:
            property_data = self._get_property_data(response)
            amenity_keys = (
                self._get_amenity_keys(response, property_data) if property_data else set()
            )

            balcony_keys = {"balcony", "frenchbalcony", "rooftopbalcony"}
            if amenity_keys & balcony_keys:
                return True
            if "nobalcony" in amenity_keys:
                return False

            info_texts = self._extract_info_texts(property_data) if property_data else []
            positive_patterns = [
                r"med\s+balkong",
                r"har\s+.*balkong",
                r"egen\s+balkong",
                r"stor\s+balkong",
                r"liten\s+balkong",
                r"balkong\s+ut\s+mot",
                r"solig\s+balkong",
                r"skyddad\s+balkong",
                r"fransk[t]?\s+balkong",
                r"uteplats.*balkong",
                r"balkong.*uteplats",
                r"\bbalkong(er)?\b",
            ]
            negative_patterns = [
                r"utan\s+balkong",
                r"saknar\s+balkong",
                r"ingen\s+balkong",
                r"balkong\s*saknas",
                r"utan\s+balkong\s+eller\s+uteplats",
                r"varken\s+balkong\s+eller",
            ]

            for text in info_texts:
                result = self._infer_boolean_from_text(text, positive_patterns, negative_patterns)
                if result is not None:
                    return result

            page_text = self._get_cached_page_text(response)
            result = self._infer_boolean_from_text(page_text, positive_patterns, negative_patterns)
            if result is not None:
                return result
        except Exception as e:
            self.logger.debug(f"Could not extract balcony information: {e}")
        return None
