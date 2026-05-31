"""Sold-price regex must require a sale-context prefix AND a Swedish currency suffix.

The previous bare ``r'blev.*?(\\d+\\s*\\d+)'`` and ``r'var.*?(\\d+\\s*\\d+)'``
patterns matched broker bios and area descriptions, injecting false sold
prices into training data.
"""

from __future__ import annotations

import pytest

from estate_value_index.ingestion.booli.spiders.booli import extract_sold_price_from_text


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Slutpriset blev 7 150 000 kr", 7_150_000),
        ("Bostaden såldes för 5 200 000 SEK", 5_200_000),
        ("Slutpris 4 500 000 kr", 4_500_000),
        ("Sista budet var 8 900 000 kr", 8_900_000),
    ],
)
def test_positive_matches(text: str, expected: int):
    assert extract_sold_price_from_text(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Mäklaren blev 1985",  # broker bio: bare "blev" + year, no kr/SEK
        "Området var fantastiskt 2024",  # description: bare "var", no currency
        "Han blev född 1985 och flyttade hit",
        "Boendet var nybyggt",
    ],
)
def test_negative_matches(text: str):
    assert extract_sold_price_from_text(text) is None
