"""FastAPI prediction server with in-memory model caching.

Usage:
    uvicorn api_server:app --host 0.0.0.0 --port 8000
    python api_server.py
"""

import asyncio
import hashlib
import hmac
import logging
import os
import sys
import time
import warnings
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from uuid import uuid4

import joblib
import pandas as pd
import uvicorn
from cachetools import TTLCache
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from estate_value_index.ml.preprocessing import normalize_area_for_model
from estate_value_index.model_artifacts import (
    DEFAULT_MODEL_PREFIX,
    LISTING_MODEL_ID,
    NO_LIST_MODEL_ID,
    production_model_files,
    required_production_artifact_files,
)
from estate_value_index.utils.settings import (
    get_rate_limit_max_ips,
    get_rate_limit_requests,
    get_rate_limit_window_seconds,
    get_web_concurrency,
    is_trust_proxy_headers,
)

logger = logging.getLogger(__name__)
if not logger.handlers and not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

# Silence noisy numpy warnings raised inside feature engineering on empty slices.
warnings.filterwarnings("ignore", category=RuntimeWarning, message="Mean of empty slice")
warnings.filterwarnings("ignore", category=RuntimeWarning, module="numpy")

try:
    from estate_value_index.utils.gcs import GCSClient, is_gcs_enabled

    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False
    logger.warning("GCS utilities not available, running in local mode")

MODELS_DIR = Path("web/models")
AUTO_MODEL = "auto"
NO_LIST_MODEL = NO_LIST_MODEL_ID
LISTING_MODEL = LISTING_MODEL_ID
PRODUCTION_MODEL_FILES = production_model_files(DEFAULT_MODEL_PREFIX)
REQUIRED_MODEL_IDS = frozenset(PRODUCTION_MODEL_FILES)

MODEL_CACHE: dict[str, dict] = {}

# IP-based rate limiting via a bounded TTL cache (per-process; not cross-worker).
RATE_LIMIT_MAX_IPS = get_rate_limit_max_ips()
RATE_LIMIT_REQUESTS = get_rate_limit_requests()
RATE_LIMIT_WINDOW = get_rate_limit_window_seconds()
RATE_LIMIT_STORE: TTLCache[str, list[float]] = TTLCache(
    maxsize=RATE_LIMIT_MAX_IPS,
    ttl=float(RATE_LIMIT_WINDOW),
)


def _resolve_client_ip(request: Request) -> str:
    """Resolve client IP for rate limiting (proxy-aware when explicitly enabled)."""
    forwarded = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")

    # Read each request: tests rely on env-var-only behavior, and the cost is
    # a single dict lookup so caching at startup buys nothing meaningful.
    if is_trust_proxy_headers() and forwarded:
        return forwarded.split(",")[0].strip() or "unknown"

    if request.client is not None and request.client.host:
        return request.client.host

    return "unknown"


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
    global MODEL_CACHE
    logger.info("Startup: TRUST_PROXY_HEADERS=%s", is_trust_proxy_headers())
    web_workers = get_web_concurrency()
    if web_workers > 1 and not os.getenv("RATE_LIMIT_BACKEND"):
        # stderr print mirrors the logger.warning so ops dashboards that grep
        # the boot output (and the corresponding regression test) keep working.
        message = (
            "Multi-worker mode without distributed rate-limit backend; "
            "rate limits will be per-worker."
        )
        logger.warning(message)
        print(f"[WARNING] {message}", file=sys.stderr)

    logger.info("Loading models from %s", MODELS_DIR.absolute())
    MODEL_CACHE = load_all_models(MODELS_DIR)

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Per-IP rate limiting; ``/health`` is exempt so liveness probes never block."""
    if request.url.path == "/health":
        return await call_next(request)

    client_ip = _resolve_client_ip(request)
    current_time = time.time()

    # No async lock around the gate: TTLCache get/set is atomic enough for an
    # advisory rate limit, and per-IP races at most leak a handful of extra
    # requests. A global lock here would serialize every prediction request
    # behind the gate and defeat the point of running async.
    req_list = RATE_LIMIT_STORE.get(client_ip) or []
    req_list = [ts for ts in req_list if current_time - ts < RATE_LIMIT_WINDOW]

    if len(req_list) >= RATE_LIMIT_REQUESTS:
        return JSONResponse(
            status_code=429,
            content={
                "detail": (
                    f"Rate limit exceeded. Max {RATE_LIMIT_REQUESTS} requests per "
                    f"{RATE_LIMIT_WINDOW} seconds."
                )
            },
        )

    req_list.append(current_time)
    RATE_LIMIT_STORE[client_ip] = req_list
    remaining = RATE_LIMIT_REQUESTS - len(req_list)

    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(RATE_LIMIT_REQUESTS)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(int(current_time + RATE_LIMIT_WINDOW))

    return response


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


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    models_loaded: list[str]
    models_count: int


def _available_models(models_dir: Path) -> dict[str, Path]:
    """Find the two production model artifacts."""
    mapping: dict[str, Path] = {}
    for model_id, filename in PRODUCTION_MODEL_FILES.items():
        path = models_dir / filename
        if path.exists():
            mapping[model_id] = path
    return mapping


def _missing_required_models(cache: dict[str, dict]) -> list[str]:
    return sorted(REQUIRED_MODEL_IDS.difference(cache))


def _download_models_from_gcs(models_dir: Path) -> None:
    """Download required model files from GCS into ``models_dir`` (no-op when disabled)."""
    if not GCS_AVAILABLE or not is_gcs_enabled():
        return

    try:
        gcs_client = GCSClient()
        models_dir.mkdir(parents=True, exist_ok=True)

        required_models = [
            f"models/{filename}"
            for filename in required_production_artifact_files(DEFAULT_MODEL_PREFIX)
        ]

        logger.info("Downloading %d required model files from GCS", len(required_models))
        download_start = time.time()

        for gcs_path in required_models:
            filename = Path(gcs_path).name
            local_path = models_dir / filename

            if local_path.exists():
                logger.info("Using cached %s", filename)
                continue

            file_start = time.time()
            gcs_client.download_file(gcs_path, local_path)
            logger.info("Downloaded %s (%.1fs)", filename, time.time() - file_start)

        logger.info("Model download completed in %.1fs", time.time() - download_start)

    except Exception as e:
        logger.error("Failed to download models from GCS: %s", e)


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


def load_all_models(models_dir: Path) -> dict[str, dict]:
    """Load all available models into memory on startup.

    Each artefact must be accompanied by a ``<artefact>.sha256`` sidecar.
    Artefacts that fail integrity verification (or whose sidecar is missing)
    are logged and skipped — they are not added to the cache.
    """
    cache: dict[str, dict] = {}

    _download_models_from_gcs(models_dir)

    available = _available_models(models_dir)
    if not available:
        logger.warning("No models found in %s", models_dir.absolute())
        return cache

    logger.info("Loading %d model(s) into memory", len(available))
    load_start = time.time()

    for model_type, model_path in available.items():
        try:
            digest = _verify_model_integrity(model_path)
        except RuntimeError as exc:
            logger.error("Refusing to load %s (%s): %s", model_type, model_path.name, exc)
            continue

        try:
            model_load_start = time.time()
            model = joblib.load(model_path)
            model_load_duration = time.time() - model_load_start
        except Exception as exc:
            logger.error("Failed to load %s (%s): %s", model_type, model_path.name, exc)
            continue

        cache[model_type] = {
            "model": model,
            "path": model_path,
            "sha256": digest,
            "requires_listing_price": bool(getattr(model, "requires_listing_price", False)),
            "model_type": getattr(model, "model_type", model_type),
        }
        logger.info(
            "Loaded %s model: %s (sha256=%s..., %.1fs)",
            model_type,
            model_path.name,
            digest[:16],
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
        status="healthy", models_loaded=list(MODEL_CACHE.keys()), models_count=len(MODEL_CACHE)
    )


@app.post("/predict", response_model=PredictionResponse)
async def predict(request: PredictionRequest):
    """Predict a Swedish property price. Feature engineering happens inside the pipeline."""
    if not MODEL_CACHE:
        raise HTTPException(status_code=503, detail="No models loaded. Server is not ready.")

    try:
        requested_model = request.model.lower()
        model_type = _resolve_prediction_model(requested_model, request.listing_price)

        cached = MODEL_CACHE[model_type]
        model = cached["model"]
        model_path = cached["path"]

        input_data = request.model_dump(exclude={"model"})

        # Booli-shaped strings and plain names: same path as training (preprocessing).
        if input_data.get("area"):
            area_original = input_data["area"]
            area_normalized = normalize_area_for_model(area_original)
            input_data["area"] = area_normalized
            logger.info("Area normalized for predict: %r -> %r", area_original, area_normalized)

        input_df = pd.DataFrame([input_data])
        if "scraped_at" not in input_df.columns:
            input_df["scraped_at"] = pd.Timestamp.now()

        prediction_arr = await asyncio.to_thread(model.predict, input_df)

        return PredictionResponse(
            predicted_price=float(prediction_arr[0]),
            model_used=model_path.name,
            model_type=str(cached.get("model_type", model_type)),
            model_id=model_type,
            requires_listing_price=bool(cached.get("requires_listing_price", False)),
            status="success",
        )

    except HTTPException:
        raise
    except Exception as e:
        _raise_internal_error("Prediction failed", e)


def _resolve_prediction_model(requested_model: str, listing_price: float | None) -> str:
    has_listing_price = listing_price is not None and listing_price > 0
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
