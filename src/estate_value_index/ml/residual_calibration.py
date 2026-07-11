"""Residual calibration used by production model training and inference."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from estate_value_index.ml import (
    build_feature_context,
    create_optimized_features,
    get_categorical_indices,
    get_feature_lists,
    handle_missing_values,
)
from estate_value_index.ml.ask_price import mask_ask_price_signals
from estate_value_index.ml.training import LGBMTrainer
from estate_value_index.ml.training_workflow.data import load_feature_subset
from estate_value_index.ml.training_workflow.metrics import regression_metrics

CENTRAL_AREAS = frozenset({"ostermalm", "vasastan", "sodermalm", "kungsholmen"})
CALIBRATION_NUMERIC_FEATURES = [
    "base_prediction",
    "base_prediction_ppsqm",
    "living_area",
    "rooms",
    "floor",
    "micro_area_ppsqm_median",
    "micro_area_ppsqm_count",
    "h3_neighbor_ppsqm",
    "same_size_ppsqm_median",
    "same_size_ppsqm_count",
    "market_ppsqm_index",
    "market_ppsqm_index_change_3m",
    "market_sales_volume",
    "market_months_since_2020",
    "market_data_age_months",
    "is_central_area",
]
CALIBRATION_CATEGORICAL_FEATURES = ["area", "h3_res9", "micro_area_resolution_used"]


@dataclass(frozen=True)
class PreparedModelData:
    train_engineered: pd.DataFrame
    test_engineered: pd.DataFrame
    numeric_features: list[str]
    categorical_features: list[str]
    all_features: list[str]


@dataclass(frozen=True)
class BaseFitResult:
    model: LGBMRegressor
    predictions: np.ndarray
    test_frame: pd.DataFrame


def build_calibration_features(
    frame: pd.DataFrame,
    base_predictions: np.ndarray | pd.Series,
) -> pd.DataFrame:
    """Create residual-calibrator inputs from engineered rows and base predictions."""
    features = pd.DataFrame(index=frame.index)
    predictions = pd.Series(np.asarray(base_predictions, dtype=float), index=frame.index)
    living_area = pd.to_numeric(frame.get("living_area"), errors="coerce").replace(0, np.nan)

    features["base_prediction"] = predictions
    features["base_prediction_ppsqm"] = predictions / living_area
    for column in CALIBRATION_NUMERIC_FEATURES:
        if column in {"base_prediction", "base_prediction_ppsqm", "is_central_area"}:
            continue
        if column in frame.columns:
            features[column] = pd.to_numeric(frame[column], errors="coerce")
        else:
            features[column] = np.nan

    area = (
        frame["area"].astype("string")
        if "area" in frame.columns
        else pd.Series(pd.NA, index=frame.index)
    )
    features["is_central_area"] = area.isin(CENTRAL_AREAS).astype(float)

    for column in CALIBRATION_CATEGORICAL_FEATURES:
        if column in frame.columns:
            features[column] = frame[column].astype("string").fillna("unknown")
        else:
            features[column] = "unknown"

    return features[CALIBRATION_NUMERIC_FEATURES + CALIBRATION_CATEGORICAL_FEATURES]


def apply_residual_calibration(
    base_predictions: np.ndarray,
    residual_adjustment: np.ndarray,
) -> np.ndarray:
    """Apply residual SEK adjustments and keep predictions non-negative."""
    return np.clip(
        np.asarray(base_predictions, dtype=float) + np.asarray(residual_adjustment, dtype=float),
        0,
        None,
    )


def apply_calibration_correction(
    base_predictions: np.ndarray,
    correction: np.ndarray,
    *,
    max_abs: float = 1_000_000.0,
    max_frac: float = 0.12,
    min_base_prediction: float = 0.0,
) -> np.ndarray:
    """Apply a clipped residual correction, keeping predictions non-negative.

    Each correction is limited to +/- ``max_abs`` SEK and to +/- ``max_frac`` of the
    base prediction, whichever is tighter, so calibration can never swing a
    prediction wildly. Corrections are only applied where the base prediction is at
    least ``min_base_prediction`` (the tiered model is already well-calibrated in the
    mid-market; the bias worth correcting sits in the high-end tail). The final
    prediction is floored at zero.
    """
    base = np.asarray(base_predictions, dtype=float)
    delta = np.asarray(correction, dtype=float)
    cap = np.minimum(float(max_abs), float(max_frac) * np.abs(base))
    clipped = np.clip(delta, -cap, cap)
    if min_base_prediction > 0:
        clipped = np.where(base >= float(min_base_prediction), clipped, 0.0)
    return np.clip(base + clipped, 0, None)


def _feature_set_requires_listing_price(feature_set: str | None) -> bool:
    subset_numeric, _ = load_feature_subset(feature_set)
    if subset_numeric is None:
        return True
    return "listing_price" in subset_numeric


def _prepare_model_data(
    train_raw: pd.DataFrame,
    test_raw: pd.DataFrame,
    feature_set: str,
) -> PreparedModelData:
    # Mask ask-price signals before feature engineering, exactly as production
    # training does — otherwise engineered features leak listing-price signal into
    # the no-list experiment metrics.
    if not _feature_set_requires_listing_price(feature_set):
        train_raw = mask_ask_price_signals(train_raw)
        test_raw = mask_ask_price_signals(test_raw)
    train_engineered = create_optimized_features(train_raw)
    feature_context = build_feature_context(train_engineered)
    test_engineered = create_optimized_features(test_raw, context=feature_context)
    combined = pd.concat([train_engineered, test_engineered], ignore_index=True)
    numeric_features, categorical_features = _resolve_features(combined, feature_set)
    return PreparedModelData(
        train_engineered=train_engineered,
        test_engineered=test_engineered,
        numeric_features=numeric_features,
        categorical_features=categorical_features,
        all_features=numeric_features + categorical_features,
    )


def _resolve_features(
    df_engineered: pd.DataFrame,
    feature_set: str,
) -> tuple[list[str], list[str]]:
    numeric_features, categorical_features, _ = get_feature_lists()
    subset_numeric, subset_categorical = load_feature_subset(feature_set)
    if subset_numeric is not None:
        numeric_features = [
            feature for feature in subset_numeric if feature in df_engineered.columns
        ]
        categorical_features = [
            feature for feature in (subset_categorical or []) if feature in df_engineered.columns
        ]
    return numeric_features, categorical_features


def _fit_base_model(
    prepared: PreparedModelData,
    random_state: int,
    lgbm_params: dict[str, Any] | None = None,
) -> BaseFitResult:
    X_train, X_test, y_train, _ = _prepare_matrices(prepared)
    model = _train_lgbm(
        X_train,
        y_train,
        prepared.categorical_features,
        random_state,
        lgbm_params=lgbm_params,
    )
    predictions = np.expm1(model.predict(X_test))
    return BaseFitResult(
        model=model,
        predictions=predictions,
        test_frame=prepared.test_engineered.reset_index(drop=True),
    )


def _prepare_matrices(
    prepared: PreparedModelData,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    X_train_raw = prepared.train_engineered[prepared.all_features].copy()
    X_test_raw = prepared.test_engineered[prepared.all_features].copy()
    y_train = prepared.train_engineered["sold_price"].copy()
    y_test = prepared.test_engineered["sold_price"].copy()

    X_train, X_test, _, _ = handle_missing_values(
        X_train_raw,
        X_test_raw,
        prepared.numeric_features,
        prepared.categorical_features,
    )

    return X_train, X_test, y_train, y_test


def _train_lgbm(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    categorical_features: list[str],
    random_state: int,
    *,
    lgbm_params: dict[str, Any] | None = None,
) -> LGBMRegressor:
    trainer = LGBMTrainer(random_state=random_state)
    categorical_indices = get_categorical_indices(X_train, categorical_features)
    return trainer.train(
        X_train,
        np.log1p(y_train),
        hyperparameter_tuning=False,
        categorical_indices=categorical_indices,
        parameters=lgbm_params,
    )


def _build_oof_residual_training_data(
    train_raw: pd.DataFrame,
    *,
    feature_set: str,
    n_splits: int,
    random_state: int,
) -> pd.DataFrame:
    sorted_train = train_raw.sort_values("sold_date").reset_index(drop=True)
    splitter = TimeSeriesSplit(n_splits=n_splits)
    rows = []

    for fold, (fold_train_idx, fold_valid_idx) in enumerate(splitter.split(sorted_train), start=1):
        fold_train_raw = sorted_train.iloc[fold_train_idx].reset_index(drop=True)
        fold_valid_raw = sorted_train.iloc[fold_valid_idx].reset_index(drop=True)
        prepared = _prepare_model_data(fold_train_raw, fold_valid_raw, feature_set)
        fit = _fit_base_model(prepared, random_state)
        fold_features = build_calibration_features(
            fit.test_frame,
            fit.predictions,
        )
        fold_features["residual"] = (
            prepared.test_engineered["sold_price"].reset_index(drop=True).to_numpy()
            - fit.predictions
        )
        fold_features["actual_price"] = prepared.test_engineered["sold_price"].reset_index(
            drop=True
        )
        fold_features["fold"] = fold
        rows.append(fold_features)

    return pd.concat(rows, ignore_index=True)


def _fit_residual_calibrator(oof: pd.DataFrame, *, random_state: int) -> Pipeline:
    X = oof[CALIBRATION_NUMERIC_FEATURES + CALIBRATION_CATEGORICAL_FEATURES].copy()
    y = oof["residual"].copy()
    pipeline = Pipeline(
        steps=[
            (
                "preprocess",
                ColumnTransformer(
                    transformers=[
                        (
                            "numeric",
                            Pipeline(steps=[("imputer", SimpleImputer(strategy="median"))]),
                            CALIBRATION_NUMERIC_FEATURES,
                        ),
                        (
                            "categorical",
                            Pipeline(
                                steps=[
                                    (
                                        "imputer",
                                        SimpleImputer(strategy="constant", fill_value="unknown"),
                                    ),
                                    ("onehot", _one_hot_encoder()),
                                ]
                            ),
                            CALIBRATION_CATEGORICAL_FEATURES,
                        ),
                    ],
                    remainder="drop",
                ),
            ),
            (
                "model",
                HistGradientBoostingRegressor(
                    loss="absolute_error",
                    learning_rate=0.05,
                    max_iter=220,
                    max_leaf_nodes=15,
                    l2_regularization=0.1,
                    random_state=random_state,
                ),
            ),
        ]
    )
    pipeline.fit(X, y)
    return pipeline


def _one_hot_encoder() -> OneHotEncoder:
    return OneHotEncoder(handle_unknown="ignore", sparse_output=False)


def _prediction_metrics(y_true: pd.Series, y_pred: np.ndarray) -> dict[str, float]:
    """regression_metrics's mae/rmse/mape/median_ape/within_X_pct, plus the
    signed-bias fields the calibration gate needs (mean/median bias,
    underprediction rate). Delegates the core computation instead of
    reimplementing it, so the two can't quietly drift out of sync again.
    """
    error = pd.Series(np.asarray(y_pred, dtype=float) - y_true.to_numpy(), index=y_true.index)
    metrics = regression_metrics(y_true, y_pred)
    metrics.update(
        {
            "mean_bias": float(error.mean()),
            "median_bias": float(error.median()),
            "underprediction_rate": float((error < 0).mean() * 100),
        }
    )
    return metrics
