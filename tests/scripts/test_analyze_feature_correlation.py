"""Tests for feature-correlation analysis helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("statsmodels")

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "analyze_feature_correlation.py"


@pytest.fixture(scope="module")
def correlation_module():
    spec = importlib.util.spec_from_file_location(
        "analyze_feature_correlation_under_test", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_area_feature_names_excludes_living_area(correlation_module):
    numeric_features = [
        "listing_price",
        "living_area",
        "living_area_squared",
        "area_avg_price",
        "area_sales_volume_3m",
    ]

    assert correlation_module._area_feature_names(numeric_features) == [
        "area_avg_price",
        "area_sales_volume_3m",
    ]


def test_key_feature_names_keeps_available_features_only(correlation_module):
    df = pd.DataFrame(
        {
            "listing_price": [1.0],
            "sold_price": [2.0],
            "area_avg_price": [3.0],
        }
    )

    assert correlation_module._key_feature_names(
        df, ["area_avg_price", "missing_area_feature"]
    ) == ["listing_price", "sold_price", "area_avg_price"]


def test_high_corr_area_features_filters_by_area_and_threshold(correlation_module):
    listing_corr = pd.Series(
        {
            "listing_price": 1.0,
            "area_avg_price": 0.7,
            "area_sales_volume_3m": 0.2,
            "rooms": 0.9,
        }
    )

    high_corr = correlation_module._high_corr_area_features(
        listing_corr,
        ["area_avg_price", "area_sales_volume_3m"],
    )

    assert high_corr.to_dict() == {"area_avg_price": 0.7}


def test_mutual_information_report_returns_empty_when_target_missing(correlation_module):
    mi_df, listing_mi, area_mi = correlation_module._mutual_information_report(
        pd.DataFrame({"listing_price": [1.0, 2.0, 3.0]}),
        ["listing_price"],
        [],
    )

    assert mi_df.empty
    assert listing_mi.empty
    assert area_mi.empty


def test_listing_price_dominates_area_features(correlation_module):
    assert correlation_module._listing_price_dominates_area_features(
        pd.Series([0.9]),
        pd.Series([0.1, 0.2]),
        ratio=3.0,
    )
    assert not correlation_module._listing_price_dominates_area_features(
        pd.Series(dtype=float),
        pd.Series([0.1, 0.2]),
    )
