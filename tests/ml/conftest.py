"""Shared fixtures for ML training tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def sample_training_features() -> pd.DataFrame:
    """Training features for LGBMTrainer tests."""
    np.random.seed(42)
    n_samples = 100
    return pd.DataFrame(
        {
            "living_area": np.random.uniform(30, 150, n_samples),
            "rooms": np.random.randint(1, 6, n_samples),
            "floor": np.random.randint(0, 10, n_samples),
            "monthly_fee": np.random.uniform(2000, 8000, n_samples),
            "construction_year": np.random.randint(1900, 2024, n_samples),
        }
    )


@pytest.fixture
def sample_training_target() -> np.ndarray:
    """Log-transformed target for training."""
    np.random.seed(42)
    prices = np.random.uniform(2_000_000, 8_000_000, 100)
    return np.log(prices)
