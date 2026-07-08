"""Unit tests for api_server (rate limit, client IP, error redaction)."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from cachetools import TTLCache
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

import api_server


def _request(
    *,
    client_host: tuple[str, int] | None = ("127.0.0.1", 50000),
    forwarded: str | None = None,
) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if forwarded is not None:
        headers.append((b"x-forwarded-for", forwarded.encode("ascii")))

    scope: dict = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/predict",
        "raw_path": b"/predict",
        "headers": headers,
        "client": client_host,
        "server": ("test", 80),
    }

    async def receive() -> dict:
        return {"type": "http.disconnect"}

    return Request(scope, receive)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("env_trust", "forwarded", "client", "expected"),
    [
        ("false", None, None, "unknown"),
        ("false", "5.6.7.8", None, "unknown"),
        ("true", "5.6.7.8, 9.10.11.12", None, "5.6.7.8"),
        ("true", "5.6.7.8, 9.10.11.12", ("1.2.3.4", 1234), "5.6.7.8"),
        ("false", "5.6.7.8, 9.10.11.12", ("1.2.3.4", 1234), "1.2.3.4"),
    ],
)
def test_resolve_client_ip(
    monkeypatch: pytest.MonkeyPatch,
    env_trust: str,
    forwarded: str | None,
    client: tuple[str, int] | None,
    expected: str,
) -> None:
    monkeypatch.setenv("TRUST_PROXY_HEADERS", env_trust)
    req = _request(client_host=client, forwarded=forwarded)
    assert api_server._resolve_client_ip(req) == expected


@pytest.mark.unit
def test_rate_limit_ttlcache_eviction_prefers_recent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_server, "RATE_LIMIT_STORE", TTLCache(maxsize=3, ttl=3600.0))
    store = api_server.RATE_LIMIT_STORE
    store["a"] = [1.0]
    store["b"] = [1.0]
    store["c"] = [1.0]
    _ = store["a"]
    store["d"] = [1.0]
    assert len(store) == 3
    assert "a" in store


@pytest.mark.unit
def test_rate_limit_store_stays_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_server, "RATE_LIMIT_STORE", TTLCache(maxsize=50, ttl=3600.0))
    store = api_server.RATE_LIMIT_STORE
    now = time.time()
    for i in range(1000):
        store[f"10.{i // 256}.{(i // 16) % 256}.{i % 256}"] = [now]
    assert len(store) <= 50


@pytest.mark.unit
def test_rate_limit_returns_429(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_server, "RATE_LIMIT_REQUESTS", 1)
    monkeypatch.setattr(api_server, "RATE_LIMIT_STORE", TTLCache(maxsize=10, ttl=3600.0))

    with TestClient(api_server.app) as client:
        first = client.get("/docs")
        second = client.get("/docs")

    assert first.status_code == 200
    assert second.status_code == 429
    assert "Rate limit exceeded" in second.json()["detail"]


@pytest.mark.unit
def test_predict_500_hides_exception_message(caplog: pytest.LogCaptureFixture) -> None:
    mock_model = MagicMock()
    mock_model.predict.side_effect = ValueError("SECRET_INTERNAL_DO_NOT_LEAK")

    with caplog.at_level(logging.ERROR), TestClient(api_server.app) as client:
        api_server.MODEL_CACHE.clear()
        api_server.MODEL_CACHE["no_list_price"] = {
            "model": mock_model,
            "path": Path("dummy.joblib"),
            "model_type": "price_tiered_ensemble",
        }

        response = client.post(
            "/predict",
            json={
                "living_area": 65.0,
                "model": "no_list_price",
            },
        )

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert "correlation_id:" in detail
    assert "SECRET_INTERNAL_DO_NOT_LEAK" not in detail

    assert "SECRET_INTERNAL_DO_NOT_LEAK" in caplog.text
    assert "correlation_id" in caplog.text or "[" in caplog.text


@pytest.mark.unit
def test_predict_accepts_optional_coordinates() -> None:
    mock_model = MagicMock()
    mock_model.predict.return_value = [4_500_000.0]

    with TestClient(api_server.app) as client:
        api_server.MODEL_CACHE.clear()
        api_server.MODEL_CACHE["with_list_price"] = {
            "model": mock_model,
            "path": Path("dummy.joblib"),
            "requires_listing_price": True,
            "model_type": "price_tiered_ensemble",
        }

        response = client.post(
            "/predict",
            json={
                "listing_price": 5_000_000.0,
                "living_area": 65.0,
                "latitude": 59.315,
                "longitude": 18.07,
                "model": "with_list_price",
            },
        )

    assert response.status_code == 200
    sent_frame = mock_model.predict.call_args.args[0]
    assert sent_frame["latitude"].iloc[0] == pytest.approx(59.315)
    assert sent_frame["longitude"].iloc[0] == pytest.approx(18.07)


@pytest.mark.unit
@pytest.mark.parametrize(
    "payload",
    [
        {"living_area": -1},
        {"living_area": 55, "latitude": 91},
        {"living_area": 55, "longitude": -181},
        {"living_area": 55, "model": "old_listing"},
        {"living_area": "nan"},
    ],
)
def test_predict_rejects_invalid_request_fields(payload: dict) -> None:
    with TestClient(api_server.app) as client:
        response = client.post("/predict", json=payload)

    assert 400 <= response.status_code < 500


@pytest.mark.unit
def test_predict_auto_routes_to_no_list_without_listing_price() -> None:
    mock_model = MagicMock()
    mock_model.predict.return_value = [4_250_000.0]

    with TestClient(api_server.app) as client:
        api_server.MODEL_CACHE.clear()
        api_server.MODEL_CACHE["no_list_price"] = {
            "model": mock_model,
            "path": Path("price_prediction_model_no_list_price.joblib"),
            "requires_listing_price": False,
            "model_type": "price_tiered_ensemble",
        }

        response = client.post(
            "/predict",
            json={
                "living_area": 65.0,
                "model": "auto",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["model_id"] == "no_list_price"
    assert payload["requires_listing_price"] is False


@pytest.mark.unit
def test_listing_model_requires_listing_price() -> None:
    with TestClient(api_server.app) as client:
        api_server.MODEL_CACHE.clear()
        api_server.MODEL_CACHE["with_list_price"] = {
            "model": MagicMock(),
            "path": Path("price_prediction_model_with_list_price.joblib"),
            "requires_listing_price": True,
            "model_type": "price_tiered_ensemble",
        }

        response = client.post(
            "/predict",
            json={
                "living_area": 65.0,
                "model": "with_list_price",
            },
        )

    assert response.status_code == 400
    assert "requires listing_price" in response.json()["detail"]


@pytest.mark.unit
def test_multi_worker_emits_rate_limit_warning(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    monkeypatch.delenv("RATE_LIMIT_BACKEND", raising=False)
    with TestClient(api_server.app):
        pass
    assert "Multi-worker mode without distributed rate-limit backend" in capsys.readouterr().err


@pytest.mark.unit
def test_health_requires_both_production_models() -> None:
    with TestClient(api_server.app) as client:
        api_server.MODEL_CACHE.clear()
        api_server.MODEL_CACHE["with_list_price"] = {
            "model": MagicMock(),
            "path": Path("price_prediction_model_with_list_price.joblib"),
            "requires_listing_price": True,
            "model_type": "price_tiered_ensemble",
        }

        response = client.get("/health")

    assert response.status_code == 503
    assert "no_list_price" in response.json()["detail"]


@pytest.mark.unit
def test_health_responds_while_predicts_in_flight() -> None:
    release_predict = threading.Event()
    predict_started = threading.Event()
    active_predicts = 0
    lock = threading.Lock()

    def slow_predict(_df):  # noqa: ANN001
        nonlocal active_predicts
        with lock:
            active_predicts += 1
            predict_started.set()
        try:
            release_predict.wait(timeout=1.0)
        finally:
            with lock:
                active_predicts -= 1
        return [4_500_000.0]

    mock_model = MagicMock()
    mock_model.predict.side_effect = slow_predict

    transport = ASGITransport(app=api_server.app)
    api_server.MODEL_CACHE.clear()
    api_server.MODEL_CACHE["with_list_price"] = {
        "model": mock_model,
        "path": Path("dummy.joblib"),
        "requires_listing_price": True,
        "model_type": "price_tiered_ensemble",
    }
    api_server.MODEL_CACHE["no_list_price"] = {
        "model": MagicMock(),
        "path": Path("dummy.joblib"),
        "requires_listing_price": False,
        "model_type": "price_tiered_ensemble",
    }

    body = {"listing_price": 5_000_000.0, "living_area": 65.0, "model": "with_list_price"}

    async def _run() -> None:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            predict_tasks = [
                asyncio.create_task(client.post("/predict", json=body)) for _ in range(10)
            ]
            assert await asyncio.to_thread(predict_started.wait, 1.0)
            health = await client.get("/health")
            with lock:
                predicts_in_flight = active_predicts
            release_predict.set()
            await asyncio.gather(*predict_tasks)

        assert health.status_code == 200
        assert predicts_in_flight > 0

    asyncio.run(_run())
