"""Test get_categorical_indices uses isinstance, not deprecated helper."""

from __future__ import annotations

import pandas as pd

from estate_value_index.ml.features import get_categorical_indices


def test_returns_index_of_categorical_column():
    df = pd.DataFrame(
        {
            "a": [1, 2],
            "b": pd.Categorical(["x", "y"]),
        }
    )
    # No column listed in categorical_features → falls through to the dtype check.
    assert get_categorical_indices(df, []) == [1]


def test_listed_categorical_feature_takes_precedence():
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    assert get_categorical_indices(df, ["a"]) == [0]
