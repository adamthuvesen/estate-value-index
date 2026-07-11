"""Custom exception hierarchy for Estate Value Index.

Hierarchy:
    EstateValueIndexError (base)
    ├── ConfigurationError
    ├── DataError {DataValidationError, DataLoadError}
    ├── ModelError {ModelValidationError}
    ├── PipelineError
    └── InfrastructureError {BigQueryError}
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


# Model


class ModelError(EstateValueIndexError):
    """Base class for model-related errors."""


class ModelValidationError(ModelError):
    """Model failed performance validation (MAE/R²/area sensitivity)."""


# Pipeline


class PipelineError(EstateValueIndexError):
    """Base class for pipeline orchestration errors."""


# Infrastructure


class InfrastructureError(EstateValueIndexError):
    """Base class for GCP infrastructure errors."""


class BigQueryError(InfrastructureError):
    """BigQuery operation failed."""


def exception_context(operation: str, **kwargs: Any) -> dict[str, Any]:
    """Build a standardized exception context dict (``operation`` + extras)."""
    return {"operation": operation, **kwargs}
