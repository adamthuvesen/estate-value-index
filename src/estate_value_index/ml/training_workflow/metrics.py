"""Training metrics and model fitting."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, mean_squared_error


def regression_metrics(y_true: pd.Series, y_pred: np.ndarray) -> dict[str, float]:
    """Compute common regression metrics for a prediction."""
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    mape = mean_absolute_percentage_error(y_true, y_pred)
    absolute_pct_error = np.abs((np.asarray(y_pred) - y_true.to_numpy()) / y_true.to_numpy())
    within_10_pct = np.mean(absolute_pct_error <= 0.10) * 100
    return {
        "mae": float(mae),
        "rmse": float(rmse),
        "mape": float(mape),
        "within_10_pct": float(within_10_pct),
    }


def train_and_evaluate(
    name: str,
    trainer,
    *,
    X_train: pd.DataFrame,
    y_train_log: pd.Series,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    hyperparameter_tuning: bool,
    log_target: bool = True,
    **fit_kwargs,
):
    """Train a model using the provided trainer and compute evaluation metrics."""
    model = trainer.train(
        X_train,
        y_train_log,
        hyperparameter_tuning=hyperparameter_tuning,
        **fit_kwargs,
    )

    if model is None or isinstance(model, str):
        raw_pred = np.asarray(trainer.predict(X_test), dtype=float)
    else:
        raw_pred = np.asarray(model.predict(X_test), dtype=float)
    pred = np.expm1(raw_pred) if log_target else raw_pred

    metrics = regression_metrics(y_test, pred)
    metrics.update(
        {
            "best_params": trainer.best_params,
            "tuning_time": float(getattr(trainer, "tuning_time", 0.0) or 0.0),
        }
    )

    return {
        "name": name,
        "model": model,
        "predictions": pred,
        "raw_predictions": raw_pred,
        "metrics": metrics,
    }
