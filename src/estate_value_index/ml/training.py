"""Model training module for property price prediction.

Provides LGBMTrainer with built-in hyperparameter tuning using Optuna.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.model_selection import TimeSeriesSplit, cross_val_score

logger = logging.getLogger(__name__)

# Type aliases for training data
Features = pd.DataFrame | np.ndarray
Target = pd.Series | np.ndarray


class LGBMTrainer:
    """LightGBM model trainer with Optuna hyperparameter tuning.

    Args:
        random_state: Random seed for reproducibility

    Attributes:
        model: Trained LGBMRegressor (None before training)
        best_params: Best hyperparameters found during training
        tuning_time: Time spent on hyperparameter tuning (seconds)
    """

    # Default parameters from historical best model (2025-10-05, 238K MAE)
    DEFAULT_PARAMS: dict[str, Any] = {
        "num_leaves": 20,
        "learning_rate": 0.14512245277319302,
        "n_estimators": 1333,
        "subsample": 0.6637017332034828,
        "colsample_bytree": 0.73636499344142,
        "reg_alpha": 0.015254729458052608,
        "reg_lambda": 0.1631759695642342,
        "min_child_samples": 31,
        "max_depth": 9,
        "min_split_gain": 0.001955370866274525,
    }

    def __init__(self, random_state: int = 42) -> None:
        self.random_state = random_state
        self.model: LGBMRegressor | None = None
        self.best_params: dict[str, Any] | None = None
        self.tuning_time: float = 0.0

    def train(
        self,
        X_train: Features,
        y_train_log: Target,
        hyperparameter_tuning: bool = False,
        categorical_indices: Sequence[int] | None = None,
    ) -> LGBMRegressor:
        """Train LightGBM model with optional Optuna hyperparameter tuning.

        Args:
            X_train: Training features
            y_train_log: Log-transformed training target
            hyperparameter_tuning: Run Optuna Bayesian optimization
            categorical_indices: Indices of categorical feature columns

        Returns:
            Trained LGBMRegressor model
        """
        if hyperparameter_tuning:
            return self._train_with_tuning(X_train, y_train_log, categorical_indices)
        return self._train_with_defaults(X_train, y_train_log, categorical_indices)

    def _train_with_defaults(
        self,
        X_train: Features,
        y_train_log: Target,
        categorical_indices: Sequence[int] | None = None,
    ) -> LGBMRegressor:
        """Train with default optimized parameters."""
        logger.info("Training LightGBM with default parameters")

        self.best_params = self.DEFAULT_PARAMS.copy()
        self.model = self._create_model(self.best_params)
        self._fit_model(X_train, y_train_log, categorical_indices)
        self.tuning_time = 0.0

        return self.model

    def _train_with_tuning(
        self,
        X_train: Features,
        y_train_log: Target,
        categorical_indices: Sequence[int] | None = None,
    ) -> LGBMRegressor:
        """Train with Bayesian optimization using Optuna."""
        import optuna

        logger.info("Starting Optuna hyperparameter optimization")
        start_time = time.time()

        study = optuna.create_study(
            direction="minimize",
            sampler=optuna.samplers.TPESampler(seed=self.random_state),
            pruner=optuna.pruners.MedianPruner(n_startup_trials=5, n_warmup_steps=3),
        )

        optuna.logging.set_verbosity(optuna.logging.WARNING)

        def objective(trial: optuna.Trial) -> float:
            params = {
                "num_leaves": trial.suggest_int("num_leaves", 20, 50),
                "learning_rate": trial.suggest_float("learning_rate", 0.05, 0.15, log=True),
                "n_estimators": trial.suggest_int("n_estimators", 500, 1500),
                "subsample": trial.suggest_float("subsample", 0.6, 0.9),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.7, 0.9),
                "reg_alpha": trial.suggest_float("reg_alpha", 0.01, 0.1, log=True),
                "reg_lambda": trial.suggest_float("reg_lambda", 0.1, 0.5, log=True),
                "min_child_samples": trial.suggest_int("min_child_samples", 10, 50),
                "max_depth": trial.suggest_int("max_depth", 6, 12),
                "min_split_gain": trial.suggest_float("min_split_gain", 0.001, 0.01, log=True),
            }

            model = self._create_model(params)
            tscv = TimeSeriesSplit(n_splits=3)
            scores = cross_val_score(
                model, X_train, y_train_log, cv=tscv, scoring="neg_mean_absolute_error", n_jobs=-1
            )

            return float(-scores.mean())

        n_trials = 5
        study.optimize(objective, n_trials=n_trials, show_progress_bar=True)

        self.best_params = study.best_params
        self.model = self._create_model(self.best_params)
        self._fit_model(X_train, y_train_log, categorical_indices)

        self.tuning_time = time.time() - start_time
        optuna.logging.set_verbosity(optuna.logging.INFO)

        logger.info(
            "Optimization completed in %.1fs. Best CV MAE: %.2f", self.tuning_time, study.best_value
        )
        logger.debug("Best parameters: %s", self.best_params)

        return self.model

    def _create_model(self, params: dict[str, Any]) -> LGBMRegressor:
        """Create LGBMRegressor with given parameters."""
        base_params = {
            "objective": "regression",
            "metric": "mae",
            "boosting_type": "gbdt",
            "random_state": self.random_state,
            "verbosity": -1,
            "n_jobs": -1,
        }
        base_params.update(params)
        return LGBMRegressor(**base_params)

    def _fit_model(
        self,
        X_train: Features,
        y_train_log: Target,
        categorical_indices: Sequence[int] | None = None,
    ) -> None:
        """Fit the model with optional categorical feature handling."""
        if categorical_indices:
            self.model.fit(X_train, y_train_log, categorical_feature=categorical_indices)
        else:
            self.model.fit(X_train, y_train_log)

    def predict(self, X: Features) -> np.ndarray:
        """Make predictions with the trained model."""
        if self.model is None:
            raise ValueError("Model not trained. Call train() first.")
        return self.model.predict(X)

    def get_best_params(self) -> dict[str, Any]:
        """Get best parameters found during training."""
        return self.best_params.copy() if self.best_params else {}
