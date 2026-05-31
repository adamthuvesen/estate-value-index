#!/usr/bin/env python3
"""CLI entry point for property price model training."""

from __future__ import annotations

import argparse
from pathlib import Path

from estate_value_index.ml.training_workflow import TrainingConfig, run_training


def main(
    hyperparameter_tuning: bool = False,
    *,
    data_file: str | Path | None = None,
    data_source: str = "json",
    use_materialized_features: bool = False,
    model_dir: str | Path | None = None,
    metrics_prefix: str | None = None,
    importance_threshold: float | None = None,
    production_mode: bool = False,
    config_file: str | None = None,
    feature_set: str | None = None,
) -> float:
    """Train models; returns holdout MAE."""
    return run_training(
        TrainingConfig(
            hyperparameter_tuning=hyperparameter_tuning,
            data_file=data_file,
            data_source=data_source,
            use_materialized_features=use_materialized_features,
            model_dir=model_dir,
            metrics_prefix=metrics_prefix,
            importance_threshold=importance_threshold,
            production_mode=production_mode,
            config_file=config_file,
            feature_set=feature_set,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train property price prediction models")
    parser.add_argument(
        "--tune",
        action="store_true",
        help="Enable hyperparameter tuning (slower but potentially better performance)",
    )
    parser.add_argument(
        "--data-source",
        type=str,
        choices=["json", "bigquery"],
        default="json",
        help="Data source: 'json' for local/GCS files, 'bigquery' for BigQuery tables.",
    )
    parser.add_argument(
        "--use-features",
        action="store_true",
        help="Load pre-computed features from booli_features.engineered_features.",
    )
    parser.add_argument(
        "--data-file",
        type=str,
        default=None,
        help="Path to the training dataset (JSON or JSONL). Overrides BOOLI_TRAIN_DATA.",
    )
    parser.add_argument(
        "--model-dir",
        type=str,
        default=None,
        help="Directory to write trained model artifacts. Overrides BOOLI_MODEL_OUTPUT.",
    )
    parser.add_argument(
        "--model-prefix",
        type=str,
        default=None,
        help="Filename prefix for saved models/metrics. Overrides BOOLI_MODEL_PREFIX.",
    )
    parser.add_argument(
        "--importance-threshold",
        type=float,
        default=None,
        help="Drop features whose LGBM normalized importance is at or below this value.",
    )
    parser.add_argument(
        "--production-mode",
        action="store_true",
        help="After temporal evaluation, retrain on ALL data for production deployment.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to YAML configuration file (default: config/pipeline_config.yaml)",
    )
    parser.add_argument(
        "--feature-set",
        type=str,
        default=None,
        choices=["top_10", "top_20", "top_30", "full"],
        help="Feature subset to use (from config/feature_subsets.yaml).",
    )
    args = parser.parse_args()

    main(
        hyperparameter_tuning=args.tune,
        data_source=args.data_source,
        use_materialized_features=args.use_features,
        data_file=args.data_file,
        model_dir=args.model_dir,
        metrics_prefix=args.model_prefix,
        importance_threshold=args.importance_threshold,
        production_mode=args.production_mode,
        config_file=args.config,
        feature_set=args.feature_set,
    )
