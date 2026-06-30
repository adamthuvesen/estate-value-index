"""Tests for Booli area extraction priority and fallbacks."""

from __future__ import annotations

import logging

import pytest

scrapy = pytest.importorskip("scrapy")

from scrapy.http import HtmlResponse, Request

from estate_value_index.ingestion.booli.extractors import BooliExtractionMixins


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


@pytest.mark.unit
def test_extract_area_prefers_structured_property_data() -> None:
    response = _response(
        "<html><body><nav><a>Kungsholmen</a></nav></body></html>",
        meta={"_booli_property_data": {"neighborhoodName": "Vasastan"}},
    )

    assert _Extractor().extract_area(response) == "Vasastan"


@pytest.mark.unit
def test_extract_area_uses_nested_structured_location_when_top_level_is_generic() -> None:
    response = _response(
        "<html><body></body></html>",
        meta={
            "_booli_property_data": {
                "area": "Stockholm",
                "location": {"district": "Södermalm"},
            }
        },
    )

    assert _Extractor().extract_area(response) == "Södermalm"


@pytest.mark.unit
def test_extract_area_falls_back_to_preamble() -> None:
    response = _response(
        """
        <html><body>
          <p class="object-card__preamble">Lägenhet · Vasastan · Stockholm</p>
        </body></html>
        """
    )

    assert _Extractor().extract_area(response) == "Vasastan"


@pytest.mark.unit
def test_extract_area_falls_back_to_breadcrumbs() -> None:
    response = _response(
        """
        <html><body>
          <nav><a>Stockholm</a><a>Kungsholmen</a></nav>
        </body></html>
        """
    )

    assert _Extractor().extract_area(response) == "Kungsholmen"
