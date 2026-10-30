"""The areas module gives the same output as the three implementations it replaced.

``tests/fixtures/area_normalization_golden.json`` was written by the old
``ingestion.processing.clean_area_name``, ``ml.preprocessing.normalize_area_for_model``,
and ``ml.area_names.get_display_name``, over every area value in the committed
fixtures, tests, reference data, and alias maps, plus Booli-shaped variants of each.
"""

from __future__ import annotations

import json
from pathlib import Path

from estate_value_index.areas import clean_area_name, get_display_name, normalize_area_for_model

GOLDEN = json.loads(
    (Path(__file__).parent / "fixtures" / "area_normalization_golden.json").read_text(
        encoding="utf-8"
    )
)


def test_area_forms_match_the_replaced_implementations() -> None:
    assert len(GOLDEN) > 1000
    mismatches = []
    for row in GOLDEN:
        raw = row["input"]
        key = normalize_area_for_model(raw)
        actual = {"model_key": key, "display_name": get_display_name(key)}
        if raw is not None:
            cleaned = clean_area_name(raw)
            actual["clean_area_name"] = cleaned
            actual["model_key_of_clean"] = normalize_area_for_model(cleaned)
        expected = {name: row[name] for name in actual}
        if actual != expected:
            mismatches.append((raw, expected, actual))
    assert mismatches == []
