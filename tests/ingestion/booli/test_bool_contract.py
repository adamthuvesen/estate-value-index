"""Cross-layer boolean coercion contract (ingestion vs ML features)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from estate_value_index.ingestion.booli.normalization import to_bool
from estate_value_index.ml.features import _coerce_nullable_bool

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "bool_coercion_cases.json"


@pytest.mark.parametrize("case", json.loads(FIXTURE_PATH.read_text(encoding="utf-8")))
def test_bool_coercion_contract(case: dict) -> None:
    raw = case["input"]
    expected = case["expected"]

    assert to_bool(raw) is expected

    series = pd.Series([raw], dtype="object")
    coerced = _coerce_nullable_bool(series).iloc[0]
    if expected is None:
        assert pd.isna(coerced)
    else:
        assert bool(coerced) is expected
