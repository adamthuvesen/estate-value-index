"""Generate city-wide (overall) statistics for the web Stats page.

Mirrors the per-area machinery in ``analytics.area_statistics`` but aggregates
across the whole published dataset instead of one area at a time. The output
schema is frozen; see the data contract shipped alongside the web types.

Sources:
- raw listings (``booli_listings_prod.json`` or BigQuery): every sold listing
- ``value_analysis.json``: property-level predictions, used for undervalued
  share per area and the ``best_value`` record.

Output: ``data/derived/overall_statistics.json``.
"""

from __future__ import annotations

import json
import logging
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from estate_value_index.analytics.area_statistics import (
    CONSTRUCTION_ERAS,
    _group_by_area,
    _price_per_sqm_value,
    calculate_price_by_size,
    calculate_price_per_sqm_by_rooms,
    calculate_size_distribution,
    construction_era_bucket,
    load_json,
    load_raw_listings,
    resolve_generated_at,
)
from estate_value_index.ml.area_names import get_display_name
from estate_value_index.ml.preprocessing import normalize_area_for_model

logger = logging.getLogger(__name__)

# Areas need at least this many rows in a bucket before we publish its median;
# below this the median is too noisy to trust. Applies to floor, fee, size, and
# area-premium buckets.
MIN_BUCKET_N = 30

# Per-arm minimum for the within-area amenity comparison: an area only counts
# toward the within-area diff when both the "with" and "without" arms clear this.
MIN_WITHIN_AREA_ARM_N = 20

# An area needs this many bidding rows before its premium is rankable.
MIN_PREMIUM_AREA_N = 30

# Ceiling for the biggest-bid-up record. In the production data every premium
# above this is an exact 2x/10x listing-price typo (the p99.9 premium is ~40%),
# so anything higher is a scrape error, not a bidding war.
MAX_PLAUSIBLE_PREMIUM_PCT = 75.0


@dataclass(frozen=True)
class OverallStatisticsPaths:
    value_analysis: Path
    raw_listings: Path
    output: Path


# --------------------------------------------------------------------------- #
# Pure helpers over list[dict] / list[float]
# --------------------------------------------------------------------------- #


def build_histogram(
    values: list[float],
    bins: int,
    clip_lo_pct: float,
    clip_hi_pct: float,
    *,
    as_int: bool = True,
) -> dict[str, Any]:
    """Histogram with percentiles on the unclipped values.

    Percentiles (p1/p25/p50/p75/p99) are computed over all supplied ``values``.
    Bin counts are computed after trimming values to the ``clip_lo_pct`` ..
    ``clip_hi_pct`` percentile window, so a few extreme sales don't stretch the
    axis and flatten the shape. ``sample_size`` is the pre-clip count.

    ``as_int`` rounds the reported edges and percentiles to whole numbers (for
    price / kr-m² domains); pass ``False`` for percentage domains.
    """
    arr = np.asarray([v for v in values if v is not None], dtype=float)
    sample_size = int(arr.size)

    p1, p25, p50, p75, p99 = (float(x) for x in np.percentile(arr, [1, 25, 50, 75, 99]))
    lo = float(np.percentile(arr, clip_lo_pct))
    hi = float(np.percentile(arr, clip_hi_pct))

    retained = arr[(arr >= lo) & (arr <= hi)]
    counts, _ = np.histogram(retained, bins=bins, range=(lo, hi))
    bin_width = (hi - lo) / bins

    def r(x: float) -> float:
        return int(round(x)) if as_int else x

    return {
        "min": r(lo),
        "max": r(hi),
        "bin_width": int(round(bin_width)) if as_int else bin_width,
        "counts": [int(c) for c in counts],
        "p1": r(p1),
        "p25": r(p25),
        "p50": r(p50),
        "p75": r(p75),
        "p99": r(p99),
        "sample_size": sample_size,
    }


def _month_key(sold_date: str | None) -> str | None:
    if not sold_date or len(sold_date) < 7:
        return None
    return sold_date[:7]


def _sold_prices(properties: list[dict]) -> list[float]:
    return [p["sold_price"] for p in properties if p.get("sold_price")]


def _ppsqm_values(properties: list[dict]) -> list[float]:
    return [v for p in properties if (v := _price_per_sqm_value(p)) is not None]


def build_monthly_series(properties: list[dict]) -> list[dict]:
    """Median price/kr-m² and volume for every month present, chronological.

    Unlike the area helper (which truncates to the last 12 months), this covers
    the whole range. The latest month is flagged ``is_partial`` — collection is
    ongoing so it is always incomplete.
    """
    by_month: dict[str, list[dict]] = defaultdict(list)
    for prop in properties:
        month = _month_key(prop.get("sold_date"))
        if month and prop.get("sold_price"):
            by_month[month].append(prop)

    months = sorted(by_month)
    if not months:
        return []
    latest = months[-1]

    series = []
    for month in months:
        rows = by_month[month]
        ppsqm = _ppsqm_values(rows)
        series.append(
            {
                "month": month,
                "median_price_per_sqm": round(statistics.median(ppsqm)) if ppsqm else 0,
                "median_sold_price": round(statistics.median(_sold_prices(rows))),
                "sales_count": len(rows),
                "is_partial": month == latest,
            }
        )
    return series


def build_seasonality(properties: list[dict]) -> list[dict]:
    """Per calendar-month (1..12) median kr-m² and mean sales per occurrence."""
    ppsqm_by_moy: dict[int, list[float]] = defaultdict(list)
    count_by_month: dict[str, int] = defaultdict(int)

    for prop in properties:
        month = _month_key(prop.get("sold_date"))
        if not month:
            continue
        moy = int(month[5:7])
        count_by_month[month] += 1
        value = _price_per_sqm_value(prop)
        if value is not None:
            ppsqm_by_moy[moy].append(value)

    # Group the per-month volumes by their calendar month to average occurrences.
    volumes_by_moy: dict[int, list[int]] = defaultdict(list)
    for month, count in count_by_month.items():
        volumes_by_moy[int(month[5:7])].append(count)

    result = []
    for moy in range(1, 13):
        ppsqm = ppsqm_by_moy.get(moy, [])
        volumes = volumes_by_moy.get(moy, [])
        if not ppsqm:
            continue
        result.append(
            {
                "month_of_year": moy,
                "median_price_per_sqm": round(statistics.median(ppsqm)),
                "avg_sales_count": round(statistics.mean(volumes), 1) if volumes else 0,
            }
        )
    return result


# --------------------------------------------------------------------------- #
# Bidding (rows with a real listing_price)
# --------------------------------------------------------------------------- #


def _has_listing_price(prop: dict) -> bool:
    listing_price = prop.get("listing_price")
    return listing_price is not None and listing_price > 0


def _premium_pct(prop: dict) -> float:
    listing_price = prop["listing_price"]
    return (prop["sold_price"] - listing_price) / listing_price * 100


def _bidding_rows(properties: list[dict]) -> list[dict]:
    return [p for p in properties if _has_listing_price(p) and p.get("sold_price")]


def _over_under_shares(premiums: list[float]) -> dict[str, float]:
    n = len(premiums)
    if not n:
        return {"share_over_ask": 0.0, "share_under_ask": 0.0, "share_at_ask": 0.0}
    over = sum(1 for x in premiums if x > 0)
    under = sum(1 for x in premiums if x < 0)
    at = n - over - under
    return {
        "share_over_ask": over / n,
        "share_under_ask": under / n,
        "share_at_ask": at / n,
    }


def build_listing_vs_sold(bidding: list[dict]) -> dict[str, Any]:
    listing_prices = [p["listing_price"] for p in bidding]
    sold_prices = [p["sold_price"] for p in bidding]
    premiums = [_premium_pct(p) for p in bidding]
    shares = _over_under_shares(premiums)
    return {
        "sample_size": len(bidding),
        "median_listing_price": round(statistics.median(listing_prices)),
        "median_sold_price": round(statistics.median(sold_prices)),
        "median_premium_pct": statistics.median(premiums),
        **shares,
    }


def build_bidding_monthly(bidding: list[dict]) -> list[dict]:
    by_month: dict[str, list[float]] = defaultdict(list)
    for prop in bidding:
        month = _month_key(prop.get("sold_date"))
        if month:
            by_month[month].append(_premium_pct(prop))

    months = sorted(by_month)
    if not months:
        return []
    latest = months[-1]

    result = []
    for month in months:
        premiums = by_month[month]
        shares = _over_under_shares(premiums)
        result.append(
            {
                "month": month,
                **shares,
                "sample_size": len(premiums),
                "is_partial": month == latest,
            }
        )
    return result


def _area_premiums(bidding: list[dict], published_areas: set[str]) -> list[dict]:
    by_area: dict[str, list[float]] = defaultdict(list)
    for prop in bidding:
        area_key = normalize_area_for_model(prop.get("area", ""))
        if area_key in published_areas:
            by_area[area_key].append(_premium_pct(prop))

    rows = []
    for area_key, premiums in by_area.items():
        if len(premiums) < MIN_PREMIUM_AREA_N:
            continue
        rows.append(
            {
                "area_name": area_key,
                "display_name": get_display_name(area_key),
                "avg_premium_pct": statistics.mean(premiums),
                "median_premium_pct": statistics.median(premiums),
                "sample_size": len(premiums),
            }
        )
    return rows


def build_bidding(bidding: list[dict], published_areas: set[str]) -> dict[str, Any]:
    premiums = [_premium_pct(p) for p in bidding]
    area_rows = sorted(
        _area_premiums(bidding, published_areas),
        key=lambda r: r["avg_premium_pct"],
        reverse=True,
    )
    return {
        "sample_size": len(bidding),
        "premium_pct_histogram": build_histogram(premiums, 50, 1, 99, as_int=False),
        "monthly_over_under": build_bidding_monthly(bidding),
        "top_premium_areas": area_rows[:5],
        "bottom_premium_areas": list(reversed(area_rows[-5:])) if area_rows else [],
    }


# --------------------------------------------------------------------------- #
# Geography (published areas)
# --------------------------------------------------------------------------- #


def _undervalued_share_by_area(value_properties: list[dict]) -> dict[str, float]:
    rankable_by_area: dict[str, list[dict]] = defaultdict(list)
    for prop in value_properties:
        if prop.get("is_rankable"):
            area_key = normalize_area_for_model(prop.get("area", ""))
            rankable_by_area[area_key].append(prop)

    shares = {}
    for area_key, rows in rankable_by_area.items():
        undervalued = sum(1 for p in rows if p.get("is_undervalued"))
        shares[area_key] = undervalued / len(rows)
    return shares


def build_geography(
    listings_by_area: dict[str, list[dict]],
    published_areas: list[str],
    undervalued_share: dict[str, float],
) -> dict[str, Any]:
    areas = []
    for area_key in published_areas:
        rows = listings_by_area[area_key]
        ppsqm = _ppsqm_values(rows)
        areas.append(
            {
                "area_name": area_key,
                "display_name": get_display_name(area_key),
                "median_price_per_sqm": round(statistics.median(ppsqm)) if ppsqm else 0,
                "median_sold_price": round(statistics.median(_sold_prices(rows))),
                "sales_count": len(rows),
                "undervalued_share": undervalued_share.get(area_key),
            }
        )
    areas.sort(key=lambda a: a["median_price_per_sqm"], reverse=True)
    return {"areas": areas}


# --------------------------------------------------------------------------- #
# Size / rooms
# --------------------------------------------------------------------------- #

# 10 m² buckets for the kr-m² vs size curve.
_PPSQM_SIZE_BUCKETS: list[tuple[str, int, int | None]] = [
    ("20-30", 20, 30),
    ("30-40", 30, 40),
    ("40-50", 40, 50),
    ("50-60", 50, 60),
    ("60-70", 60, 70),
    ("70-80", 70, 80),
    ("80-90", 80, 90),
    ("90-100", 90, 100),
    ("100-110", 100, 110),
    ("110-120", 110, 120),
    ("120-130", 120, 130),
    ("130-140", 130, 140),
    ("140+", 140, None),
]


def build_ppsqm_vs_size_curve(properties: list[dict]) -> list[dict]:
    bucket_values: dict[str, list[float]] = {label: [] for label, _, _ in _PPSQM_SIZE_BUCKETS}
    for prop in properties:
        living_area = prop.get("living_area")
        value = _price_per_sqm_value(prop)
        if not living_area or value is None:
            continue
        for label, low, high in _PPSQM_SIZE_BUCKETS:
            if living_area >= low and (high is None or living_area < high):
                bucket_values[label].append(value)
                break

    curve = []
    for label, low, high in _PPSQM_SIZE_BUCKETS:
        values = bucket_values[label]
        if len(values) < MIN_BUCKET_N:
            continue
        curve.append(
            {
                "size_bucket": label,
                "bucket_min": low,
                "bucket_max": high,
                "median_price_per_sqm": round(statistics.median(values)),
                "sample_size": len(values),
            }
        )
    return curve


# --------------------------------------------------------------------------- #
# Building (construction era, amenities, floor, fee)
# --------------------------------------------------------------------------- #


def build_construction_era(properties: list[dict]) -> list[dict]:
    ppsqm_by_era: dict[str, list[float]] = defaultdict(list)
    counts: dict[str, int] = defaultdict(int)
    total = 0
    for prop in properties:
        year = prop.get("construction_year")
        if not year:
            continue
        era = construction_era_bucket(year)
        counts[era] += 1
        total += 1
        value = _price_per_sqm_value(prop)
        if value is not None:
            ppsqm_by_era[era].append(value)

    result = []
    for era in CONSTRUCTION_ERAS:
        if not counts.get(era):
            continue
        ppsqm = ppsqm_by_era.get(era, [])
        result.append(
            {
                "era": era,
                "count": counts[era],
                "share": counts[era] / total if total else 0.0,
                "median_price_per_sqm": round(statistics.median(ppsqm)) if ppsqm else 0,
            }
        )
    return result


def _amenity_effect(properties: list[dict], flag: str) -> dict[str, Any]:
    """Effect of an amenity (balcony/elevator) on kr-m².

    ``null`` means unknown and is excluded; only rows where the flag is truly
    ``True`` or ``False`` count. When the source carries no ``False`` rows the
    "without" arm is empty, so the numeric diffs are reported as ``None`` rather
    than dividing by an empty set.
    """
    with_rows, without_rows = [], []
    for prop in properties:
        value = _price_per_sqm_value(prop)
        if value is None:
            continue
        state = prop.get(flag)
        if state is True:
            with_rows.append(value)
        elif state is False:
            without_rows.append(value)

    known = len(with_rows) + len(without_rows)
    median_with = round(statistics.median(with_rows)) if with_rows else None
    median_without = round(statistics.median(without_rows)) if without_rows else None
    naive_diff_pct = (
        (median_with - median_without) / median_without * 100
        if median_with is not None and median_without
        else None
    )
    within_diffs = _within_area_amenity_diffs(properties, flag)
    return {
        "known_count": known,
        "share_with": len(with_rows) / known if known else 0.0,
        "median_ppsqm_with": median_with,
        "median_ppsqm_without": median_without,
        "naive_diff_pct": naive_diff_pct,
        "within_area_diff_pct": (statistics.median(within_diffs) if within_diffs else None),
        "within_area_sample_areas": len(within_diffs),
    }


def _within_area_amenity_diffs(properties: list[dict], flag: str) -> list[float]:
    """Per-area kr-m² diff (with vs without), for areas with both arms >= 20."""
    by_area: dict[str, dict[bool, list[float]]] = defaultdict(lambda: {True: [], False: []})
    for prop in properties:
        value = _price_per_sqm_value(prop)
        state = prop.get(flag)
        if value is None or state not in (True, False):
            continue
        area_key = normalize_area_for_model(prop.get("area", ""))
        by_area[area_key][state].append(value)

    diffs = []
    for arms in by_area.values():
        with_rows, without_rows = arms[True], arms[False]
        if len(with_rows) < MIN_WITHIN_AREA_ARM_N or len(without_rows) < MIN_WITHIN_AREA_ARM_N:
            continue
        median_without = statistics.median(without_rows)
        if median_without:
            diffs.append((statistics.median(with_rows) - median_without) / median_without * 100)
    return diffs


_FLOOR_BUCKETS: list[tuple[str, int, int | None]] = [
    ("0", 0, 0),
    ("1", 1, 1),
    ("2", 2, 2),
    ("3", 3, 3),
    ("4", 4, 4),
    ("5", 5, 5),
    ("6+", 6, None),
]


def build_by_floor(properties: list[dict]) -> list[dict]:
    bucket_values: dict[str, list[float]] = {label: [] for label, _, _ in _FLOOR_BUCKETS}
    for prop in properties:
        floor = prop.get("floor")
        value = _price_per_sqm_value(prop)
        if floor is None or value is None:
            continue
        for label, low, high in _FLOOR_BUCKETS:
            if floor >= low and (high is None or floor <= high):
                bucket_values[label].append(value)
                break

    result = []
    for label, _, _ in _FLOOR_BUCKETS:
        values = bucket_values[label]
        if len(values) < MIN_BUCKET_N:
            continue
        result.append(
            {
                "floor_bucket": label,
                "median_price_per_sqm": round(statistics.median(values)),
                "sample_size": len(values),
            }
        )
    return result


_FEE_BUCKETS: list[tuple[str, float, float]] = [
    ("<2000", 0, 2000),
    ("2000-3000", 2000, 3000),
    ("3000-4000", 3000, 4000),
    ("4000-5000", 4000, 5000),
    ("5000+", 5000, float("inf")),
]


def build_monthly_fee(properties: list[dict]) -> dict[str, Any]:
    fee_per_sqm: list[float] = []
    bucket_rows: dict[str, list[dict]] = {label: [] for label, _, _ in _FEE_BUCKETS}

    for prop in properties:
        fee = prop.get("monthly_fee")
        if not fee:  # excludes null and 0
            continue
        living_area = prop.get("living_area")
        if living_area and living_area > 0:
            fee_per_sqm.append(fee / living_area)
        for label, low, high in _FEE_BUCKETS:
            if low <= fee < high:
                bucket_rows[label].append(prop)
                break

    by_bucket = []
    for label, _, _ in _FEE_BUCKETS:
        rows = bucket_rows[label]
        if len(rows) < MIN_BUCKET_N:
            continue
        ppsqm = _ppsqm_values(rows)
        by_bucket.append(
            {
                "fee_bucket": label,
                "median_sold_price": round(statistics.median(_sold_prices(rows))),
                "median_price_per_sqm": round(statistics.median(ppsqm)) if ppsqm else 0,
                "sample_size": len(rows),
            }
        )

    return {
        "fee_per_sqm_histogram": build_histogram(fee_per_sqm, 50, 1, 99, as_int=True),
        "median_price_by_fee_bucket": by_bucket,
    }


# --------------------------------------------------------------------------- #
# Records (superlatives)
# --------------------------------------------------------------------------- #


def _record_base(prop: dict) -> dict[str, Any]:
    area_key = normalize_area_for_model(prop.get("area", ""))
    return {
        "address": prop.get("address"),
        "area_name": area_key,
        "display_name": get_display_name(area_key),
        "sold_date": _normalize_record_date(prop.get("sold_date")),
        "url": prop.get("url"),
        "living_area": prop.get("living_area"),
        "rooms": prop.get("rooms"),
        "sold_price": prop.get("sold_price"),
    }


def _normalize_record_date(sold_date: str | None) -> str | None:
    return sold_date[:10] if sold_date else None


_HOUSE_NUMBER_RE = re.compile(r"\s+\d+\s*[A-Za-z]?$")


def _street_name(address: str) -> str:
    """Strip a trailing Swedish house number: 'Vasagatan 12B' -> 'Vasagatan'."""
    return _HOUSE_NUMBER_RE.sub("", address).strip()


def build_top_streets(properties: list[dict]) -> list[dict]:
    by_street: dict[str, list[float]] = defaultdict(list)
    for prop in properties:
        address = prop.get("address")
        sold_price = prop.get("sold_price")
        if not address or not sold_price:
            continue
        by_street[_street_name(address)].append(sold_price)

    ranked = sorted(by_street.items(), key=lambda kv: len(kv[1]), reverse=True)
    return [
        {
            "street": street,
            "sales_count": len(prices),
            "median_sold_price": round(statistics.median(prices)),
        }
        for street, prices in ranked[:10]
    ]


def _best_value_record(value_properties: list[dict]) -> dict[str, Any] | None:
    rankable = [
        p for p in value_properties if p.get("is_rankable") and p.get("value_score") is not None
    ]
    if not rankable:
        return None
    best = max(rankable, key=lambda p: p["value_score"])
    return {
        **_record_base(best),
        "prediction_delta_percentage": best.get("prediction_delta_percentage"),
        "value_score": best.get("value_score"),
    }


def build_records(properties: list[dict], value_properties: list[dict]) -> dict[str, Any]:
    priced = [p for p in properties if p.get("sold_price")]

    most_expensive = max(priced, key=lambda p: p["sold_price"])
    cheapest = min(priced, key=lambda p: p["sold_price"])

    ppsqm_rows = [(p, v) for p in properties if (v := _price_per_sqm_value(p)) is not None]
    highest_ppsqm_prop, highest_ppsqm = max(ppsqm_rows, key=lambda pv: pv[1])

    fast_rows = [
        p for p in priced if p.get("days_on_market") is not None and p["days_on_market"] >= 1
    ]
    fastest = min(fast_rows, key=lambda p: p["days_on_market"])

    bidding = _bidding_rows(properties)
    # The only premiums above this are exact 2x/10x listing-price typos in the
    # source (p99.9 of the distribution is ~40%); a record card must not
    # showcase a data error.
    plausible_bids = [p for p in bidding if _premium_pct(p) <= MAX_PLAUSIBLE_PREMIUM_PCT]
    biggest_bid_up = max(plausible_bids, key=_premium_pct)

    return {
        "most_expensive": _record_base(most_expensive),
        "cheapest": _record_base(cheapest),
        "highest_price_per_sqm": {
            **_record_base(highest_ppsqm_prop),
            "price_per_sqm": round(highest_ppsqm),
        },
        "fastest_sale": {
            **_record_base(fastest),
            "days_on_market": fastest["days_on_market"],
        },
        "biggest_bid_up": {
            **_record_base(biggest_bid_up),
            "premium_pct": _premium_pct(biggest_bid_up),
            "listing_price": biggest_bid_up["listing_price"],
        },
        "best_value": _best_value_record(value_properties),
        "top_streets": build_top_streets(properties),
    }


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #


def _published_areas(listings_by_area: dict[str, list[dict]]) -> list[str]:
    """Areas the web publishes: >= 2 raw listings, same rule as area_statistics."""
    return sorted(key for key, rows in listings_by_area.items() if len(rows) >= 2)


def _hero(properties: list[dict], published_areas: list[str]) -> dict[str, Any]:
    ppsqm = _ppsqm_values(properties)
    return {
        "total_sales": len(properties),
        "total_areas": len(published_areas),
        "median_sold_price": round(statistics.median(_sold_prices(properties))),
        "median_price_per_sqm": round(statistics.median(ppsqm)),
        "price_per_sqm_strip": build_histogram(ppsqm, 200, 0.5, 99.5, as_int=True),
    }


def _prices(properties: list[dict], bidding: list[dict]) -> dict[str, Any]:
    return {
        "sold_price_histogram": build_histogram(_sold_prices(properties), 60, 1, 99, as_int=True),
        "price_per_sqm_histogram": build_histogram(
            _ppsqm_values(properties), 60, 1, 99, as_int=True
        ),
        "listing_vs_sold": build_listing_vs_sold(bidding),
    }


def _date_range(properties: list[dict]) -> dict[str, str]:
    dates = sorted(d[:10] for p in properties if (d := p.get("sold_date")))
    return {"start": dates[0], "end": dates[-1]}


def _resolve_paths(
    value_analysis_path: Path | None,
    raw_listings_path: Path | None,
    output_path: Path | None,
) -> OverallStatisticsPaths:
    project_root = Path(__file__).resolve().parents[3]
    return OverallStatisticsPaths(
        value_analysis=value_analysis_path
        or project_root / "data" / "derived" / "value_analysis.json",
        raw_listings=raw_listings_path
        or project_root / "data" / "raw" / "booli" / "booli_listings_prod.json",
        output=output_path or project_root / "data" / "derived" / "overall_statistics.json",
    )


def _build_overall_statistics(
    raw_listings: list[dict],
    value_properties: list[dict],
    value_analysis: dict,
    raw_listings_source: str,
    value_analysis_name: str,
) -> dict[str, Any]:
    listings_by_area = _group_by_area(raw_listings)
    published_areas = _published_areas(listings_by_area)
    published_set = set(published_areas)
    bidding = _bidding_rows(raw_listings)
    undervalued_share = _undervalued_share_by_area(value_properties)

    return {
        "metadata": {
            "generated_at": resolve_generated_at(raw_listings, {}, value_analysis),
            "total_properties": len(raw_listings),
            "total_areas": len(published_areas),
            "date_range": _date_range(raw_listings),
            "data_sources": {
                "raw_listings": raw_listings_source,
                "value_analysis": value_analysis_name,
            },
        },
        "hero": _hero(raw_listings, published_areas),
        "prices": _prices(raw_listings, bidding),
        "over_time": {
            "monthly": build_monthly_series(raw_listings),
            "seasonality": build_seasonality(raw_listings),
        },
        "bidding": build_bidding(bidding, published_set),
        "geography": build_geography(listings_by_area, published_areas, undervalued_share),
        "size_rooms": {
            "price_per_sqm_by_rooms": calculate_price_per_sqm_by_rooms(raw_listings),
            "price_by_size": calculate_price_by_size(raw_listings),
            "size_distribution": calculate_size_distribution(raw_listings),
            "ppsqm_vs_size_curve": build_ppsqm_vs_size_curve(raw_listings),
        },
        "building": {
            "construction_era": build_construction_era(raw_listings),
            "amenities": {
                "balcony": _amenity_effect(raw_listings, "balcony"),
                "elevator": _amenity_effect(raw_listings, "elevator"),
            },
            "by_floor": build_by_floor(raw_listings),
            "monthly_fee": build_monthly_fee(raw_listings),
        },
        "records": build_records(raw_listings, value_properties),
    }


def generate_overall_statistics(
    *,
    data_source: str = "bigquery",
    value_analysis_path: Path | None = None,
    raw_listings_path: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Build the city-wide statistics file consumed by the web Stats page."""
    paths = _resolve_paths(value_analysis_path, raw_listings_path, output_path)

    logger.info("Loading data sources...")
    value_analysis = load_json(paths.value_analysis)
    raw_listings, raw_listings_source = load_raw_listings(data_source, paths.raw_listings)
    value_properties = value_analysis.get("properties", [])

    logger.info(
        "Loaded %d raw listings, %d value-analysis properties",
        len(raw_listings),
        len(value_properties),
    )

    output_data = _build_overall_statistics(
        raw_listings,
        value_properties,
        value_analysis,
        raw_listings_source,
        paths.value_analysis.name,
    )

    logger.info("Writing overall statistics to %s...", paths.output)
    paths.output.parent.mkdir(parents=True, exist_ok=True)
    with open(paths.output, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    logger.info(
        "Overall statistics: %d properties, %d areas -> %s",
        output_data["metadata"]["total_properties"],
        output_data["metadata"]["total_areas"],
        paths.output,
    )
    return output_data
