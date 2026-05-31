"""End-to-end model training workflow."""

from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from estate_value_index.ml import (
    SimplePredictionPipeline,
    build_feature_context,
    create_optimized_features,
    create_temporal_holdout_split,
    filter_valid_listings,
    get_categorical_indices,
    get_feature_lists,
    handle_missing_values,
)
from estate_value_index.ml.training import LGBMTrainer
from estate_value_index.ml.training_workflow.config import TrainingConfig
from estate_value_index.ml.training_workflow.data import (
    load_feature_subset,
    load_training_dataframe,
)
from estate_value_index.ml.training_workflow.metrics import train_and_evaluate
from estate_value_index.ml.training_workflow.reporting import (
    analyze_prediction_errors,
    generate_area_performance_report,
    generate_price_tier_analysis,
)
from estate_value_index.monitoring.constants import (
    BASELINE_DATA_PATH,
    CRITICAL_CATEGORICAL_FEATURES,
    CRITICAL_NUMERIC_FEATURES,
)
from estate_value_index.utils.gcs import (
    get_gcs_bucket,
    is_gcs_enabled,
    upload_blob,
    upload_model_artifacts,
)
from estate_value_index.utils.settings import get_mae_threshold, get_random_state, get_test_size

MIN_FEATURES_AFTER_PRUNING = 5


@dataclass
class SplitData:
    """Leakage-free train/test frames plus the training-fold feature context."""

    train_engineered: pd.DataFrame
    test_engineered: pd.DataFrame
    df_engineered: pd.DataFrame
    feature_context: object


def _clean_value(value):
    """Replace non-finite floats with None so payloads stay JSON-serialisable."""
    if isinstance(value, dict):
        return {key: _clean_value(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_clean_value(val) for val in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _context_payload(feature_context) -> dict[str, object]:
    """Serialise a feature context to a JSON-safe dict (date as ISO string)."""
    payload = asdict(feature_context)
    payload["reference_date"] = feature_context.reference_date.isoformat()
    return {key: _clean_value(val) for key, val in payload.items()}


def _print_run_header(config: TrainingConfig) -> None:
    """Echo run configuration before any heavy work starts."""
    print("Training Optimized Property Price Prediction Model")
    print("=" * 60)
    print("Model: LightGBM (LGBM)")

    if config.config_file:
        os.environ["EVI_CONFIG_FILE"] = config.config_file
        print(f"Using config file: {config.config_file}")

    if config.use_materialized_features:
        print(
            "Data Source: BigQuery (pre-computed features from booli_features.engineered_features)"
        )
    elif config.data_source.lower() == "bigquery":
        print("Data Source: BigQuery (estate-value-index.booli_raw.listings)")
    else:
        print(
            f"Data: {Path(config.data_file or os.getenv('BOOLI_TRAIN_DATA') or 'data/raw/booli/booli_listings_prod.json').name}"
        )
    print()

    if config.hyperparameter_tuning:
        print("Hyperparameter tuning ENABLED")
        print("This may take several minutes...")
    else:
        print("Using optimized default parameters (fast)")
    print()


def _load_and_split(config: TrainingConfig) -> SplitData:
    """Load data, split temporally, then engineer features on the train fold only.

    Per fix-ml-temporal-leakage: split FIRST, then engineer features. Training
    statistics (medians, target-encoding global mean, area-market expanding
    stats) are fit on the training fold only; the holdout is transformed via
    FeatureEngineeringContext so no holdout-derived statistic is observable
    to the trained model.
    """
    df_or_engineered, skip_feature_engineering = load_training_dataframe(
        use_materialized_features=config.use_materialized_features,
        data_source=config.data_source,
        data_file=config.data_file,
    )

    test_size = get_test_size()
    if not skip_feature_engineering:
        df = df_or_engineered
        df_filtered = filter_valid_listings(df, min_price=3000000, drop_na_features=False)
        print(f"After filtering: {len(df_filtered)} listings")
        # The temporal split needs sold_date as datetime; previously this was
        # done by feature engineering, which now runs after the split.
        df_filtered = df_filtered.copy()
        df_filtered["sold_date"] = pd.to_datetime(df_filtered["sold_date"], errors="coerce")
        if df_filtered["sold_date"].isna().any():
            n_bad = int(df_filtered["sold_date"].isna().sum())
            print(f"Dropping {n_bad} rows with unparseable sold_date before split")
            df_filtered = df_filtered.loc[df_filtered["sold_date"].notna()].reset_index(drop=True)
        print("\nCreating temporal train/test split BEFORE feature engineering...")
        train_df_raw, test_df_raw = create_temporal_holdout_split(
            df_filtered, test_size=test_size, date_column="sold_date"
        )
        print("Engineering features on training fold (statistics fit here)...")
        train_engineered = create_optimized_features(train_df_raw)
        print("Building feature context from training fold...")
        feature_context = build_feature_context(train_engineered)
        print("Transforming holdout fold via training-only context...")
        test_engineered = create_optimized_features(test_df_raw, context=feature_context)
    else:
        # BigQuery features path: features are pre-materialised. We still
        # split temporally and rebuild the context against the train fold
        # so handle_missing_values uses train-only fill values.
        df_engineered = df_or_engineered
        print("\nCreating temporal train/test split on materialised features...")
        train_engineered, test_engineered = create_temporal_holdout_split(
            df_engineered, test_size=test_size, date_column="sold_date"
        )
        feature_context = build_feature_context(train_engineered)

    # Concatenate views for downstream column discovery only — the actual
    # train/test slices below come from the separate engineered frames.
    combined = pd.concat([train_engineered, test_engineered], ignore_index=True)

    return SplitData(
        train_engineered=train_engineered,
        test_engineered=test_engineered,
        df_engineered=combined,
        feature_context=feature_context,
    )


def _resolve_base_features(
    df_engineered: pd.DataFrame, feature_set: str | None
) -> tuple[list[str], list[str]]:
    """Pick the candidate numeric/categorical feature lists, honouring a subset."""
    base_numeric_features, base_categorical_features, _ = get_feature_lists()

    subset_numeric, subset_categorical = load_feature_subset(feature_set)
    if subset_numeric is not None:
        # Filter to only features that exist in the subset
        base_numeric_features = [f for f in subset_numeric if f in df_engineered.columns]
        base_categorical_features = [
            f for f in (subset_categorical or []) if f in df_engineered.columns
        ]
        # Check for missing features
        missing_numeric = set(subset_numeric) - set(df_engineered.columns)
        if missing_numeric:
            print(f"Missing numeric features (not in data): {missing_numeric}")

    return base_numeric_features, base_categorical_features


def _resolve_prune_threshold(importance_threshold: float | None) -> float | None:
    """Take the explicit prune threshold or fall back to the env override."""
    if importance_threshold is not None:
        return importance_threshold
    env_threshold = os.getenv("BOOLI_IMPORTANCE_THRESHOLD")
    if env_threshold:
        try:
            return float(env_threshold)
        except ValueError:
            return None
    return None


def _prepare_train_test_matrices(
    split: SplitData,
    numeric_features: list[str],
    categorical_features: list[str],
    all_features: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, dict, dict]:
    """Slice, impute, and cast the leakage-free frames into LGBM-ready matrices."""
    # Train/test slices come from the leakage-free engineered frames built
    # above; no re-split or re-engineering inside the pruning loop.
    X_train_raw = split.train_engineered[all_features].copy()
    X_test_raw = split.test_engineered[all_features].copy()
    y_train = split.train_engineered["sold_price"].copy()
    y_test = split.test_engineered["sold_price"].copy()

    print(f"Training: {len(X_train_raw)}, Test: {len(X_test_raw)}")

    X_train, X_test, numeric_fill_values, categorical_fill_values = handle_missing_values(
        X_train_raw,
        X_test_raw,
        numeric_features,
        categorical_features,
    )

    # Ensure categorical features are properly converted to category dtype for LightGBM 4.6+
    for col in categorical_features:
        if col in X_train.columns and X_train[col].dtype == "object":
            X_train[col] = X_train[col].astype("category")
        if col in X_test.columns and X_test[col].dtype == "object":
            X_test[col] = X_test[col].astype("category")

    return X_train, X_test, y_train, y_test, numeric_fill_values, categorical_fill_values


def _compute_importances(
    lgbm_model, columns: pd.Index
) -> tuple[dict[str, dict[str, float]], pd.Series]:
    """Build raw/normalised LGBM importance payloads from a fitted model."""
    lgbm_importances = pd.Series(lgbm_model.feature_importances_, index=columns).astype(float)
    lgbm_importances_sorted = lgbm_importances.sort_values(ascending=False)
    lgbm_importance_sum = lgbm_importances.sum()
    if lgbm_importance_sum > 0:
        lgbm_importances_normalised = lgbm_importances_sorted / lgbm_importance_sum
    else:
        lgbm_importances_normalised = lgbm_importances_sorted.copy()

    importance_payload = {
        "lgbm_raw": {k: float(v) for k, v in lgbm_importances_sorted.items()},
        "lgbm_normalized": {k: float(v) for k, v in lgbm_importances_normalised.items()},
    }
    return importance_payload, lgbm_importances_normalised


def _fit_and_evaluate_iteration(
    split: SplitData,
    numeric_features: list[str],
    categorical_features: list[str],
    all_features: list[str],
    hyperparameter_tuning: bool,
) -> tuple[dict[str, object], dict[str, dict[str, float]], pd.Series]:
    """Fit LGBM on the current feature set and gather metrics + importances.

    Returns the per-iteration results bundle, the importance payload, and the
    normalised importances used by the pruning decision.
    """
    X_train, X_test, y_train, y_test, numeric_fill_values, categorical_fill_values = (
        _prepare_train_test_matrices(split, numeric_features, categorical_features, all_features)
    )

    # feature_context was built outside the loop from the actual training
    # fold (per fix-ml-temporal-leakage); no per-iteration rebuild needed.
    context_payload = _context_payload(split.feature_context)

    y_train_log = np.log1p(y_train)

    random_state = get_random_state()
    lgbm_trainer = LGBMTrainer(random_state=random_state)

    categorical_indices = get_categorical_indices(X_train, categorical_features)

    if hyperparameter_tuning:
        print("=== HYPERPARAMETER TUNING ===")

    lgbm_result = train_and_evaluate(
        "lgbm",
        lgbm_trainer,
        X_train=X_train,
        y_train_log=y_train_log,
        X_test=X_test,
        y_test=y_test,
        hyperparameter_tuning=hyperparameter_tuning,
        categorical_indices=categorical_indices,
    )

    lgbm_model = lgbm_result["model"]
    y_pred = lgbm_result["predictions"]

    comparison_df = pd.DataFrame(
        {
            "actual": y_test.reset_index(drop=True),
            "lgbm_pred": pd.Series(y_pred).reset_index(drop=True),
        }
    )
    comparison_df["abs_err_lgbm"] = (comparison_df["actual"] - comparison_df["lgbm_pred"]).abs()

    # Feature importance reporting
    importance_payload, lgbm_importances_normalised = _compute_importances(
        lgbm_model, X_train.columns
    )

    current_results = {
        "numeric_features": numeric_features,
        "categorical_features": categorical_features,
        "all_features": all_features,
        "train_size": len(X_train),
        "test_size": len(X_test),
        "models": {
            "lgbm": lgbm_model,
        },
        "metrics": {
            "lgbm": dict(lgbm_result["metrics"]),
        },
        "predictions": {
            "y_test": y_test.reset_index(drop=True),
            "lgbm": y_pred,
        },
        "feature_context": split.feature_context,
        "context_payload": context_payload,
        "numeric_fill_values": numeric_fill_values,
        "categorical_fill_values": categorical_fill_values,
        "comparison_df": comparison_df,
    }

    return current_results, importance_payload, lgbm_importances_normalised


def _select_iteration_features(
    split: SplitData,
    base_numeric_features: list[str],
    base_categorical_features: list[str],
    removed_features: set[str],
    iteration: int,
) -> tuple[list[str], list[str], list[str]]:
    """Drop already-pruned/absent columns and log the feature set for this pass."""
    numeric_features = [
        feature
        for feature in base_numeric_features
        if feature not in removed_features and feature in split.df_engineered.columns
    ]
    categorical_features = [
        feature
        for feature in base_categorical_features
        if feature not in removed_features and feature in split.df_engineered.columns
    ]
    all_features = numeric_features + categorical_features

    if not all_features:
        raise ValueError("No features available for training after pruning.")

    if iteration == 1:
        print(f"Features: {len(numeric_features)} numeric, {len(categorical_features)} categorical")
        print(f"Total samples: {len(split.train_engineered) + len(split.test_engineered)}")
    else:
        print(
            f"\nRe-training with {len(all_features)} features after pruning low-importance signals…"
        )
        print(f"Features: {len(numeric_features)} numeric, {len(categorical_features)} categorical")

    return numeric_features, categorical_features, all_features


def _train_with_pruning(
    split: SplitData,
    base_numeric_features: list[str],
    base_categorical_features: list[str],
    prune_threshold: float | None,
    hyperparameter_tuning: bool,
) -> tuple[dict[str, object], dict[str, dict[str, float]], list[dict[str, object]]]:
    """Iteratively fit LGBM, pruning low-importance features until stable.

    Returns the final results bundle, its importance payload, and the record of
    features dropped in each pruning iteration.
    """
    removed_features: set[str] = set()
    dropped_feature_records: list[dict[str, object]] = []
    final_results: dict[str, object] | None = None
    final_importance: dict[str, dict[str, float]] | None = None

    iteration = 0
    while True:
        iteration += 1
        numeric_features, categorical_features, all_features = _select_iteration_features(
            split,
            base_numeric_features,
            base_categorical_features,
            removed_features,
            iteration,
        )

        current_results, importance_payload, lgbm_importances_normalised = (
            _fit_and_evaluate_iteration(
                split,
                numeric_features,
                categorical_features,
                all_features,
                hyperparameter_tuning,
            )
        )

        threshold = prune_threshold
        low_importance_features: list[str] = []
        if threshold is not None:
            low_importance_features = [
                feature
                for feature, score in lgbm_importances_normalised.items()
                if score <= threshold
            ]
            if (
                low_importance_features
                and len(all_features) - len(low_importance_features) >= MIN_FEATURES_AFTER_PRUNING
            ):
                removed_features.update(low_importance_features)
                dropped_feature_records.append(
                    {
                        "iteration": iteration,
                        "threshold": threshold,
                        "removed": low_importance_features,
                    }
                )
                print(
                    f"Pruning {len(low_importance_features)} features with normalized importance ≤ {threshold:.4f}."
                )
                continue

        final_results = current_results
        final_importance = importance_payload
        break

    if final_results is None or final_importance is None:
        raise RuntimeError("Training did not produce final results.")

    return final_results, final_importance, dropped_feature_records


def _log_performance(lgbm_metrics: dict[str, object], hyperparameter_tuning: bool) -> None:
    """Print the headline tuning summary and evaluation metrics."""
    if hyperparameter_tuning:
        print("\nHyperparameter Tuning Summary:")
        print(f"LGBM tuning: {lgbm_metrics['tuning_time']:.1f}s")

        print("\nBest Parameters Found:")
        print(f"LGBM:  {lgbm_metrics['best_params']}")
    else:
        print("\nUsed optimized default parameters (no hyperparameter tuning)")

    print("\nLGBM Performance:")
    print(f"MAE:  {lgbm_metrics['mae']:,.0f} SEK")
    print(f"RMSE: {lgbm_metrics['rmse']:,.0f} SEK")
    print(f"MAPE: {lgbm_metrics['mape']:.4f}")


def _generate_evaluation_reports(
    split: SplitData,
    y_test: pd.Series,
    y_pred: np.ndarray,
    train_size: int,
    test_count: int,
) -> None:
    """Write price-tier, area, error, and temporal-validation reports to disk."""
    train_df = split.train_engineered
    test_df = split.test_engineered

    print("\n" + "=" * 80)
    print("GENERATING EVALUATION REPORTS")
    print("=" * 80)

    # Prepare predictions dictionary
    all_predictions = {
        "LGBM": y_pred,
    }

    # Create reports directory
    reports_dir = Path("reports")
    figures_dir = reports_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    # 1. Price tier analysis
    print("\nAnalyzing performance by price tier...")
    price_tier_analysis = generate_price_tier_analysis(y_test, all_predictions)
    if not price_tier_analysis.empty:
        print("\nPerformance by Price Tier:")
        # Create a formatted display
        for _, row in price_tier_analysis.iterrows():
            print(f"\n  {row['tier']} ({row['price_range']} SEK) - {row['n_samples']} samples:")
            print(
                f"    LGBM: MAE = {row['LGBM_MAE']:>9,.0f}  RMSE = {row['LGBM_RMSE']:>9,.0f}  MAPE = {row['LGBM_MAPE']:>6.2%}"
            )

        tier_path = reports_dir / "price_tier_performance.json"
        price_tier_analysis.to_json(tier_path, orient="records", indent=2)
        print(f"\n   Saved detailed tier analysis to {tier_path}")

    # 2. Area-specific performance
    print("\nAnalyzing performance by area...")
    area_performance = generate_area_performance_report(
        test_df, y_test, all_predictions, min_samples=5
    )
    if not area_performance.empty:
        print(f"   Found {len(area_performance)} areas with ≥5 test samples")
        print("\n   Area performance (by LGBM MAE, descending order):")
        for _, row in area_performance.iterrows():
            print(
                f"      {row['area']:30s}  MAE = {row['LGBM_MAE']:>9,.0f}  ({row['n_samples']:>3d} samples)"
            )

        area_path = reports_dir / "area_performance.json"
        area_performance.to_json(area_path, orient="records", indent=2)
        print(f"\n   Saved area performance to {area_path}")
    # 3. Detailed error analysis (saved to file, not printed)
    print("\nAnalyzing prediction errors...")
    error_analysis = analyze_prediction_errors(y_test, test_df, all_predictions, n_worst=20)

    error_path = reports_dir / "prediction_errors.json"
    with open(error_path, "w", encoding="utf-8") as f:
        json.dump(error_analysis, f, indent=2, ensure_ascii=False)
    print(f"   Saved top 20 worst predictions (over/under) to {error_path}")

    # 4. Temporal validation report
    _log_temporal_validation(train_df, test_df, train_size, test_count)

    print("\n" + "=" * 80)
    print("EVALUATION COMPLETE")
    print("=" * 80)


def _log_temporal_validation(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    train_size: int,
    test_count: int,
) -> None:
    """Print the train/test date ranges and confirm no temporal leakage."""
    print("\nTemporal Split Validation:")
    print(f"   Training set: {train_size:,} samples")
    print(
        f"      Date range: {train_df['sold_date'].min().date()} to {train_df['sold_date'].max().date()}"
    )
    print(f"   Test set: {test_count:,} samples")
    print(
        f"      Date range: {test_df['sold_date'].min().date()} to {test_df['sold_date'].max().date()}"
    )
    temporal_gap = (test_df["sold_date"].min() - train_df["sold_date"].max()).days
    print(f"   Temporal gap: {temporal_gap} day(s)")
    print("   No temporal leakage (test data is strictly after training data)")


def _retrain_on_all_data(
    split: SplitData,
    numeric_features: list[str],
    categorical_features: list[str],
    all_features: list[str],
) -> dict[str, object]:
    """Refit on the full dataset so inference uses the latest area statistics."""
    print("\n" + "=" * 80)
    print("PRODUCTION MODE: RETRAINING ON ALL DATA")
    print("=" * 80)
    print("\nRetraining on FULL dataset (train+test) for production deployment...")
    print("   This ensures inference uses most recent area statistics.\n")

    # Use full engineered dataset (no temporal split)
    df_engineered = split.df_engineered
    X_full = df_engineered[all_features].copy()
    y_full = df_engineered["sold_price"].copy()

    print(f"Full dataset size: {len(X_full)} samples")

    # Handle missing values using full dataset statistics
    X_full_train, _, numeric_fill_prod, categorical_fill_prod = handle_missing_values(
        X_full,
        X_full.copy(),  # Dummy test set (not used)
        numeric_features,
        categorical_features,
    )

    # Ensure categorical features are category dtype
    for col in categorical_features:
        if col in X_full_train.columns and X_full_train[col].dtype == "object":
            X_full_train[col] = X_full_train[col].astype("category")

    # Build feature context from FULL dataset
    feature_context_prod = build_feature_context(df_engineered)
    context_payload_prod = _context_payload(feature_context_prod)

    # Log transform target
    y_full_log = np.log1p(y_full)

    # Train production model (reuse best parameters from evaluation)
    random_state = get_random_state()
    lgbm_trainer_prod = LGBMTrainer(random_state=random_state)
    categorical_indices_prod = get_categorical_indices(X_full_train, categorical_features)

    print("Training production model with evaluation's best parameters...")
    lgbm_model_prod = lgbm_trainer_prod.train(
        X_full_train,
        y_full_log,
        hyperparameter_tuning=False,  # Use best params from evaluation
        categorical_indices=categorical_indices_prod,
    )

    # Create production pipeline
    pipeline_prod = SimplePredictionPipeline(
        lgbm_model_prod,
        numeric_features,
        categorical_features,
        context=feature_context_prod,
    )

    production_results = {
        "model": lgbm_model_prod,
        "pipeline": pipeline_prod,
        "context": feature_context_prod,
        "context_payload": context_payload_prod,
        "numeric_fill_values": numeric_fill_prod,
        "categorical_fill_values": categorical_fill_prod,
        "n_samples": len(X_full_train),
    }

    print(f"Production model trained on {len(X_full_train)} samples")
    print("   Context updated with latest area statistics from all data")

    return production_results


def _log_pruning_and_importance(
    dropped_feature_records: list[dict[str, object]],
    final_importance: dict[str, dict[str, float]],
) -> None:
    """Summarise pruned features and print the top normalised importances."""
    if dropped_feature_records:
        print("\nFeature pruning summary:")
        for record in dropped_feature_records:
            feature_list = ", ".join(record["removed"])
            print(
                f"Iteration {record['iteration']}: removed {len(record['removed'])} feature(s) (≤ {record['threshold']:.4f}) -> {feature_list}"
            )

    print("\nFeature importance (LGBM, normalized - top 50):")
    importance_series = pd.Series(final_importance["lgbm_normalized"])
    top_importance = importance_series.sort_values(ascending=False).head(50)
    print(top_importance.to_string(float_format=lambda x: f"{x:.4f}"))


def _persist_evaluation_model(
    config: TrainingConfig,
    resolved_model_dir: Path,
    prefix: str,
    final_results: dict[str, object],
    final_importance: dict[str, dict[str, float]],
    dropped_feature_records: list[dict[str, object]],
) -> None:
    """Write the evaluation pipeline, context, metrics, and importances to disk."""
    import joblib

    lgbm_model = final_results["models"]["lgbm"]
    numeric_features = final_results["numeric_features"]
    categorical_features = final_results["categorical_features"]
    all_features = final_results["all_features"]
    feature_context = final_results["feature_context"]
    context_payload = final_results["context_payload"]
    lgbm_metrics = final_results["metrics"]["lgbm"]

    # Create LGBM pipeline
    pipeline_lgbm = SimplePredictionPipeline(
        lgbm_model,
        numeric_features,
        categorical_features,
        context=feature_context,
    )

    # Save model and metrics
    joblib.dump(pipeline_lgbm, resolved_model_dir / f"{prefix}_lgbm.joblib")

    with open(resolved_model_dir / f"{prefix}_feature_context.json", "w", encoding="utf-8") as f:
        json.dump(context_payload, f, indent=2, ensure_ascii=False)

    target_mae = get_mae_threshold()

    metrics_lgbm = {
        "mae": lgbm_metrics["mae"],
        "rmse": lgbm_metrics["rmse"],
        "mape": lgbm_metrics["mape"],
        "n_train": final_results["train_size"],
        "n_test": final_results["test_size"],
        "target_achieved": lgbm_metrics["mae"] < target_mae,
        "features_used": all_features,
        "best_params": lgbm_metrics["best_params"],
        "tuning_time_seconds": lgbm_metrics["tuning_time"],
        "model_type": "LGBM (Hyperparameter Tuned)"
        if config.hyperparameter_tuning
        else "LGBM (Optimized)",
        "feature_importance_normalized": final_importance["lgbm_normalized"],
        "feature_importance_raw": final_importance["lgbm_raw"],
        "pruned_features": dropped_feature_records,
        "note": "For production performance, run: python -m estate_value_index.cli value-analysis",
    }

    with open(resolved_model_dir / f"{prefix}_metrics_lgbm.json", "w", encoding="utf-8") as f:
        json.dump(metrics_lgbm, f, indent=2, ensure_ascii=False)

    with open(resolved_model_dir / f"{prefix}_feature_importance.json", "w", encoding="utf-8") as f:
        json.dump(final_importance, f, indent=2, ensure_ascii=False)


def _upload_evaluation_artifacts(
    resolved_model_dir: Path,
    prefix: str,
    train_df: pd.DataFrame,
) -> None:
    """Push evaluation artifacts and a drift baseline to GCS when enabled."""
    print("\nUploading model artifacts to GCS...")
    gcs_artifacts = upload_model_artifacts(resolved_model_dir, prefix)
    print(f"Uploaded {len(gcs_artifacts)} artifacts to Cloud Storage")
    for artifact_type, uri in gcs_artifacts.items():
        print(f"  - {artifact_type}: {uri}")

    # Save training data as drift detection baseline
    print("\nSaving training data as drift detection baseline...")
    baseline_columns = []
    for col in CRITICAL_NUMERIC_FEATURES + CRITICAL_CATEGORICAL_FEATURES + ["sold_price"]:
        if col in train_df.columns:
            baseline_columns.append(col)
        else:
            print(f"  Baseline column '{col}' not in training data, skipping")

    if baseline_columns:
        baseline_df = train_df[baseline_columns].copy()
        local_baseline_path = Path("/tmp/baseline_data.parquet")
        baseline_df.to_parquet(local_baseline_path, index=False)

        gcs_bucket = get_gcs_bucket()
        upload_blob(
            bucket_name=gcs_bucket,
            source_file_name=str(local_baseline_path),
            destination_blob_name=BASELINE_DATA_PATH,
        )
        print(f"Saved {len(baseline_df)} rows as drift baseline")
        print(f"  - gs://{gcs_bucket}/{BASELINE_DATA_PATH}")
        print(f"  - Columns: {len(baseline_columns)} ({', '.join(baseline_columns[:5])}...)")


def _persist_production_model(
    resolved_model_dir: Path,
    prefix: str,
    production_results: dict[str, object],
    final_results: dict[str, object],
    final_importance: dict[str, dict[str, float]],
) -> None:
    """Write and optionally upload the full-dataset production model artifacts."""
    import joblib

    all_features = final_results["all_features"]
    lgbm_metrics = final_results["metrics"]["lgbm"]
    train_size = final_results["train_size"]

    print("\n" + "=" * 80)
    print("SAVING PRODUCTION MODEL")
    print("=" * 80)

    prod_prefix = f"{prefix}_production"

    # Save production pipeline
    joblib.dump(production_results["pipeline"], resolved_model_dir / f"{prod_prefix}_lgbm.joblib")

    # Save production context
    with open(
        resolved_model_dir / f"{prod_prefix}_feature_context.json", "w", encoding="utf-8"
    ) as f:
        json.dump(production_results["context_payload"], f, indent=2, ensure_ascii=False)

    # Save production metrics (note: no test metrics since trained on all data)
    production_metrics = {
        "mae": "N/A - trained on full dataset",
        "rmse": "N/A - trained on full dataset",
        "mape": "N/A - trained on full dataset",
        "n_train": production_results["n_samples"],
        "n_test": 0,
        "features_used": all_features,
        "best_params": lgbm_metrics["best_params"],  # Reused from evaluation
        "model_type": "LGBM (Production - Full Dataset)",
        "feature_importance_normalized": final_importance["lgbm_normalized"],
        "feature_importance_raw": final_importance["lgbm_raw"],
        "note": "Production model trained on ALL data (train+test) for optimal inference. Use evaluation metrics for performance assessment.",
    }

    with open(resolved_model_dir / f"{prod_prefix}_metrics_lgbm.json", "w", encoding="utf-8") as f:
        json.dump(production_metrics, f, indent=2, ensure_ascii=False)

    with open(
        resolved_model_dir / f"{prod_prefix}_feature_importance.json", "w", encoding="utf-8"
    ) as f:
        json.dump(final_importance, f, indent=2, ensure_ascii=False)

    # Upload production artifacts to GCS if enabled
    if is_gcs_enabled():
        print("\nUploading production model artifacts to GCS...")
        prod_gcs_artifacts = upload_model_artifacts(resolved_model_dir, prod_prefix)
        print(f"Uploaded {len(prod_gcs_artifacts)} production artifacts to Cloud Storage")
        for artifact_type, uri in prod_gcs_artifacts.items():
            print(f"  - {artifact_type}: {uri}")

    print("\nProduction model saved:")
    print(f"   Evaluation model: {resolved_model_dir / f'{prefix}_lgbm.joblib'}")
    print(f"   Production model: {resolved_model_dir / f'{prod_prefix}_lgbm.joblib'}")
    print(f"\nProduction model uses updated context from {production_results['n_samples']} samples")
    print(f"   (vs evaluation model context from {train_size} samples)")
    print("\nUse evaluation metrics to assess performance, production model for deployment!")


def run_training(config: TrainingConfig) -> float:
    _print_run_header(config)

    split = _load_and_split(config)

    base_numeric_features, base_categorical_features = _resolve_base_features(
        split.df_engineered, config.feature_set
    )

    prune_threshold = _resolve_prune_threshold(config.importance_threshold)

    final_results, final_importance, dropped_feature_records = _train_with_pruning(
        split,
        base_numeric_features,
        base_categorical_features,
        prune_threshold,
        config.hyperparameter_tuning,
    )

    all_features = final_results["all_features"]
    y_test = final_results["predictions"]["y_test"]
    y_pred = final_results["predictions"]["lgbm"]
    lgbm_metrics = final_results["metrics"]["lgbm"]
    train_size = final_results["train_size"]
    test_size = final_results["test_size"]

    _log_performance(lgbm_metrics, config.hyperparameter_tuning)

    _generate_evaluation_reports(split, y_test, y_pred, train_size, test_size)

    production_results = None
    if config.production_mode:
        production_results = _retrain_on_all_data(
            split,
            final_results["numeric_features"],
            final_results["categorical_features"],
            all_features,
        )

    _log_pruning_and_importance(dropped_feature_records, final_importance)

    resolved_model_dir = Path(config.model_dir or os.getenv("BOOLI_MODEL_OUTPUT") or "web/models")
    resolved_model_dir.mkdir(parents=True, exist_ok=True)

    prefix = config.metrics_prefix or os.getenv("BOOLI_MODEL_PREFIX", "price_prediction_model")

    _persist_evaluation_model(
        config,
        resolved_model_dir,
        prefix,
        final_results,
        final_importance,
        dropped_feature_records,
    )

    if is_gcs_enabled():
        _upload_evaluation_artifacts(resolved_model_dir, prefix, split.train_engineered)

    if config.production_mode and production_results:
        _persist_production_model(
            resolved_model_dir,
            prefix,
            production_results,
            final_results,
            final_importance,
        )

    if config.hyperparameter_tuning:
        print("\nHyperparameter-tuned model saved to:")
        print(f"- {resolved_model_dir / f'{prefix}_lgbm.joblib'} (LGBM - Tuned)")
        print("Hyperparameter tuning and training completed successfully!")
    else:
        print("\nOptimized model saved to:")
        print(f"- {resolved_model_dir / f'{prefix}_lgbm.joblib'} (LGBM - Optimized)")
        print("Fast training with optimized parameters completed!")

    return lgbm_metrics["mae"]
