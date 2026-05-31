"""Tests for the training module."""

import numpy as np
import pytest

from src.estate_value_index.ml.training import LGBMTrainer
from tests.conftest import assert_valid_predictions


class TestTrainerIntegration:
    @pytest.mark.integration
    def test_trainer_with_lgbm_pipeline(self, sample_swedish_properties):
        from src.estate_value_index.ml.features import (
            SimplePredictionPipeline,
            build_feature_context,
            create_optimized_features,
            handle_missing_values,
        )

        valid_data = sample_swedish_properties.dropna(subset=["sold_price"])
        df_engineered = create_optimized_features(valid_data)

        numeric_features = ["listing_price", "living_area", "rooms", "monthly_fee"]
        categorical_features = ["area"]
        all_features = numeric_features + categorical_features

        X_train = df_engineered[all_features].copy()
        y_train_log = np.log1p(df_engineered["sold_price"].copy())

        X_train, _, _, _ = handle_missing_values(
            X_train, X_train.copy(), numeric_features, categorical_features
        )
        for col in categorical_features:
            if col in X_train.columns:
                X_train[col] = X_train[col].astype("category")

        feature_context = build_feature_context(df_engineered)
        categorical_indices = [
            X_train.columns.get_loc(col) for col in categorical_features if col in X_train.columns
        ]

        lgbm_trainer = LGBMTrainer(random_state=42)
        lgbm_model = lgbm_trainer.train(
            X_train,
            y_train_log,
            hyperparameter_tuning=False,
            categorical_indices=categorical_indices,
        )

        lgbm_pipeline = SimplePredictionPipeline(
            lgbm_model, numeric_features, categorical_features, context=feature_context
        )

        test_data = df_engineered.head(min(5, len(df_engineered)))
        lgbm_preds = lgbm_pipeline.predict(test_data)

        assert_valid_predictions(lgbm_preds)
        assert len(lgbm_preds) == len(test_data)
