"""Typed helpers and fakes shared by tests."""

from typing import Any

import pandas as pd


def value_at(frame: pd.DataFrame, row: Any, column: str) -> Any:
    """One cell as ``Any``: pandas types ``.loc`` cells as ``Scalar``, which does not compare."""
    value: Any = frame.at[row, column]
    return value
