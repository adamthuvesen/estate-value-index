from __future__ import annotations

from datetime import date

import pandas as pd

from estate_value_index.ml.data_fingerprint import fingerprint_training_frame


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "listing_id": ["1", "2", "3"],
            "sold_date": pd.to_datetime(["2026-01-01", "2026-03-05", "2026-02-01"]),
            "sold_price": [5_000_000, 6_000_000, 5_500_000],
            "images": [["a.jpg"], [], ["b.jpg"]],
        }
    )


def test_fingerprint_records_rows_and_newest_sold_date() -> None:
    fingerprint = fingerprint_training_frame(_frame())
    assert fingerprint.rows == 3
    assert fingerprint.max_sold_date == date(2026, 3, 5)
    assert len(fingerprint.sha256) == 64


def test_fingerprint_ignores_row_and_column_order() -> None:
    frame = _frame()
    shuffled = frame.iloc[[2, 0, 1]][list(reversed(frame.columns))]
    assert fingerprint_training_frame(shuffled) == fingerprint_training_frame(frame)


def test_fingerprint_changes_when_a_value_changes() -> None:
    changed = _frame()
    changed.loc[0, "sold_price"] = 5_000_001
    assert fingerprint_training_frame(changed).sha256 != fingerprint_training_frame(_frame()).sha256
