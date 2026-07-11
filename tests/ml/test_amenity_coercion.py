"""Regression tests for amenity boolean coercion (fix-amenity-boolean-coercion).

Pins the canonical truth-table that any boolean amenity parser in this repo
must follow, and the rule that unrecognised tokens become nullable rather
than collapsing to ``True`` via bare ``bool(value)``.
"""

from __future__ import annotations

import pandas as pd
import pytest

from estate_value_index.ingestion.booli.normalization import to_bool
from estate_value_index.ml.features import _coerce_nullable_bool

_CANONICAL_TRUTH_TABLE = [
    (True, True, True),
    (False, False, False),
    (1, True, True),
    (0, False, False),
    ("yes", True, True),
    ("Yes", True, True),
    ("YES", True, True),
    ("y", True, True),
    ("true", True, True),
    ("True", True, True),
    ("ja", True, True),
    ("1", True, True),
    ("no", False, False),
    ("No", False, False),
    ("NO", False, False),
    ("n", False, False),
    ("false", False, False),
    ("False", False, False),
    ("nej", False, False),
    ("0", False, False),
]


@pytest.mark.parametrize("raw,expected_pipeline,expected_feature", _CANONICAL_TRUTH_TABLE)
def test_canonical_truth_table_pipeline(raw, expected_pipeline, expected_feature):
    assert to_bool(raw) is expected_pipeline


@pytest.mark.parametrize("raw,expected_pipeline,expected_feature", _CANONICAL_TRUTH_TABLE)
def test_canonical_truth_table_feature(raw, expected_pipeline, expected_feature):
    series = pd.Series([raw])
    coerced = _coerce_nullable_bool(series).iloc[0]
    assert bool(coerced) is expected_feature


_UNRECOGNISED = ["unknown", "-", "maybe", "ej känt", "n/a"]


@pytest.mark.parametrize("raw", _UNRECOGNISED)
def test_unrecognised_token_returns_none_at_pipeline(raw):
    assert to_bool(raw) is None
    assert bool(raw) is True  # contrast: bare bool() would corrupt the value


@pytest.mark.parametrize("raw", _UNRECOGNISED)
def test_unrecognised_token_returns_na_at_feature(raw):
    series = pd.Series([raw])
    coerced = _coerce_nullable_bool(series)
    assert coerced.isna().iloc[0]


def test_amenity_feature_block_handles_string_no():
    """A scraped 'no' for elevator/balcony must not become has_*='yes'."""
    from estate_value_index.ml.features.basic import _create_amenity_features

    df = pd.DataFrame(
        {
            "elevator": ["no", "yes", "unknown", True, False, None],
            "balcony": ["nej", "ja", "maybe", True, False, None],
            "floor": [3, 4, 1, 2, 5, 0],
        }
    )
    out = _create_amenity_features(df.copy())
    assert list(out["has_elevator"]) == ["no", "yes", "no", "yes", "no", "no"]
    assert list(out["has_balcony"]) == ["no", "yes", "no", "yes", "no", "no"]
