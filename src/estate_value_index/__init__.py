"""Estate Value Index - Swedish Real Estate ML System.

Architecture: Scraping → BigQuery → Feature Engineering → Training → Deployment
"""

__version__ = "1.0.0"
__author__ = "Estate Value Index Team"

VERSION_INFO = {
    "version": __version__,
    "python_requires": ">=3.11",
    "model_version": "lgbm-v1",
    "feature_count": 91,
}

__all__ = [
    "__version__",
    "VERSION_INFO",
    "load_listings",
    "create_optimized_features",
    "build_feature_context",
    "SimplePredictionPipeline",
    "FeatureEngineeringContext",
    "LGBMTrainer",
    "EstateValueIndexError",
    "DataValidationError",
    "ModelValidationError",
    "PipelineError",
    "ConfigurationError",
]

# Lazy submodule imports — each entry maps an exported name to its submodule path.
_LAZY_ATTRS = {
    "load_listings": "estate_value_index.ml.data_loader",
    "create_optimized_features": "estate_value_index.ml.features",
    "build_feature_context": "estate_value_index.ml.features",
    "SimplePredictionPipeline": "estate_value_index.ml.features",
    "FeatureEngineeringContext": "estate_value_index.ml.features",
    "LGBMTrainer": "estate_value_index.ml.training",
    "EstateValueIndexError": "estate_value_index.exceptions",
    "DataValidationError": "estate_value_index.exceptions",
    "ModelValidationError": "estate_value_index.exceptions",
    "PipelineError": "estate_value_index.exceptions",
    "ConfigurationError": "estate_value_index.exceptions",
}


def __getattr__(name):
    module_path = _LAZY_ATTRS.get(name)
    if module_path is None:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

    import importlib

    return getattr(importlib.import_module(module_path), name)
