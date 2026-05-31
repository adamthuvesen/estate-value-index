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
def test_predict_500_hides_exception_message(caplog: pytest.LogCaptureFixture) -> None:
    mock_model = MagicMock()
    mock_model.predict.side_effect = ValueError("SECRET_INTERNAL_DO_NOT_LEAK")

    with caplog.at_level(logging.ERROR), TestClient(api_server.app) as client:
        api_server.MODEL_CACHE.clear()
        api_server.MODEL_CACHE["lgbm"] = {
            "model": mock_model,
            "path": Path("dummy.joblib"),
        }

        response = client.post(
            "/predict",
            json={
                "listing_price": 5_000_000.0,
                "living_area": 65.0,
                "model": "lgbm",
            },
        )

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert "correlation_id:" in detail
    assert "SECRET_INTERNAL_DO_NOT_LEAK" not in detail

    assert "SECRET_INTERNAL_DO_NOT_LEAK" in caplog.text
    assert "correlation_id" in caplog.text or "[" in caplog.text


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
    api_server.MODEL_CACHE["lgbm"] = {
        "model": mock_model,
        "path": Path("dummy.joblib"),
    }

    body = {"listing_price": 5_000_000.0, "living_area": 65.0, "model": "lgbm"}

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
