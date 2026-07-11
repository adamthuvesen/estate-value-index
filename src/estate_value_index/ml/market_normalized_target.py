"""Market-index target normalization used by production model training."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error

from estate_value_index.ml.residual_calibration import _prepare_matrices, _train_lgbm

DEFAULT_BLEND_WEIGHTS = tuple(round(value, 2) for value in np.linspace(0.0, 1.0, 21))
MARKET_INDEX_COLUMN = "market_ppsqm_index"


@dataclass(frozen=True)
class MarketNormalizedFit:
    predictions: np.ndarray
    reference_index: float
    train_rows: int
    fallback_prediction_rows: int


def normalize_prices_to_market_index(
    prices: pd.Series | np.ndarray,
    market_index: pd.Series | np.ndarray,
    *,
    reference_index: float,
) -> pd.Series:
    """Convert SEK prices to a common market-index level."""
    if not np.isfinite(reference_index) or reference_index <= 0:
        raise ValueError("reference_index must be a positive finite value")

    price_series = _as_numeric_series(prices)
    index_series = _as_numeric_series(market_index, index=price_series.index)
    return price_series * reference_index / index_series


def denormalize_market_predictions(
    normalized_predictions: np.ndarray,
    market_index: pd.Series | np.ndarray,
    *,
    reference_index: float,
    fallback_predictions: np.ndarray,
) -> np.ndarray:
    """Convert market-normalized SEK predictions back to row-month SEK prices."""
    if not np.isfinite(reference_index) or reference_index <= 0:
        raise ValueError("reference_index must be a positive finite value")

    normalized = np.asarray(normalized_predictions, dtype=float)
    index_values = _as_numeric_series(market_index).to_numpy(dtype=float)
    fallback = np.asarray(fallback_predictions, dtype=float)
    prices = normalized * index_values / reference_index
    valid = (
        np.isfinite(prices)
        & np.isfinite(normalized)
        & np.isfinite(index_values)
        & (index_values > 0)
    )
    return np.where(valid, np.clip(prices, 0, None), fallback)


def market_index_reference(market_index: pd.Series | np.ndarray) -> float:
    """Use the median valid training market index as the normalizing baseline."""
    valid = _as_numeric_series(market_index)
    valid = valid[np.isfinite(valid) & (valid > 0)]
    if valid.empty:
        raise ValueError("At least one positive market index is required")
    return float(valid.median())


def blend_market_predictions(
    base_predictions: np.ndarray,
    normalized_predictions: np.ndarray,
    *,
    normalized_weight: float,
) -> np.ndarray:
    """Blend base SEK predictions with market-normalized-target SEK predictions."""
    if not 0.0 <= normalized_weight <= 1.0:
        raise ValueError("normalized_weight must be between 0 and 1")
    base = np.asarray(base_predictions, dtype=float)
    normalized = np.asarray(normalized_predictions, dtype=float)
    return (1.0 - normalized_weight) * base + normalized_weight * normalized


def select_best_market_blend_weight(
    y_true: np.ndarray,
    base_predictions: np.ndarray,
    normalized_predictions: np.ndarray,
    *,
    weights: tuple[float, ...] = DEFAULT_BLEND_WEIGHTS,
) -> dict[str, object]:
    """Pick the normalized-target blend weight with lowest OOF MAE."""
    candidates = []
    for weight in weights:
        prediction = blend_market_predictions(
            base_predictions,
            normalized_predictions,
            normalized_weight=weight,
        )
        candidates.append(
            {
                "normalized_weight": float(weight),
                "mae": float(mean_absolute_error(y_true, prediction)),
            }
        )
    best = min(candidates, key=lambda candidate: candidate["mae"])
    return {
        "normalized_weight": best["normalized_weight"],
        "oof_mae": best["mae"],
        "candidates": candidates,
    }


def _fit_market_normalized_predictions(
    prepared,
    random_state: int,
    *,
    fallback_predictions: np.ndarray,
    lgbm_params: dict[str, Any] | None = None,
) -> MarketNormalizedFit:
    """Fit the normalized target for one training/validation split."""
    X_train, X_test, y_train, _ = _prepare_matrices(prepared)
    train_index = _market_index(prepared.train_engineered)
    test_index = _market_index(prepared.test_engineered)
    reference_index = market_index_reference(train_index)
    y_normalized = normalize_prices_to_market_index(
        y_train,
        train_index,
        reference_index=reference_index,
    )
    valid_train = (
        y_train.gt(0)
        & y_normalized.gt(0)
        & y_normalized.notna()
        & train_index.gt(0)
        & train_index.notna()
    )
    if valid_train.sum() < 100:
        raise ValueError("Not enough valid market index rows to train a normalized target model")

    model = _train_lgbm(
        X_train.loc[valid_train],
        y_normalized.loc[valid_train],
        prepared.categorical_features,
        random_state,
        lgbm_params=lgbm_params,
    )
    normalized_predictions = np.expm1(model.predict(X_test))
    predictions = denormalize_market_predictions(
        normalized_predictions,
        test_index,
        reference_index=reference_index,
        fallback_predictions=fallback_predictions,
    )
    fallback_rows = int((~test_index.gt(0) | test_index.isna()).sum())
    return MarketNormalizedFit(
        predictions=predictions,
        reference_index=reference_index,
        train_rows=int(valid_train.sum()),
        fallback_prediction_rows=fallback_rows,
    )


def _market_index(frame: pd.DataFrame) -> pd.Series:
    if MARKET_INDEX_COLUMN not in frame.columns:
        raise ValueError(f"{MARKET_INDEX_COLUMN} is required for market-normalized target training")
    return pd.to_numeric(frame[MARKET_INDEX_COLUMN], errors="coerce")


def _as_numeric_series(values: pd.Series | np.ndarray, *, index=None) -> pd.Series:
    if isinstance(values, pd.Series):
        return pd.to_numeric(values, errors="coerce")
    return pd.to_numeric(pd.Series(values, index=index), errors="coerce")
