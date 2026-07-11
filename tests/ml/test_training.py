"""Unit tests for ml/training.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from lightgbm import LGBMRegressor

from estate_value_index.ml.training import LGBMTrainer, _raw_price_mae


def test_raw_price_mae_inverts_log_targets() -> None:
    y_true_log = np.log1p([100.0, 200.0])
    y_pred_log = np.log1p([110.0, 180.0])

    assert _raw_price_mae(y_true_log, y_pred_log) == pytest.approx(15.0)


class TestLGBMTrainerInit:
    @pytest.mark.unit
    def test_init_default_random_state(self) -> None:
        assert LGBMTrainer().random_state == 42

    @pytest.mark.unit
    def test_init_custom_random_state(self) -> None:
        assert LGBMTrainer(random_state=123).random_state == 123

    @pytest.mark.unit
    def test_init_model_is_none(self) -> None:
        assert LGBMTrainer().model is None

    @pytest.mark.unit
    def test_init_best_params_is_none(self) -> None:
        assert LGBMTrainer().best_params is None

    @pytest.mark.unit
    def test_init_tuning_time_is_zero(self) -> None:
        assert LGBMTrainer().tuning_time == 0.0


class TestLGBMTrainerCreateModel:
    @pytest.mark.unit
    def test_create_model_returns_lgbm_regressor(self) -> None:
        model = LGBMTrainer()._create_model({"num_leaves": 31, "learning_rate": 0.1})
        assert isinstance(model, LGBMRegressor)

    @pytest.mark.unit
    def test_create_model_includes_base_params(self) -> None:
        model = LGBMTrainer(random_state=99)._create_model({"num_leaves": 31})

        assert model.random_state == 99
        assert model.objective == "regression"
        assert model.metric == "mae"
        assert model.boosting_type == "gbdt"

    @pytest.mark.unit
    def test_create_model_custom_params_override(self) -> None:
        model = LGBMTrainer()._create_model(
            {
                "num_leaves": 50,
                "learning_rate": 0.05,
                "n_estimators": 500,
            }
        )

        assert model.num_leaves == 50
        assert model.learning_rate == 0.05
        assert model.n_estimators == 500


class TestLGBMTrainerTrain:
    @pytest.mark.unit
    def test_train_without_tuning_uses_defaults(
        self,
        sample_training_features: pd.DataFrame,
        sample_training_target: np.ndarray,
    ) -> None:
        trainer = LGBMTrainer()

        model = trainer.train(
            sample_training_features,
            sample_training_target,
            hyperparameter_tuning=False,
        )

        assert isinstance(model, LGBMRegressor)
        assert trainer.best_params == LGBMTrainer.DEFAULT_PARAMS
        assert trainer.tuning_time == 0.0

    @pytest.mark.unit
    def test_train_stores_model(
        self,
        sample_training_features: pd.DataFrame,
        sample_training_target: np.ndarray,
    ) -> None:
        trainer = LGBMTrainer()
        trainer.train(sample_training_features, sample_training_target)

        assert trainer.model is not None
        assert isinstance(trainer.model, LGBMRegressor)

    @pytest.mark.unit
    def test_train_with_tuning_calls_optuna(
        self,
        sample_training_features: pd.DataFrame,
        sample_training_target: np.ndarray,
    ) -> None:
        trainer = LGBMTrainer()

        with patch("optuna.create_study") as mock_create_study:
            mock_study = MagicMock()
            mock_study.best_params = {
                "num_leaves": 25,
                "learning_rate": 0.1,
                "n_estimators": 100,
                "subsample": 0.8,
                "colsample_bytree": 0.8,
                "reg_alpha": 0.02,
                "reg_lambda": 0.2,
                "min_child_samples": 20,
                "max_depth": 8,
                "min_split_gain": 0.005,
            }
            mock_study.best_value = 0.1
            mock_create_study.return_value = mock_study

            trainer.train(
                sample_training_features,
                sample_training_target,
                hyperparameter_tuning=True,
            )

        assert mock_create_study.called
        assert mock_study.optimize.called
        assert trainer.tuning_time > 0

    @pytest.mark.unit
    def test_train_with_categorical_indices(
        self,
        sample_training_features: pd.DataFrame,
        sample_training_target: np.ndarray,
    ) -> None:
        df = sample_training_features.copy()
        df["property_type"] = pd.Categorical(["apt"] * len(df))

        model = LGBMTrainer().train(
            df,
            sample_training_target,
            categorical_indices=[df.columns.get_loc("property_type")],
        )

        assert isinstance(model, LGBMRegressor)

    @pytest.mark.unit
    def test_train_with_preselected_parameters(
        self,
        sample_training_features: pd.DataFrame,
        sample_training_target: np.ndarray,
    ) -> None:
        trainer = LGBMTrainer()
        parameters = {**LGBMTrainer.DEFAULT_PARAMS, "num_leaves": 31}

        model = trainer.train(
            sample_training_features,
            sample_training_target,
            parameters=parameters,
        )

        assert model.num_leaves == 31
        assert trainer.best_params == parameters

    @pytest.mark.unit
    def test_train_rejects_tuning_with_preselected_parameters(
        self,
        sample_training_features: pd.DataFrame,
        sample_training_target: np.ndarray,
    ) -> None:
        with pytest.raises(ValueError, match="cannot be combined"):
            LGBMTrainer().train(
                sample_training_features,
                sample_training_target,
                hyperparameter_tuning=True,
                parameters=LGBMTrainer.DEFAULT_PARAMS,
            )


class TestLGBMTrainerPredict:
    @pytest.mark.unit
    def test_predict_raises_if_not_trained(self, sample_training_features: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="Model not trained"):
            LGBMTrainer().predict(sample_training_features)

    @pytest.mark.unit
    def test_predict_returns_numpy_array(
        self,
        sample_training_features: pd.DataFrame,
        sample_training_target: np.ndarray,
    ) -> None:
        trainer = LGBMTrainer()
        trainer.train(sample_training_features, sample_training_target)

        assert isinstance(trainer.predict(sample_training_features), np.ndarray)

    @pytest.mark.unit
    def test_predict_correct_shape(
        self,
        sample_training_features: pd.DataFrame,
        sample_training_target: np.ndarray,
    ) -> None:
        trainer = LGBMTrainer()
        trainer.train(sample_training_features, sample_training_target)

        predictions = trainer.predict(sample_training_features)
        assert predictions.shape == (len(sample_training_features),)

    @pytest.mark.unit
    def test_predict_accepts_numpy_array(
        self,
        sample_training_features: pd.DataFrame,
        sample_training_target: np.ndarray,
    ) -> None:
        trainer = LGBMTrainer()
        trainer.train(sample_training_features, sample_training_target)

        predictions = trainer.predict(sample_training_features.values)

        assert isinstance(predictions, np.ndarray)
        assert len(predictions) == len(sample_training_features)


class TestLGBMTrainerGetBestParams:
    @pytest.mark.unit
    def test_get_best_params_returns_copy(
        self,
        sample_training_features: pd.DataFrame,
        sample_training_target: np.ndarray,
    ) -> None:
        trainer = LGBMTrainer()
        trainer.train(sample_training_features, sample_training_target)

        params = trainer.get_best_params()
        params["num_leaves"] = 9999

        assert trainer.best_params["num_leaves"] != 9999

    @pytest.mark.unit
    def test_get_best_params_empty_if_not_trained(self) -> None:
        assert LGBMTrainer().get_best_params() == {}

    @pytest.mark.unit
    def test_get_best_params_after_training(
        self,
        sample_training_features: pd.DataFrame,
        sample_training_target: np.ndarray,
    ) -> None:
        trainer = LGBMTrainer()
        trainer.train(sample_training_features, sample_training_target)

        params = trainer.get_best_params()
        assert "num_leaves" in params
        assert "learning_rate" in params
        assert "n_estimators" in params


class TestDefaultParams:
    @pytest.mark.unit
    def test_default_params_exist(self) -> None:
        assert hasattr(LGBMTrainer, "DEFAULT_PARAMS")
        assert isinstance(LGBMTrainer.DEFAULT_PARAMS, dict)

    @pytest.mark.unit
    def test_default_params_contains_required_keys(self) -> None:
        required_keys = [
            "num_leaves",
            "learning_rate",
            "n_estimators",
            "subsample",
            "colsample_bytree",
            "reg_alpha",
            "reg_lambda",
            "min_child_samples",
            "max_depth",
            "min_split_gain",
        ]
        for key in required_keys:
            assert key in LGBMTrainer.DEFAULT_PARAMS

    @pytest.mark.unit
    def test_default_params_reasonable_values(self) -> None:
        params = LGBMTrainer.DEFAULT_PARAMS

        assert 10 <= params["num_leaves"] <= 100
        assert 0.01 <= params["learning_rate"] <= 0.5
        assert 100 <= params["n_estimators"] <= 5000
        assert 0.5 <= params["subsample"] <= 1.0
        assert 0.5 <= params["colsample_bytree"] <= 1.0
