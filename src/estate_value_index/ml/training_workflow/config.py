"""Training configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class TrainingConfig:
    """Parameters for a full training run."""

    hyperparameter_tuning: bool = False
    data_file: str | Path | None = None
    data_source: str = "json"
    use_materialized_features: bool = False
    model_dir: str | Path | None = None
    metrics_prefix: str | None = None
    importance_threshold: float | None = None
    production_mode: bool = False
    config_file: str | None = None
    feature_set: str | None = None
