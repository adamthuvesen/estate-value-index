"""Sold-price text patterns."""

from __future__ import annotations

import re

# Patterns require both a known sale-context prefix and a Swedish currency
# suffix (kr/SEK) on the numeric group.
SOLD_PRICE_PATTERNS = (
    r"(?:Slutpris(?:et)?|sista budet)\s+(?:blev|var|gick för|såldes för)?\s*([\d\s]+?)\s*(?:kr|SEK)\b",
    r"(?:såldes för|gick för)\s+([\d\s]+?)\s*(?:kr|SEK)\b",
    r"([\d\s]+?)\s*(?:kr|SEK)\b[^.]*?(?:såld|Slutpris)",
)


def extract_sold_price_from_text(text: str) -> int | None:
    """Match ``SOLD_PRICE_PATTERNS`` against ``text`` and return an integer price.

    Returns ``None`` when no pattern matches or the captured digits cannot be
    parsed as a positive integer.
    """
    for pattern in SOLD_PRICE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            digits = re.sub(r"\s+", "", match.group(1))
            if digits.isdigit():
                value = int(digits)
                if value > 0:
                    return value
    return None
