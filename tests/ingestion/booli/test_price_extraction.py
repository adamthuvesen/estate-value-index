"""Sold-price regex must require a sale-context prefix AND a Swedish currency suffix.

The previous bare ``r'blev.*?(\\d+\\s*\\d+)'`` and ``r'var.*?(\\d+\\s*\\d+)'``
patterns matched broker bios and area descriptions, injecting false sold
prices into training data.
"""

from __future__ import annotations

import json
import logging

import pytest

scrapy = pytest.importorskip("scrapy")

from scrapy.http import HtmlResponse, Request

from estate_value_index.ingestion.booli.extractors import BooliExtractionMixins
from estate_value_index.ingestion.booli.spiders.booli import extract_sold_price_from_text


class _Extractor(BooliExtractionMixins):
    logger = logging.getLogger(__name__)
    debug_extraction = False
    build_id = None
    build_id_cache_path = "/tmp/booli-build-id-test"


def _response(body: str, *, meta: dict | None = None) -> HtmlResponse:
    request = Request("https://www.booli.se/annons/123", meta=meta or {})
    return HtmlResponse(
        url=request.url,
        request=request,
        body=body.encode("utf-8"),
        encoding="utf-8",
    )


def test_listing_price_prefers_structured_first_price() -> None:
    response = _response(
        "<html><body>Utropspriset var 9 000 000 kr</body></html>",
        meta={"_booli_property_data": {"firstPrice": 6_750_000, "price": 9_000_000}},
    )

    assert _Extractor().extract_listing_price(response) == 6_750_000


def test_listing_price_from_json_ld_product() -> None:
    payload = {"@type": "Product", "offers": {"price": "6 750 000"}}
    response = _response(
        f'<script type="application/ld+json">{json.dumps(payload)}</script>',
    )

    assert _Extractor().extract_listing_price(response) == 6_750_000


def test_listing_price_from_json_ld_product_list() -> None:
    payload = [{"@type": "Product", "offers": {"price": "6 750 000"}}]
    response = _response(
        f'<script type="application/ld+json">{json.dumps(payload)}</script>',
    )

    assert _Extractor().extract_listing_price(response) == 6_750_000


def test_listing_price_from_info_point() -> None:
    response = _response(
        """
        <html><body>
          <div class="info-point"><span>Utropspris</span><span>6 750 000 kr</span></div>
        </body></html>
        """
    )

    assert _Extractor().extract_listing_price(response) == 6_750_000


def test_listing_price_from_page_text() -> None:
    response = _response("<html><body>Utropspriset var 6 750 000 kr</body></html>")

    assert _Extractor().extract_listing_price(response) == 6_750_000


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
