"""Helpers for hiding asking-price signals in no-list-price training paths."""

from __future__ import annotations

import numpy as np
import pandas as pd

ASK_PRICE_SIGNAL_COLUMNS = (
    "listing_price",
    "price_per_sqm",
    "relative_area_price",
    "price_change",
    "total_cost_per_sqm",
    "cost_benefit_ratio",
    "efficiency_premium",
)


def mask_ask_price_signals(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with direct and derived asking-price columns nulled."""
    masked = frame.copy()
    for column in ASK_PRICE_SIGNAL_COLUMNS:
        masked[column] = np.nan
    return masked
