"""Booli field extraction (spider mixin)."""

from __future__ import annotations

import re

from estate_value_index.ingestion.booli.normalization import (
    normalize_text,
    to_bool,
)


class BooliExtractionHelpersMixin:
    def _match_patterns(self, text, patterns):
        if not text:
            return False
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def _infer_boolean_from_text(self, text, positive_patterns, negative_patterns):
        if not text:
            return None
        if self._match_patterns(text, negative_patterns):
            return False
        if self._match_patterns(text, positive_patterns):
            return True
        return None

    def _coerce_bool(self, value):
        """Delegates to the shared ``to_bool`` so spider/processing/ML cannot drift."""
        return to_bool(value)

    def _normalize_text(self, value):
        """Delegates to the shared Booli text normalizer."""
        return normalize_text(value)

    def _extract_price_from_value(self, raw_value):
        """Normalise different price representations into an integer"""
        if raw_value is None:
            return None

        if isinstance(raw_value, dict):
            # Prefer explicit numeric payloads if present
            if isinstance(raw_value.get("raw"), (int, float)):
                return self._sanitize_price(raw_value["raw"])
            for key in ("value", "formatted", "price"):
                val = raw_value.get(key)
                if val is None:
                    continue
                digits = re.sub(r"[^0-9]", "", str(val))
                if digits:
                    return self._sanitize_price(int(digits))

        if isinstance(raw_value, (int, float)):
            return self._sanitize_price(raw_value)

        if isinstance(raw_value, str):
            digits = re.sub(r"[^0-9]", "", raw_value)
            if digits:
                return self._sanitize_price(int(digits))

        return None

    def _sanitize_price(self, price):
        """Ensure price meets minimum threshold, otherwise return None"""
        if price is None:
            return None

        try:
            numeric_price = int(price)
        except (TypeError, ValueError):
            return None

        if numeric_price < 1_000_000:
            return None

        return numeric_price

    def _extract_int_from_value(self, raw_value):
        """Extract integer value from heterogenous payloads"""
        if raw_value is None:
            return None

        if isinstance(raw_value, dict):
            for key in ("raw", "value", "formatted", "amount", "number"):
                if key in raw_value:
                    extracted = self._extract_int_from_value(raw_value[key])
                    if extracted is not None:
                        return extracted
            return None

        if isinstance(raw_value, (int, float)):
            return int(raw_value)

        if isinstance(raw_value, str):
            digits = re.sub(r"[^0-9]", "", raw_value)
            if digits:
                return int(digits)

        return None
