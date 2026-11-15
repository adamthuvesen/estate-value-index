"""Data loading helpers for training."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from estate_value_index.ml.data_loader import load_from_bigquery
from estate_value_index.utils.gcs import is_gcs_enabled, resolve_data_path
from estate_value_index.utils.settings import get_settings

logger = logging.getLogger(__name__)


def load_training_dataframe(
    *,
    data_source: str,
    data_file: str | Path | None,
) -> pd.DataFrame:
    """Load raw listings for training from BigQuery or a local file."""
    if data_source.lower() == "bigquery":
        logger.info("Loading data from BigQuery...")
        df = load_from_bigquery()
        logger.info("Loaded %d listings from BigQuery", len(df))
        return df

    default_data_file = Path(
        data_file or get_settings().booli_train_data or "data/raw/booli/booli_listings_prod.json"
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
        with Path(resolved_data_file).open() as f:
            raw_data = json.load(f)
    except json.JSONDecodeError:
        raw_data = []
        with Path(resolved_data_file).open() as f:
            for line in f:
                line = line.strip()
                if line:
                    raw_data.append(json.loads(line))

    df = pd.DataFrame(raw_data)
    logger.info("Loaded %d listings", len(df))
    return df
