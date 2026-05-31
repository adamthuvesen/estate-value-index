"""Custom exception hierarchy for Estate Value Index.

Hierarchy:
    EstateValueIndexError (base)
    ├── ConfigurationError
    ├── DataError {DataValidationError, DataLoadError, DataQualityError}
    ├── ModelError {ModelValidationError, ModelTrainingError, ModelLoadError}
    ├── PipelineError {ScrapingError, ProcessingError, DeploymentError}
    └── InfrastructureError {BigQueryError, GCSError, VertexAIError}
"""

from typing import Any


class EstateValueIndexError(Exception):
    """Base exception with optional structured ``context`` dict for debugging."""

    def __init__(self, message: str, context: dict[str, Any] | None = None):
        self.message = message
        self.context = context or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            return f"{self.message} (context: {context_str})"
        return self.message


# Configuration


class ConfigurationError(EstateValueIndexError):
    """Configuration is invalid or missing (env vars, YAML, parameter combos)."""


# Data


class DataError(EstateValueIndexError):
    """Base class for data-related errors."""


class DataValidationError(DataError):
    """Data failed validation (range, types, required fields, null thresholds)."""


class DataLoadError(DataError):
    """Loading data failed (missing file, BigQuery error, malformed input)."""


class DataQualityError(DataError):
    """Data is too sparse or noisy for downstream use."""


# Model


class ModelError(EstateValueIndexError):
    """Base class for model-related errors."""


class ModelValidationError(ModelError):
    """Model failed performance validation (MAE/R²/area sensitivity)."""


class ModelTrainingError(ModelError):
    """Training failed (Optuna error, OOM, numerical instability, timeout)."""


class ModelLoadError(ModelError):
    """Loading or deserializing a model failed."""


# Pipeline


class PipelineError(EstateValueIndexError):
    """Base class for pipeline orchestration errors."""


class ScrapingError(PipelineError):
    """Web scraping failed (HTML changed, rate limited, timeout, parse error)."""


class ProcessingError(PipelineError):
    """Data processing step failed (area cleaning, imputation, merging, materialization)."""


class DeploymentError(PipelineError):
    """Deployment failed (Cloud Run rollout, health check, artifact upload)."""


# Infrastructure


class InfrastructureError(EstateValueIndexError):
    """Base class for GCP infrastructure errors."""


class BigQueryError(InfrastructureError):
    """BigQuery operation failed."""


class GCSError(InfrastructureError):
    """GCS operation failed."""


class VertexAIError(InfrastructureError):
    """Vertex AI operation failed."""


def exception_context(operation: str, **kwargs: Any) -> dict[str, Any]:
    """Build a standardized exception context dict (``operation`` + extras)."""
    return {"operation": operation, **kwargs}
