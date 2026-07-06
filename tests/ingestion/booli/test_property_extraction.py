"""Tests for Booli property field extraction."""

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
def test_extract_floor_uses_structured_floor_number() -> None:
    response = _response(
        "<html><body>Våning 2</body></html>",
        meta={"_booli_property_data": {"floorNumber": 4}},
    )

    assert _Extractor().extract_floor(response) == 4


@pytest.mark.unit
def test_extract_floor_uses_structured_info_point_text() -> None:
    response = _response(
        "<html><body></body></html>",
        meta={
            "_booli_property_data": {
                "infoSections": [
                    {
                        "content": {
                            "infoPoints": [
                                {
                                    "key": "floor",
                                    "displayText": {"markdown": "Våning 3"},
                                }
                            ]
                        }
                    }
                ]
            }
        },
    )

    assert _Extractor().extract_floor(response) == 3


@pytest.mark.unit
def test_extract_floor_treats_structured_ground_floor_as_zero() -> None:
    response = _response(
        "<html><body></body></html>",
        meta={
            "_booli_property_data": {
                "infoSections": [
                    {
                        "content": {
                            "infoPoints": [
                                {"key": "våning", "value": "Entréplan"},
                            ]
                        }
                    }
                ]
            }
        },
    )

    assert _Extractor().extract_floor(response) == 0


@pytest.mark.unit
def test_extract_floor_falls_back_to_dom_info_point() -> None:
    response = _response(
        """
        <html><body>
          <div class="info-point"><span>Våning</span><span>2 tr</span></div>
        </body></html>
        """
    )

    assert _Extractor().extract_floor(response) == 2


@pytest.mark.unit
def test_extract_floor_falls_back_to_page_text_ground_floor() -> None:
    response = _response("<html><body>Bostaden ligger på bottenplan</body></html>")

    assert _Extractor().extract_floor(response) == 0


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2,5 rum", 2),  # half-room must not be read as "5"
        ("1,5 rum", 1),
        ("3,5 rum", 3),
        ("2 rum", 2),
        ("3 rum och kök", 3),
        ("4 rum", 4),
        ("56 m² · 2,5 rum · 2 924 kr/mån", 2),
    ],
)
def test_extract_rooms_handles_half_rooms(text: str, expected: int) -> None:
    response = _response(f"<html><body><span>{text}</span></body></html>")

    assert _Extractor().extract_rooms(response) == expected


@pytest.mark.unit
def test_extract_rooms_returns_none_without_match() -> None:
    response = _response("<html><body>Ingen rumsinformation här</body></html>")

    assert _Extractor().extract_rooms(response) is None
