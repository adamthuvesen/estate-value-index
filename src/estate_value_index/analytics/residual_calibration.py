"""Residual calibration experiments for no-list-price model variants."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, mean_squared_error
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from estate_value_index.ml import (
    build_feature_context,
    create_optimized_features,
    create_temporal_holdout_split,
    filter_valid_listings,
    get_categorical_indices,
    get_feature_lists,
    handle_missing_values,
)
from estate_value_index.ml.training import LGBMTrainer
from estate_value_index.ml.training_workflow.data import (
    load_feature_subset,
    load_training_dataframe,
)
from estate_value_index.utils.settings import get_random_state, get_test_size

CENTRAL_AREAS = frozenset({"ostermalm", "vasastan", "sodermalm", "kungsholmen"})
DEFAULT_DATA_FILE = Path(
    "data/raw/booli/backfill_full_unfiltered_20260706_36areas/all_dedup_apartments_enriched.jsonl"
)
DEFAULT_OUTPUT_DIR = Path("reports/calibration_experiments")

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


def run_residual_calibration_experiment(
    *,
    data_file: Path | None = None,
    feature_set: str = "no_list_price_h3_market",
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    n_splits: int = 4,
    random_state: int | None = None,
) -> dict[str, object]:
    """Run a temporal residual calibration experiment and write JSON/Markdown outputs."""
    if n_splits < 2:
        raise ValueError("n_splits must be at least 2")

    seed = get_random_state() if random_state is None else random_state
    raw_train, raw_test = _load_temporal_raw_split(data_file, feature_set)
    prepared = _prepare_model_data(raw_train, raw_test, feature_set)

    base_fit = _fit_base_model(prepared, seed)
    oof = _build_oof_residual_training_data(
        raw_train,
        feature_set=feature_set,
        n_splits=n_splits,
        random_state=seed,
    )
    calibrator = _fit_residual_calibrator(oof, random_state=seed)

    test_calibration_features = build_calibration_features(
        base_fit.test_frame,
        base_fit.predictions,
    )
    residual_adjustment = calibrator.predict(test_calibration_features)
    calibrated_predictions = np.clip(base_fit.predictions + residual_adjustment, 0, None)

    result = _build_result_payload(
        feature_set=feature_set,
        data_file=data_file or DEFAULT_DATA_FILE,
        raw_train=raw_train,
        raw_test=raw_test,
        base_predictions=base_fit.predictions,
        calibrated_predictions=calibrated_predictions,
        residual_adjustment=residual_adjustment,
        test_frame=base_fit.test_frame,
        oof=oof,
        n_splits=n_splits,
    )
    _write_outputs(result, output_dir)
    return result


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

    area = frame["area"].astype("string") if "area" in frame.columns else pd.Series(pd.NA, index=frame.index)
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


def _load_temporal_raw_split(
    data_file: Path | None,
    feature_set: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df_or_engineered, skip_feature_engineering = load_training_dataframe(
        use_materialized_features=False,
        data_source="json",
        data_file=data_file or DEFAULT_DATA_FILE,
    )
    if skip_feature_engineering:
        raise ValueError("Residual calibration requires raw listings, not materialized features.")

    df_filtered = filter_valid_listings(
        df_or_engineered,
        min_price=3_000_000,
        drop_na_features=False,
        require_listing_price=_feature_set_requires_listing_price(feature_set),
    )
    df_filtered = df_filtered.copy()
    df_filtered["sold_date"] = pd.to_datetime(df_filtered["sold_date"], errors="coerce")
    df_filtered = df_filtered.loc[df_filtered["sold_date"].notna()].reset_index(drop=True)

    return create_temporal_holdout_split(
        df_filtered,
        test_size=get_test_size(),
        date_column="sold_date",
    )


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
        numeric_features = [feature for feature in subset_numeric if feature in df_engineered.columns]
        categorical_features = [
            feature for feature in (subset_categorical or []) if feature in df_engineered.columns
        ]
    return numeric_features, categorical_features


def _fit_base_model(
    prepared: PreparedModelData,
    random_state: int,
) -> BaseFitResult:
    X_train, X_test, y_train, _ = _prepare_matrices(prepared)
    model = _train_lgbm(X_train, y_train, prepared.categorical_features, random_state)
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
    for column in prepared.categorical_features:
        if column in X_train.columns and X_train[column].dtype == "object":
            X_train[column] = X_train[column].astype("category")
        if column in X_test.columns and X_test[column].dtype == "object":
            X_test[column] = X_test[column].astype("category")

    return X_train, X_test, y_train, y_test


def _train_lgbm(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    categorical_features: list[str],
    random_state: int,
) -> LGBMRegressor:
    trainer = LGBMTrainer(random_state=random_state)
    categorical_indices = get_categorical_indices(X_train, categorical_features)
    return trainer.train(
        X_train,
        np.log1p(y_train),
        hyperparameter_tuning=False,
        categorical_indices=categorical_indices,
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
        fold_features["actual_price"] = prepared.test_engineered["sold_price"].reset_index(drop=True)
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
                            Pipeline(
                                steps=[("imputer", SimpleImputer(strategy="median"))]
                            ),
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
    try:
        return OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:
        return OneHotEncoder(handle_unknown="ignore", sparse=False)


def _build_result_payload(
    *,
    feature_set: str,
    data_file: Path,
    raw_train: pd.DataFrame,
    raw_test: pd.DataFrame,
    base_predictions: np.ndarray,
    calibrated_predictions: np.ndarray,
    residual_adjustment: np.ndarray,
    test_frame: pd.DataFrame,
    oof: pd.DataFrame,
    n_splits: int,
) -> dict[str, object]:
    y_test = test_frame["sold_price"].reset_index(drop=True)
    diagnostic_frame = test_frame.copy().reset_index(drop=True)
    diagnostic_frame["base_prediction"] = base_predictions
    diagnostic_frame["calibrated_prediction"] = calibrated_predictions
    diagnostic_frame["base_error"] = base_predictions - y_test
    diagnostic_frame["calibrated_error"] = calibrated_predictions - y_test
    diagnostic_frame["residual_adjustment"] = residual_adjustment
    diagnostic_frame["sold_month"] = pd.to_datetime(diagnostic_frame["sold_date"]).dt.to_period("M").astype(str)
    diagnostic_frame["price_band"] = diagnostic_frame["sold_price"].apply(_price_band)
    diagnostic_frame["central_area"] = diagnostic_frame["area"].isin(CENTRAL_AREAS)

    return {
        "metadata": {
            "feature_set": feature_set,
            "data_file": str(data_file),
            "train_rows": int(len(raw_train)),
            "test_rows": int(len(raw_test)),
            "test_start": str(raw_test["sold_date"].min().date()),
            "test_end": str(raw_test["sold_date"].max().date()),
            "oof_rows": int(len(oof)),
            "oof_splits": n_splits,
            "calibration_numeric_features": CALIBRATION_NUMERIC_FEATURES,
            "calibration_categorical_features": CALIBRATION_CATEGORICAL_FEATURES,
        },
        "base": _prediction_metrics(y_test, base_predictions),
        "calibrated": _prediction_metrics(y_test, calibrated_predictions),
        "delta": _metric_delta(y_test, base_predictions, calibrated_predictions),
        "residual_adjustment": _series_summary(pd.Series(residual_adjustment)),
        "by_price_band": _compare_groups(diagnostic_frame, "price_band"),
        "by_month": _compare_groups(diagnostic_frame, "sold_month"),
        "by_central_area": _compare_groups(diagnostic_frame, "central_area"),
        "worst_base_bias_areas": _compare_groups(diagnostic_frame, "area", min_rows=30)[:12],
    }


def _prediction_metrics(y_true: pd.Series, y_pred: np.ndarray) -> dict[str, float]:
    error = pd.Series(np.asarray(y_pred, dtype=float) - y_true.to_numpy(), index=y_true.index)
    abs_pct = (error.abs() / y_true).replace([np.inf, -np.inf], np.nan)
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "mape": float(mean_absolute_percentage_error(y_true, y_pred)),
        "within_10_pct": float((abs_pct <= 0.10).mean() * 100),
        "mean_bias": float(error.mean()),
        "median_bias": float(error.median()),
        "underprediction_rate": float((error < 0).mean() * 100),
    }


def _metric_delta(
    y_true: pd.Series,
    base_predictions: np.ndarray,
    calibrated_predictions: np.ndarray,
) -> dict[str, float]:
    base = _prediction_metrics(y_true, base_predictions)
    calibrated = _prediction_metrics(y_true, calibrated_predictions)
    return {
        "mae": calibrated["mae"] - base["mae"],
        "rmse": calibrated["rmse"] - base["rmse"],
        "mape": calibrated["mape"] - base["mape"],
        "within_10_pct": calibrated["within_10_pct"] - base["within_10_pct"],
        "mean_bias": calibrated["mean_bias"] - base["mean_bias"],
        "underprediction_rate": calibrated["underprediction_rate"]
        - base["underprediction_rate"],
    }


def _series_summary(values: pd.Series) -> dict[str, float]:
    return {
        "mean": float(values.mean()),
        "median": float(values.median()),
        "p10": float(values.quantile(0.10)),
        "p90": float(values.quantile(0.90)),
    }


def _compare_groups(
    frame: pd.DataFrame,
    column: str,
    *,
    min_rows: int = 1,
) -> list[dict[str, object]]:
    rows = []
    for segment, group in frame.groupby(column, dropna=False, sort=True):
        if len(group) < min_rows:
            continue
        base = _prediction_metrics(group["sold_price"], group["base_prediction"].to_numpy())
        calibrated = _prediction_metrics(
            group["sold_price"], group["calibrated_prediction"].to_numpy()
        )
        rows.append(
            {
                "segment": str(segment),
                "rows": int(len(group)),
                "base_mae": base["mae"],
                "calibrated_mae": calibrated["mae"],
                "mae_delta": calibrated["mae"] - base["mae"],
                "base_bias": base["mean_bias"],
                "calibrated_bias": calibrated["mean_bias"],
                "bias_delta": calibrated["mean_bias"] - base["mean_bias"],
                "base_underprediction_rate": base["underprediction_rate"],
                "calibrated_underprediction_rate": calibrated["underprediction_rate"],
            }
        )
    return sorted(rows, key=lambda row: row["base_bias"])


def _price_band(value: float) -> str:
    if value < 4_000_000:
        return "<4M"
    if value < 6_000_000:
        return "4-6M"
    if value < 8_000_000:
        return "6-8M"
    if value < 12_000_000:
        return "8-12M"
    return "12M+"


def _write_outputs(result: dict[str, object], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    feature_set = str(result["metadata"]["feature_set"])
    json_path = output_dir / f"{feature_set}_residual_calibration.json"
    markdown_path = output_dir / f"{feature_set}_residual_calibration.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown_path.write_text(_to_markdown(result), encoding="utf-8")


def _to_markdown(result: dict[str, object]) -> str:
    metadata = result["metadata"]
    lines = [
        f"# Residual Calibration Experiment: `{metadata['feature_set']}`",
        "",
        f"Data: `{metadata['data_file']}`",
        f"Split: {metadata['train_rows']:,} train / {metadata['test_rows']:,} test, "
        f"{metadata['test_start']} to {metadata['test_end']}",
        f"OOF residual training rows: {metadata['oof_rows']:,} across {metadata['oof_splits']} splits",
        "",
        "## Headline",
        _metrics_table(result),
        "",
        "## Segment Deltas",
        "Negative MAE delta is good. Positive bias delta means predictions moved upward.",
        "",
        "### Price Bands",
        _group_table(result["by_price_band"]),
        "",
        "### Months",
        _group_table(result["by_month"]),
        "",
        "### Central Areas",
        _group_table(result["by_central_area"]),
        "",
        "### Worst Base Bias Areas",
        _group_table(result["worst_base_bias_areas"]),
        "",
    ]
    return "\n".join(lines)


def _metrics_table(result: dict[str, object]) -> str:
    rows = [
        ("Base", result["base"]),
        ("Calibrated", result["calibrated"]),
        ("Delta", result["delta"]),
    ]
    lines = [
        "| Model | MAE | MAPE | Within 10% | Mean bias | Underpredicted |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for label, metrics in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    label,
                    _fmt_sek(metrics["mae"]),
                    _fmt_pct(metrics["mape"] * 100 if label != "Delta" else metrics["mape"] * 100),
                    _fmt_pct(metrics["within_10_pct"]),
                    _fmt_sek(metrics["mean_bias"]),
                    _fmt_pct(metrics["underprediction_rate"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _group_table(rows: list[dict[str, object]]) -> str:
    lines = [
        "| Segment | Rows | Base MAE | Cal MAE | MAE delta | Base bias | Cal bias | Bias delta | Base under | Cal under |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["segment"]),
                    str(row["rows"]),
                    _fmt_sek(row["base_mae"]),
                    _fmt_sek(row["calibrated_mae"]),
                    _fmt_sek(row["mae_delta"]),
                    _fmt_sek(row["base_bias"]),
                    _fmt_sek(row["calibrated_bias"]),
                    _fmt_sek(row["bias_delta"]),
                    _fmt_pct(row["base_underprediction_rate"]),
                    _fmt_pct(row["calibrated_underprediction_rate"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _fmt_sek(value: object) -> str:
    return f"{float(value):,.0f}"


def _fmt_pct(value: object) -> str:
    return f"{float(value):.2f}%"
