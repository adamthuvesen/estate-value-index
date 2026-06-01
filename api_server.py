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
from uuid import uuid4

import joblib
import pandas as pd
import uvicorn
from cachetools import TTLCache
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from estate_value_index.ml.preprocessing import normalize_area_for_model
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

DEFAULT_PREFIX = "price_prediction_model"
MODELS_DIR = Path("web/models")

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

    if not MODEL_CACHE:
        logger.error("No models loaded; the server will return errors.")
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
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit exceeded. Max {RATE_LIMIT_REQUESTS} requests per "
                f"{RATE_LIMIT_WINDOW} seconds."
            ),
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

    listing_price: float = Field(..., description="Property listing price in SEK")
    living_area: float = Field(..., description="Living area in square meters")
    rooms: float = Field(default=2, description="Number of rooms")
    monthly_fee: float = Field(default=3000, description="Monthly fee in SEK")
    days_on_market: float = Field(default=30, description="Days property has been on market")
    construction_year: int = Field(default=1970, description="Year property was constructed")
    municipality: str = Field(default="Stockholm", description="Municipality name")
    property_type: str = Field(default="Lägenhet", description="Property type")
    area: str = Field(default="Södermalm", description="Area/neighborhood name")
    model: str = Field(default="lgbm", description="Model type to use")
    floor: float | None = Field(default=None, description="Floor number")
    elevator: bool | None = Field(default=None, description="Has elevator")
    balcony: bool | None = Field(default=None, description="Has balcony")


class PredictionResponse(BaseModel):
    """Prediction response payload."""

    predicted_price: float
    model_used: str
    model_type: str
    status: str = "success"


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    models_loaded: list[str]
    models_count: int


def _available_models(models_dir: Path) -> dict[str, Path]:
    """Find available model files.

    Prefers the canonical ``{DEFAULT_PREFIX}_{suffix}.joblib`` produced by the
    training pipeline; falls back to the alphabetically-first timestamped
    artefact for that suffix.
    """
    mapping: dict[str, Path] = {}
    for suffix in ("lgbm", "xgb", "linear"):
        production_path = models_dir / f"{DEFAULT_PREFIX}_{suffix}.joblib"
        if production_path.exists():
            mapping[suffix] = production_path
            continue

        for path in sorted(models_dir.glob(f"*_{suffix}.joblib")):
            mapping[suffix] = path
            break
    return mapping


def _download_models_from_gcs(models_dir: Path) -> None:
    """Download required model files from GCS into ``models_dir`` (no-op when disabled)."""
    if not GCS_AVAILABLE or not is_gcs_enabled():
        return

    try:
        gcs_client = GCSClient()
        models_dir.mkdir(parents=True, exist_ok=True)

        required_models = [
            "models/price_prediction_model_lgbm.joblib",
            "models/price_prediction_model_feature_context.json",
            "models/price_prediction_model_metrics_lgbm.json",
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
    if not MODEL_CACHE:
        raise HTTPException(status_code=503, detail="No models loaded")

    return HealthResponse(
        status="healthy", models_loaded=list(MODEL_CACHE.keys()), models_count=len(MODEL_CACHE)
    )


@app.post("/predict", response_model=PredictionResponse)
async def predict(request: PredictionRequest):
    """Predict a Swedish property price. Feature engineering happens inside the pipeline."""
    if not MODEL_CACHE:
        raise HTTPException(status_code=503, detail="No models loaded. Server is not ready.")

    try:
        model_type = request.model.lower()
        if model_type not in MODEL_CACHE:
            if "lgbm" in MODEL_CACHE:
                model_type = "lgbm"
            else:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        f"Requested model '{request.model}' not available and default "
                        "model 'lgbm' not found"
                    ),
                )

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
            model_type=model_type,
            status="success",
        )

    except HTTPException:
        raise
    except Exception as e:
        _raise_internal_error("Prediction failed", e)


@app.get("/diagnostics/area-sensitivity")
async def area_sensitivity_check():
    """Compare predictions for identical apartments in two areas to gauge area sensitivity."""
    try:
        if "lgbm" not in MODEL_CACHE:
            raise HTTPException(status_code=503, detail="Model not loaded")

        entry = MODEL_CACHE["lgbm"]
        pipeline = entry.get("model")
        if pipeline is None:
            raise HTTPException(status_code=503, detail="Model pipeline not available")

        base_case = {
            "living_area": 60,
            "rooms": 2,
            "monthly_fee": 3000,
            "construction_year": 1960,
            "has_elevator": "yes",
            "has_balcony": "yes",
            "floor": 3,
            "days_on_market": 20,
        }
        test_cases = [
            {**base_case, "area": "Östermalm", "listing_price": 7000000},
            {**base_case, "area": "Sundbyberg", "listing_price": 5200000},
        ]

        predictions: dict[str, float] = {}
        for case in test_cases:
            area_display = case["area"]
            row = {
                **{k: v for k, v in case.items() if k != "area"},
                "area": normalize_area_for_model(area_display),
            }
            pred_arr = await asyncio.to_thread(pipeline.predict, pd.DataFrame([row]))
            predictions[area_display] = float(pred_arr[0])

        expected_diff = 1_800_000
        actual_diff = predictions["Östermalm"] - predictions["Sundbyberg"]
        sensitivity_pct = (actual_diff / expected_diff) * 100

        return {
            "test": "area_sensitivity",
            "predictions": predictions,
            "expected_difference_sek": expected_diff,
            "actual_difference_sek": int(actual_diff),
            "sensitivity_percent": round(sensitivity_pct, 1),
            "status": "pass" if sensitivity_pct >= 80.0 else "fail",
            "threshold_percent": 80.0,
        }
    except HTTPException:
        raise
    except Exception as e:
        _raise_internal_error("Diagnostics failed", e)


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Swedish Real Estate Price Prediction API",
        "version": "1.0.0",
        "endpoints": {
            "health": "GET /health - Health check",
            "predict": "POST /predict - Make price prediction",
            "diagnostics": "GET /diagnostics/area-sensitivity - Model area sensitivity check",
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
