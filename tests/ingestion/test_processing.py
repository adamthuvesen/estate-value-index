"""Tests for `merge_listings` conflict resolution and retention rules."""

from __future__ import annotations

from estate_value_index.ingestion.processing import merge_listings


def _listing(listing_id: str, **fields) -> dict:
    base = {"listing_id": listing_id, "address": "Some Street 1"}
    base.update(fields)
    return base


def test_existing_with_null_prices_is_kept():
    existing = [_listing("A", listing_price=None, sold_price=None)]
    merged, stats = merge_listings([], existing)

    assert {row["listing_id"] for row in merged} == {"A"}
    assert stats["final_count"] == 1


def test_new_with_sold_price_wins_over_existing_without():
    existing = [
        _listing("A", listing_price=4_000_000, sold_price=None, scraped_at="2026-01-01T00:00:00")
    ]
    new = [
        _listing(
            "A", listing_price=4_000_000, sold_price=4_500_000, scraped_at="2026-01-02T00:00:00"
        )
    ]

    merged, stats = merge_listings(new, existing)
    assert len(merged) == 1
    assert merged[0]["sold_price"] == 4_500_000
    assert stats["duplicates"] == 1
    assert stats["duplicates_replaced"] == 1


def test_existing_with_sold_price_wins_when_new_missing_it():
    existing = [
        _listing(
            "A", listing_price=4_000_000, sold_price=4_500_000, scraped_at="2026-01-01T00:00:00"
        )
    ]
    # New scrape has no sold price (e.g. listing relisted) — must NOT clobber the prior sold price
    new = [
        _listing("A", listing_price=4_100_000, sold_price=None, scraped_at="2026-02-01T00:00:00")
    ]

    merged, stats = merge_listings(new, existing)
    assert len(merged) == 1
    assert merged[0]["sold_price"] == 4_500_000
    assert stats["duplicates"] == 1
    assert stats["duplicates_replaced"] == 0


def test_both_have_sold_price_newer_scraped_at_wins():
    existing = [_listing("A", sold_price=4_500_000, scraped_at="2026-01-01T00:00:00")]
    new = [_listing("A", sold_price=4_700_000, scraped_at="2026-02-01T00:00:00")]

    merged, _ = merge_listings(new, existing)
    assert merged[0]["sold_price"] == 4_700_000


def test_both_have_sold_price_existing_wins_on_malformed_scraped_at():
    existing = [_listing("A", sold_price=4_500_000, scraped_at="not-a-date")]
    new = [_listing("A", sold_price=4_700_000, scraped_at="also-bad")]

    merged, _ = merge_listings(new, existing)
    assert merged[0]["sold_price"] == 4_500_000
