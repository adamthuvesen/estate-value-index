import pytest

from src.estate_value_index.ingestion.booli.normalization import (
    clean_text,
    ensure_list,
    to_bool,
    to_float,
    to_int,
)
from src.estate_value_index.ingestion.booli.urls import extract_listing_id


def test_clean_text_trims_and_none():
    assert clean_text("  Södermalm ") == "Södermalm"
    assert clean_text("   ") is None
    assert clean_text(None) is None
    assert clean_text(123) == "123"


def test_to_int_handles_strings_and_floats():
    assert to_int("1 200") == 1200
    assert to_int("3500000") == 3500000
    assert to_int(3.7) == 3
    assert to_int("not-a-number") is None


def test_to_float_handles_commas():
    assert to_float("45,5") == pytest.approx(45.5)
    assert to_float(" 78.25 ") == pytest.approx(78.25)
    assert to_float("") is None


def test_to_bool_variants():
    assert to_bool("Ja") is True
    assert to_bool("nej") is False
    assert to_bool(1) is True
    assert to_bool(0) is False
    assert to_bool("maybe") is None


def test_ensure_list_converts_values():
    assert ensure_list(None) == []
    assert ensure_list([1, 2]) == [1, 2]
    assert ensure_list("value") == ["value"]


def test_extract_listing_id_variants():
    assert extract_listing_id("https://www.booli.se/annons/4566") == "4566"
    assert extract_listing_id("https://www.booli.se/bostad/stockholm/sodermalm/654321") == "654321"
    assert extract_listing_id("https://www.booli.se/listing?id=777888") == "777888"
    assert extract_listing_id("https://www.booli.se/path?booliId=999") == "999"
    assert extract_listing_id("https://www.booli.se/no-id") is None
