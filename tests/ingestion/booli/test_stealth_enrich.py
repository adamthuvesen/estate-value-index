"""Tests for the parallel detail-page enrichment parser.

LOCAL BRANCH ONLY — mirrors stealth_enrich.py, which is not committed.
"""

from __future__ import annotations

import json

import pytest

from estate_value_index.ingestion.booli.stealth_enrich import (
    ChallengedError,
    apply_enrichment,
    parse_detail_fields,
)


def _detail_html(*sold_properties: dict) -> str:
    store = {sp["__ref_key"]: {k: v for k, v in sp.items() if k != "__ref_key"} for sp in sold_properties}
    payload = {"props": {"pageProps": {"__APOLLO_STATE__": store}}}
    return (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(payload)
        + "</script></body></html>"
    )


def _sold(booli_id, **fields):
    base = {
        "__ref_key": f"SoldProperty:{booli_id}",
        "__typename": "SoldProperty",
        "booliId": booli_id,
        "constructionYear": 1932,
        "rent": {"raw": 4636},
        "listPrice": {"raw": 8200000},
    }
    base.update(fields)
    return base


@pytest.mark.unit
def test_parse_detail_fields_matches_by_booli_id():
    # Page carries two SoldProperties; we must pick the one matching our id.
    html = _detail_html(
        _sold("5744382", constructionYear=1932, rent={"raw": 4636}, listPrice={"raw": 8200000}),
        _sold("9999999", constructionYear=2005, rent={"raw": 1000}, listPrice={"raw": 1}),
    )
    fields = parse_detail_fields(html, "5744382")
    assert fields == {"construction_year": 1932, "monthly_fee": 4636, "listing_price": 8200000}


@pytest.mark.unit
def test_parse_detail_fields_returns_none_when_no_match():
    html = _detail_html(_sold("111"))
    assert parse_detail_fields(html, "222") is None


@pytest.mark.unit
def test_parse_detail_fields_falls_back_to_operating_cost():
    html = _detail_html(_sold("111", rent=None, operatingCost={"raw": 5200}))
    assert parse_detail_fields(html, "111")["monthly_fee"] == 5200


@pytest.mark.unit
def test_parse_detail_fields_raises_on_challenge():
    with pytest.raises(ChallengedError):
        parse_detail_fields("<html><head><title>Just a moment...</title></head></html>", "1")


@pytest.mark.unit
def test_apply_enrichment_recomputes_price_change():
    rec = {"listing_id": "1", "sold_price": 8425000}
    apply_enrichment(rec, {"construction_year": 1932, "monthly_fee": 4636, "listing_price": 8200000})
    assert rec["construction_year"] == 1932
    assert rec["monthly_fee"] == 4636
    assert rec["listing_price"] == 8200000
    assert rec["price_change"] == 225000


@pytest.mark.unit
def test_apply_enrichment_skips_missing_fields():
    rec = {"listing_id": "1", "sold_price": 5250000, "monthly_fee": 999}
    apply_enrichment(rec, {"construction_year": 1992, "monthly_fee": None, "listing_price": None})
    assert rec["construction_year"] == 1992
    assert rec["monthly_fee"] == 999  # not overwritten with None
    assert "price_change" not in rec  # no listing_price → not computed
