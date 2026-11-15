"""Which data a model trained on: row count, newest ``sold_date``, and a content hash (D7).

The BigQuery listings table is mutable, so the metrics artifact records this
fingerprint instead of a snapshot pin. The same frame gives the same
fingerprint whatever its column order. Row order does not matter only when
``listing_id`` is unique, because rows are sorted by ``listing_id`` alone.
"""

from __future__ import annotations

import hashlib
from datetime import date

import pandas as pd
from pydantic import BaseModel, ConfigDict


class DataFingerprint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rows: int
    max_sold_date: date | None
    sha256: str


def fingerprint_training_frame(frame: pd.DataFrame) -> DataFingerprint:
    ordered = frame.sort_index(axis=1)
    if "listing_id" in ordered.columns:
        ordered = ordered.sort_values("listing_id", kind="stable")
    payload = ordered.to_json(orient="records", date_format="iso", date_unit="ns")
    sold_date = (
        pd.to_datetime(frame["sold_date"], errors="coerce").max()
        if "sold_date" in frame.columns
        else pd.NaT
    )
    return DataFingerprint(
        rows=len(frame),
        max_sold_date=None if pd.isna(sold_date) else sold_date.date(),
        sha256=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    )
