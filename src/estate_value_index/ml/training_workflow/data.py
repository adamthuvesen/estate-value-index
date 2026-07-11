"""Data loading helpers for training."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pandas as pd
import yaml

from estate_value_index.ml.data_loader import load_features_from_bigquery, load_from_bigquery
from estate_value_index.ml.features.registry import (
    CATEGORICAL_FEATURE_NAMES,
    NUMERIC_FEATURE_NAMES,
)
from estate_value_index.utils.gcs import is_gcs_enabled, resolve_data_path

logger = logging.getLogger(__name__)


def load_feature_subset(feature_set: str | None) -> tuple[list[str] | None, list[str] | None]:
    """Load and check a named feature subset from config/feature_subsets.yaml."""
    if feature_set == "full":
        return None, None

    config_path = Path("config/feature_subsets.yaml")
    if not config_path.exists():
        raise FileNotFoundError(f"Feature subset config not found: {config_path}")

    with config_path.open(encoding="utf-8") as f:
        config = yaml.safe_load(f)
    if not isinstance(config, dict):
        raise ValueError(f"Feature subset config must be a mapping: {config_path}")

    if feature_set is None:
        feature_set = config.get("default")
        if not isinstance(feature_set, str) or not feature_set:
            raise ValueError(f"Feature subset config has no valid default: {config_path}")
        if feature_set == "full":
            return None, None

    if feature_set not in config:
        available = sorted(key for key in config if key != "default")
        raise ValueError(f"Unknown feature set {feature_set!r}; available: {', '.join(available)}")

    subset = config[feature_set]
    if not isinstance(subset, dict):
        raise ValueError(f"Feature set {feature_set!r} must be a mapping")
    numeric = subset.get("numeric")
    categorical = subset.get("categorical")
    if not isinstance(numeric, list) or not isinstance(categorical, list):
        raise ValueError(f"Feature set {feature_set!r} must define numeric and categorical lists")
    if not all(isinstance(name, str) for name in numeric + categorical):
        raise ValueError(f"Feature set {feature_set!r} must contain feature names only")

    unknown_numeric = sorted(set(numeric) - set(NUMERIC_FEATURE_NAMES))
    unknown_categorical = sorted(set(categorical) - set(CATEGORICAL_FEATURE_NAMES))
    if unknown_numeric or unknown_categorical:
        unknown = unknown_numeric + unknown_categorical
        raise ValueError(
            f"Feature set {feature_set!r} contains unknown features: {', '.join(unknown)}"
        )
    if len(numeric) != len(set(numeric)) or len(categorical) != len(set(categorical)):
        raise ValueError(f"Feature set {feature_set!r} contains duplicate features")

    logger.info(
        "Using feature set '%s': %d numeric, %d categorical",
        feature_set,
        len(numeric),
        len(categorical),
    )

    return numeric, categorical


def load_training_dataframe(
    *,
    use_materialized_features: bool,
    data_source: str,
    data_file: str | Path | None,
) -> tuple[pd.DataFrame, bool]:
    """Load training data and whether feature engineering can be skipped."""
    if use_materialized_features:
        logger.info("Loading pre-computed features from BigQuery...")
        df = load_features_from_bigquery()
        logger.info("Loaded %d rows with pre-computed features", len(df))
        logger.info("Skipped feature engineering step (features already materialized)")
        return df, True

    if data_source.lower() == "bigquery":
        logger.info("Loading data from BigQuery...")
        df = load_from_bigquery()
        logger.info("Loaded %d listings from BigQuery", len(df))
        return df, False

    default_data_file = Path(
        data_file or os.getenv("BOOLI_TRAIN_DATA") or "data/raw/booli/booli_listings_prod.json"
    )
    resolved_data_file = resolve_data_path(
        default_data_file,
        gcs_path="raw/booli_listings_prod.json",
        auto_download=True,
    )

    if is_gcs_enabled():
        logger.info("Using GCS-backed data file: %s", resolved_data_file)
    else:
        logger.info("Using local data file: %s", resolved_data_file)

    if not resolved_data_file.exists():
        raise FileNotFoundError(f"Data file not found: {resolved_data_file}")

    try:
        with open(resolved_data_file) as f:
            raw_data = json.load(f)
    except json.JSONDecodeError:
        raw_data = []
        with open(resolved_data_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    raw_data.append(json.loads(line))

    df = pd.DataFrame(raw_data)
    logger.info("Loaded %d listings", len(df))
    return df, False
