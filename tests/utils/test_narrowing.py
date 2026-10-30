import numpy as np
import pandas as pd

from estate_value_index.utils.narrowing import is_missing, number


def test_number_returns_ints_and_floats_and_nothing_else() -> None:
    record = {"int": 3, "float": 2.5, "text": "7", "none": None}

    assert number(record, "int") == 3
    assert number(record, "float") == 2.5
    assert number(record, "text") is None
    assert number(record, "none") is None
    assert number(record, "absent") is None


def test_is_missing_covers_every_pandas_missing_marker() -> None:
    assert all(is_missing(value) for value in (None, np.nan, pd.NaT, pd.NA))
    assert not any(is_missing(value) for value in (0, "", "x", 1.5))
