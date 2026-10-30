"""FastAPI prediction server with in-memory model caching.

Usage:
    uvicorn api_server:app --host 0.0.0.0 --port 8000
    python api_server.py
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
import warnings
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import joblib
import pandas as pd
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, ValidationError

from estate_value_index.areas import normalize_area_for_model
from estate_value_index.ml.data_fingerprint import DataFingerprint
from estate_value_index.ml.estimate_range_factors import EstimateRangeFactors
from estate_value_index.model_artifacts import (
    DEFAULT_MODEL_PREFIX,
    LISTING_MODEL_ID,
    NO_LIST_MODEL_ID,
    installed_package_version,
    production_artifact_names,
    production_model_files,
)

logger = logging.getLogger(__name__)
if not logger.handlers and not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

# Silence noisy numpy warnings raised inside feature engineering on empty slices.
warnings.filterwarnings("ignore", category=RuntimeWarning, message="Mean of empty slice")
warnings.filterwarnings("ignore", category=RuntimeWarning, module="numpy")

MODELS_DIR = Path("web/models")
AUTO_MODEL = "auto"
NO_LIST_MODEL = NO_LIST_MODEL_ID
LISTING_MODEL = LISTING_MODEL_ID
PRODUCTION_MODEL_FILES = production_model_files(DEFAULT_MODEL_PREFIX)
REQUIRED_MODEL_IDS = frozenset(PRODUCTION_MODEL_FILES)

MODEL_CACHE: dict[str, dict[str, Any]] = {}


def _raise_internal_error(context: str, exc: BaseException) -> None:
    """Log full exception server-side; raise opaque 500 to clients."""
    correlation_id = uuid4().hex[:8]
    logger.error("[%s] %s: %s", correlation_id, context, exc, exc_info=True)
    raise HTTPException(
        status_code=500,
        detail=f"{context} (correlation_id: {correlation_id})",
    ) from None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load models on startup, cleanup on shutdown."""
    logger.info("Loading models from %s", MODELS_DIR.absolute())
    MODEL_CACHE.clear()
    MODEL_CACHE.update(load_all_models(MODELS_DIR))

    missing_models = _missing_required_models(MODEL_CACHE)
    if missing_models:
        logger.error("Missing required model(s): %s; the server is not ready.", missing_models)
    else:
        logger.info("Successfully loaded %d models: %s", len(MODEL_CACHE), list(MODEL_CACHE.keys()))
        logger.info("Server ready to accept requests")

    yield

    logger.info("Shutdown: cleaning up")


app = FastAPI(
    title="Swedish Real Estate Price Prediction API",
    description="ML-powered property price predictions for Swedish market",
    version="1.0.0",
    lifespan=lifespan,
)


class PredictionRequest(BaseModel):
    """Prediction request payload."""

    listing_price: float | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
        description="Property listing price in SEK",
    )
    living_area: float = Field(
        ..., gt=0, allow_inf_nan=False, description="Living area in square meters"
    )
    rooms: float = Field(default=2, gt=0, allow_inf_nan=False, description="Number of rooms")
    monthly_fee: float = Field(
        default=3000, ge=0, allow_inf_nan=False, description="Monthly fee in SEK"
    )
    days_on_market: float = Field(
        default=30, ge=0, allow_inf_nan=False, description="Days property has been on market"
    )
    construction_year: int = Field(
        default=1970, ge=1800, le=2100, description="Year property was constructed"
    )
    municipality: str = Field(
        default="Stockholm", min_length=1, max_length=120, description="Municipality name"
    )
    property_type: str = Field(
        default="Lägenhet", min_length=1, max_length=80, description="Property type"
    )
    area: str = Field(
        default="Södermalm", min_length=1, max_length=160, description="Area/neighborhood name"
    )
    model: Literal["auto", "no_list_price", "with_list_price"] = Field(
        default=AUTO_MODEL, description="Model id to use"
    )
    floor: float | None = Field(
        default=None, ge=-20, le=200, allow_inf_nan=False, description="Floor number"
    )
    elevator: bool | None = Field(default=None, description="Has elevator")
    balcony: bool | None = Field(default=None, description="Has balcony")
    latitude: float | None = Field(
        default=None, ge=-90, le=90, allow_inf_nan=False, description="Property latitude"
    )
    longitude: float | None = Field(
        default=None, ge=-180, le=180, allow_inf_nan=False, description="Property longitude"
    )


class PredictionResponse(BaseModel):
    """Prediction response payload."""

    predicted_price: float
    model_used: str
    model_type: str
    model_id: str
    requires_listing_price: bool
    status: str = "success"
    # The request after validation and defaults, so callers see what the model scored.
    input: PredictionRequest
    # Per-bucket q35/q65 factors driving the displayed value window; null when
    # the metrics artifact has no valid estimate_range_factors block.
    estimate_range_factors: EstimateRangeFactors | None = None


class LoadedModelInfo(BaseModel):
    """What a loaded model artifact is: its code version, its bytes, and its training data."""

    package_version: str
    sha256: str
    data_fingerprint: DataFingerprint | None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    models_loaded: list[str]
    models_count: int
    models: dict[str, LoadedModelInfo]


def _available_models(models_dir: Path) -> dict[str, Path]:
    """Find the two production model artifacts."""
    mapping: dict[str, Path] = {}
    for model_id, filename in PRODUCTION_MODEL_FILES.items():
        path = models_dir / filename
        if path.exists():
            mapping[model_id] = path
    return mapping


def _missing_required_models(cache: dict[str, dict[str, Any]]) -> list[str]:
    return sorted(REQUIRED_MODEL_IDS.difference(cache))


def _verify_model_integrity(model_path: Path) -> str:
    """Verify a model artefact's SHA256 against its `<path>.sha256` sidecar.

    Raises ``RuntimeError`` if the sidecar is missing/empty or the digest does
    not match the on-disk bytes. Returns the verified lowercase hex digest on
    success.

    The sidecar is parsed in `sha256sum` format: the first whitespace-delimited
    token is the expected digest; any trailing tokens (filename) are ignored.
    """
    sidecar = model_path.with_suffix(model_path.suffix + ".sha256")
    if not sidecar.exists():
        raise RuntimeError(f"missing sidecar: {sidecar}")

    sidecar_contents = sidecar.read_text(encoding="utf-8").strip()
    if not sidecar_contents:
        raise RuntimeError(f"empty sidecar: {sidecar}")

    expected = sidecar_contents.split()[0].lower()
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise RuntimeError(f"invalid sidecar contents (not a hex SHA256 digest): {sidecar}")

    hasher = hashlib.sha256()
    with model_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    observed = hasher.hexdigest()

    if not hmac.compare_digest(expected, observed):
        raise RuntimeError(
            f"integrity mismatch for {model_path.name}: "
            f"expected {expected[:16]}... got {observed[:16]}..."
        )
    return observed


def _read_metrics(models_dir: Path, model_id: str) -> dict[str, Any]:
    """Read a model's metrics artifact, the metadata written next to the joblib file."""
    metrics_path = models_dir / production_artifact_names(model_id, DEFAULT_MODEL_PREFIX).metrics
    if not metrics_path.exists():
        raise RuntimeError(f"missing metrics artifact: {metrics_path.name}")
    try:
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"unreadable metrics artifact {metrics_path.name}: {exc}") from exc
    if not isinstance(metrics, dict):
        raise RuntimeError(f"metrics artifact {metrics_path.name} is not a JSON object")
    return metrics


def _check_package_version(metrics: dict[str, Any]) -> str:
    """Refuse an artifact trained by a different package version than the one installed."""
    trained = metrics.get("package_version")
    installed = installed_package_version()
    if trained != installed:
        raise RuntimeError(
            f"trained with estate-value-index {trained or '(no version stamp)'}, "
            f"but {installed} is installed; retrain the model with this version"
        )
    return installed


def _estimate_range_factors(metrics: dict[str, Any], model_id: str) -> EstimateRangeFactors | None:
    """Return the typed factors, or None so the web app falls back to its baked factors."""
    raw = metrics.get("estimate_range_factors")
    if raw is None:
        return None
    try:
        return EstimateRangeFactors.model_validate(raw)
    except ValidationError as exc:
        logger.error("Ignoring invalid estimate_range_factors for %s: %s", model_id, exc)
        return None


def _data_fingerprint(metrics: dict[str, Any]) -> DataFingerprint | None:
    raw = metrics.get("data_fingerprint")
    return None if raw is None else DataFingerprint.model_validate(raw)


def load_all_models(models_dir: Path) -> dict[str, dict[str, Any]]:
    """Load all available models into memory on startup.

    Each artefact needs a ``<artefact>.sha256`` sidecar and a metrics artifact whose
    ``package_version`` matches the installed package. Artefacts that fail either
    check are logged and skipped; they are not added to the cache.
    """
    cache: dict[str, dict[str, Any]] = {}

    available = _available_models(models_dir)
    if not available:
        logger.warning("No models found in %s", models_dir.absolute())
        return cache

    logger.info("Loading %d model(s) into memory", len(available))
    load_start = time.time()

    for model_type, model_path in available.items():
        try:
            digest = _verify_model_integrity(model_path)
            metrics = _read_metrics(models_dir, model_type)
            package_version = _check_package_version(metrics)
            data_fingerprint = _data_fingerprint(metrics)
        except (RuntimeError, ValidationError) as exc:
            logger.error("Refusing to load %s (%s): %s", model_type, model_path.name, exc)
            continue

        try:
            model_load_start = time.time()
            model = joblib.load(model_path)
            model_load_duration = time.time() - model_load_start
        except Exception as exc:
            logger.error("Failed to load %s (%s): %s", model_type, model_path.name, exc)
            continue

        try:
            requires_listing_price = model.requires_listing_price
            loaded_model_type = model.model_type
        except AttributeError as exc:
            logger.error(
                "Refusing incompatible %s model (%s): %s", model_type, model_path.name, exc
            )
            continue

        cache[model_type] = {
            "model": model,
            "path": model_path,
            "sha256": digest,
            "requires_listing_price": requires_listing_price,
            "model_type": loaded_model_type,
            "estimate_range_factors": _estimate_range_factors(metrics, model_type),
            "info": LoadedModelInfo(
                package_version=package_version,
                sha256=digest,
                data_fingerprint=data_fingerprint,
            ),
        }
        logger.info(
            "Loaded %s model: %s (sha256=%s..., data=%s, %.1fs)",
            model_type,
            model_path.name,
            digest[:16],
            data_fingerprint.model_dump(mode="json") if data_fingerprint else "no fingerprint",
            model_load_duration,
        )

    logger.info("Model loading completed in %.1fs", time.time() - load_start)
    return cache


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Liveness probe; reports loaded models."""
    missing = _missing_required_models(MODEL_CACHE)
    if missing:
        raise HTTPException(
            status_code=503, detail=f"Missing required models: {', '.join(missing)}"
        )

    return HealthResponse(
        status="healthy",
        models_loaded=list(MODEL_CACHE.keys()),
        models_count=len(MODEL_CACHE),
        models={model_id: cached["info"] for model_id, cached in MODEL_CACHE.items()},
    )


@app.post("/predict", response_model=PredictionResponse)
async def predict(request: PredictionRequest):
    """Predict a Swedish property price. Feature engineering happens inside the pipeline."""
    if not MODEL_CACHE:
        raise HTTPException(status_code=503, detail="No models loaded. Server is not ready.")

    try:
        requested_model = request.model
        model_type = _resolve_prediction_model(requested_model, request.listing_price)

        cached = MODEL_CACHE[model_type]
        model = cached["model"]
        model_path = cached["path"]

        input_data = request.model_dump(exclude={"model"})

        # Booli-shaped strings and plain names: same path as training (preprocessing).
        area_original = input_data["area"]
        area_normalized = normalize_area_for_model(area_original)
        input_data["area"] = area_normalized
        logger.info("Area normalized for predict: %r -> %r", area_original, area_normalized)

        input_df = pd.DataFrame([input_data])
        input_df["scraped_at"] = pd.Timestamp.now()

        prediction_arr = await asyncio.to_thread(model.predict, input_df)

        return PredictionResponse(
            predicted_price=float(prediction_arr[0]),
            model_used=model_path.name,
            model_type=str(cached.get("model_type", model_type)),
            model_id=model_type,
            requires_listing_price=bool(cached.get("requires_listing_price", False)),
            status="success",
            input=request,
            estimate_range_factors=cached.get("estimate_range_factors"),
        )

    except HTTPException:
        raise
    except Exception as e:
        _raise_internal_error("Prediction failed", e)


def _resolve_prediction_model(requested_model: str, listing_price: float | None) -> str:
    has_listing_price = listing_price is not None
    if requested_model == AUTO_MODEL:
        model_type = LISTING_MODEL if has_listing_price else NO_LIST_MODEL
    elif requested_model in {NO_LIST_MODEL, LISTING_MODEL}:
        model_type = requested_model
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model '{requested_model}'. Use auto, no_list_price, or with_list_price.",
        )

    if model_type == LISTING_MODEL and not has_listing_price:
        raise HTTPException(
            status_code=400,
            detail="The with_list_price model requires listing_price.",
        )
    if model_type not in MODEL_CACHE:
        raise HTTPException(status_code=503, detail=f"Model '{model_type}' is not loaded")
    return model_type


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Swedish Real Estate Price Prediction API",
        "version": "1.0.0",
        "endpoints": {
            "health": "GET /health - Health check",
            "predict": "POST /predict - Make price prediction",
        },
        "models_loaded": list(MODEL_CACHE.keys()) if MODEL_CACHE else [],
        "documentation": "/docs",
    }


if __name__ == "__main__":
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=False,
    )
