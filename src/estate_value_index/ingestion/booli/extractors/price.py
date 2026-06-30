"""Booli field extraction (spider mixin)."""

from __future__ import annotations

import json
import re

from estate_value_index.ingestion.booli.extractors.price_patterns import (
    extract_sold_price_from_text,
)

_LISTING_PRICE_KEYS = (
    "firstPrice",
    "listPrice",
    "startingPrice",
    "startPrice",
    "price",
    "askingPrice",
)
_LISTING_PRICE_KEYWORDS = (
    "utropspris",
    "utropspriset",
    "utgångspris",
    "utgångspriset",
    "första utropspris",
    "första utropspriset",
    "utropspriset var",
    "utgångspriset var",
)
_LISTING_PRICE_PATTERNS = (
    r"Utropspriset.*?(\d[\d\s]*)",
    r"utropspris.*?(\d[\d\s]*)",
    r"Pris.*?(\d[\d\s]*)",
    r"(\d[\d\s]*)\s*kr.*?utrop",
    r"första.*?utropspriset.*?(\d[\d\s]*)",
    r"utropspriset.*?var.*?(\d[\d\s]*)",
)


class BooliPriceMixin:
    def extract_listing_price(self, response):
        """Extract listing price (original asking price)"""
        try:
            for extractor in (
                self._listing_price_from_property_data,
                self._listing_price_from_json_ld,
                self._listing_price_from_info_points,
                self._listing_price_from_page_text,
            ):
                price = extractor(response)
                if price is not None:
                    return price

            self.logger.debug("No listing price patterns matched")

        except Exception as e:
            self.logger.debug(f"Could not extract listing price: {e}")
        return None

    def _listing_price_from_property_data(self, response):
        property_data = self._get_property_data(response)
        if not property_data:
            return None

        for key in _LISTING_PRICE_KEYS:
            price = self._extract_price_from_value(property_data.get(key))
            if price is not None:
                self.logger.debug(f"Listing price resolved from property data key '{key}': {price}")
                return price
        return None

    def _listing_price_from_json_ld(self, response):
        json_scripts = response.css('script[type="application/ld+json"]::text').getall()
        self.logger.debug(f"Found {len(json_scripts)} JSON-LD scripts")

        for idx, script in enumerate(json_scripts):
            try:
                data = json.loads(script)
            except json.JSONDecodeError as e:
                self.logger.debug(f"JSON decode error: {e}")
                continue

            self.logger.debug(f"JSON script {idx}: {type(data)} - {str(data)[:200]}...")
            for product in self._json_ld_products(data):
                price = self._price_from_json_ld_product(product)
                if price is not None:
                    self.logger.debug(f"Extracted listing price from JSON-LD: {price}")
                    return price
        return None

    def _json_ld_products(self, data):
        if isinstance(data, dict):
            if data.get("@type") == "Product":
                yield data
            return

        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("@type") == "Product":
                    yield item

    def _price_from_json_ld_product(self, product):
        offer = product.get("offers", {})
        self.logger.debug(f"Found Product with offers: {offer}")
        if not isinstance(offer, dict) or "price" not in offer:
            return None
        return self._extract_price_from_value(offer["price"])

    def _listing_price_from_info_points(self, response):
        info_point_texts = self._get_info_point_texts(response)
        self.logger.debug(f"Found {len(info_point_texts)} info-point entries")

        for idx, normalized_text in enumerate(info_point_texts):
            if not any(keyword in normalized_text for keyword in _LISTING_PRICE_KEYWORDS):
                continue

            self.logger.debug(f"Found price text in info-point {idx}: {normalized_text}")
            price = self._price_from_text(normalized_text)
            if price is not None:
                self.logger.debug(f"Extracted listing price from info-point: {price}")
                return price
        return None

    def _listing_price_from_page_text(self, response):
        page_text = self._get_cached_page_text(response).lower()
        for pattern in _LISTING_PRICE_PATTERNS:
            price = self._price_from_text(page_text, pattern)
            if price is not None:
                self.logger.debug(f"Pattern '{pattern}' matched listing price: {price}")
                return price
        return None

    def _price_from_text(self, text, pattern=r"(\d[\d\s]*)"):
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return None
        return self._sanitize_price(match.group(1).replace(" ", ""))

    def extract_sold_price(self, response):
        """Extract sold price (final sale price)"""
        try:
            property_data = self._get_property_data(response)
            if property_data:
                for key in ("soldPrice", "lastSoldPrice", "finalPrice"):
                    price = self._extract_price_from_value(property_data.get(key))
                    if price is not None:
                        self.logger.debug(
                            f"Sold price resolved from property data key '{key}': {price}"
                        )
                        return price

            # Find all info-point elements and check their text content
            info_point_texts = self._get_info_point_texts(response)
            self.logger.debug(f"Found {len(info_point_texts)} info-point elements")

            # Enhanced patterns for sold price extraction
            sold_price_keywords = [
                "slutpris",
                "slutpriset",
                "sista budet",
                "sista bud",
                "blev",
                "var",
                "slutpriset blev",
                "slutpriset var",
                "sista budet blev",
                "sista budet var",
            ]

            for idx, text_content in enumerate(info_point_texts):
                if any(keyword in text_content for keyword in sold_price_keywords):
                    self.logger.debug(f"Found relevant text in info-point {idx}: {text_content}")
                    price_match = re.search(r"(\d[\d\s]*)", text_content)
                    if price_match:
                        price_str = price_match.group(1).replace(" ", "")
                        price = self._sanitize_price(price_str)
                        if price is not None:
                            self.logger.debug(f"Extracted sold price: {price}")
                            return price

            # Fallback: look in all page text
            page_text = self._get_cached_page_text(response)
            self.logger.debug(f"Full page text length: {len(page_text)}")

            price = extract_sold_price_from_text(page_text)
            if price is not None:
                self.logger.debug(f"Sold-price pattern matched: {price}")
                return price

            self.logger.debug("No sold price patterns matched")

        except Exception as e:
            self.logger.debug(f"Could not extract sold price: {e}")
        return None

    def extract_sold_date(self, response):
        """Extract sold date"""
        try:
            # Find all info-point elements and check their text content
            for text_content in self._get_info_point_texts(response):
                if (
                    "såld" in text_content
                    or "borttagen" in text_content
                    or "försäljning" in text_content
                ):
                    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", text_content)
                    if date_match:
                        return date_match.group(1)

            # Fallback to page text
            page_text = self._get_cached_page_text(response)

            # Updated patterns based on actual HTML structure
            date_patterns = [
                r"Såld.*?(\d{4}-\d{2}-\d{2})",  # "Såld eller borttagen 2025-09-24"
                r"såld.*?(\d{4}-\d{2}-\d{2})",  # "såld 2025-09-24"
                r"borttagen.*?(\d{4}-\d{2}-\d{2})",  # "borttagen 2025-09-24"
                r"försäljning.*?(\d{4}-\d{2}-\d{2})",  # "försäljning 2025-09-24"
                r"(\d{4}-\d{2}-\d{2}).*?slutpris",  # "2025-09-24 slutpris"
            ]

            for pattern in date_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    return match.group(1)
        except Exception as e:
            self.logger.debug(f"Could not extract sold date: {e}")
        return None

    def extract_days_on_market(self, response):
        """Extract days on market"""
        try:
            # Find all info-point elements and check their text content
            for text_content in self._get_info_point_texts(response):
                if "till salu" in text_content or "dagar" in text_content:
                    days_match = re.search(r"(\d+)", text_content)
                    if days_match:
                        return int(days_match.group(1))

            # Fallback to page text
            page_text = self._get_cached_page_text(response)

            # Updated patterns based on actual HTML structure
            days_patterns = [
                r"Bostaden.*?till salu.*?(\d+)",  # "Bostaden var till salu i 19 dagar"
                r"till salu.*?(\d+).*dag",  # "till salu i 19 dagar"
                r"(\d+)\s*dagar",  # "19 dagar"
                r"var till salu.*?(\d+)",  # "var till salu i 19"
                r"(\d+)\s*dagar",  # "19 dagar" (alternative spelling)
            ]

            for pattern in days_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    return int(match.group(1))
        except Exception as e:
            self.logger.debug(f"Could not extract days on market: {e}")
        return None

    def extract_price_change(self, response):
        """Extract price change amount"""
        try:
            page_text = self._get_cached_page_text(response)

            # Look for price change patterns
            change_patterns = [
                r"prisutvecklingen.*?([+-]?\d+\s*\d+)",
                r"priset.*?([+-]?\d+\s*\d+).*kr",
                r"förändring.*?([+-]?\d+\s*\d+)",
            ]

            for pattern in change_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    change_str = match.group(1).replace(" ", "")
                    return int(change_str)
        except Exception as e:
            self.logger.debug(f"Could not extract price change: {e}")
        return None

    def extract_price_per_sqm(self, response):
        """Extract price per square meter"""
        try:
            property_data = self._get_property_data(response)
            if property_data:
                for key in ("soldSqmPrice", "pricePerSqm", "sqmPrice"):
                    value = self._extract_int_from_value(property_data.get(key))
                    if value is not None:
                        return value

            for normalized in self._get_info_point_texts(response):
                if "kvadratmeter" in normalized or "kr/m" in normalized:
                    match = re.search(r"(\d[\d\s]*)", normalized)
                    if match:
                        return int(match.group(1).replace(" ", ""))

            page_text = self._get_cached_page_text(response)
            match = re.search(r"kvadratmeter.*?(\d[\d\s]*)", page_text, re.IGNORECASE)
            if match:
                return int(match.group(1).replace(" ", ""))
        except Exception as e:
            self.logger.debug(f"Could not extract price per sqm: {e}")
        return None
