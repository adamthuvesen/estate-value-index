from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from estate_value_index.ml.features.context import FeatureEngineeringContext
from estate_value_index.ml.features.orchestrator import create_optimized_features


class SimplePredictionPipeline:
    """Simple prediction pipeline for trained models.

    Handles all feature engineering internally using the same create_optimized_features
    function used during training. Expects only raw input features and derives
    all necessary features automatically.
    """

    def __init__(
        self,
        model: Any,
        numeric_features: Sequence[str],
        categorical_features: Sequence[str],
        *,
        context: FeatureEngineeringContext,
    ) -> None:
        self.model = model
        self.numeric_features = numeric_features
        self.categorical_features = categorical_features
        self.context = context

    def predict(self, X_raw: pd.DataFrame) -> np.ndarray:
        """Generate predictions from raw input data."""
        # Create engineered features from raw input
        X_eng = create_optimized_features(X_raw, context=self.context)

        # Select and prepare features
        X = X_eng[self.numeric_features + self.categorical_features].copy()

        # Handle missing values using training statistics
        X = self._fill_missing_values(X)

        # Predict and transform back from log space
        y_pred_log = self.model.predict(X)
        return np.expm1(y_pred_log)

    def _fill_missing_values(self, X: pd.DataFrame) -> pd.DataFrame:
        """Fill missing values using training statistics."""
        for col in self.numeric_features:
            if col in X.columns:
                fill_value = self.context.numeric_fill_values.get(col)
                if fill_value is None or pd.isna(fill_value):
                    X[col] = X[col].fillna(0)
                else:
                    X[col] = X[col].fillna(fill_value)

        for col in self.categorical_features:
            if col in X.columns:
                mode_val = self.context.categorical_fill_values.get(col, "unknown")
                if mode_val is None or (isinstance(mode_val, float) and pd.isna(mode_val)):
                    mode_val = "unknown"
                X[col] = X[col].fillna(mode_val)
                X[col] = X[col].astype("category")

        return X
