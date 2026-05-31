"""Tests for model artefact integrity verification in api_server.

Covers:
  - happy path: matching sidecar permits load
  - mismatch: corrupted bytes refuse load
  - missing sidecar: refuses load
  - load loop: only valid pair makes it into the cache
  - load failure: unreadable artefacts are skipped, not cached
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import joblib
import pytest

import api_server


def _write_artifact(tmp_path: Path, name: str, payload: object) -> Path:
    """Persist *payload* via joblib and return the resulting file path."""
    artefact_path = tmp_path / name
    joblib.dump(payload, artefact_path)
    return artefact_path


def _write_sidecar(artefact_path: Path, digest: str | None = None) -> Path:
    """Write a `<artefact>.sha256` sidecar; default to the artefact's true digest."""
    if digest is None:
        digest = hashlib.sha256(artefact_path.read_bytes()).hexdigest()
    sidecar = artefact_path.with_suffix(artefact_path.suffix + ".sha256")
    sidecar.write_text(f"{digest}  {artefact_path.name}\n", encoding="utf-8")
    return sidecar


# ---------------------------------------------------------------------------
# _verify_model_integrity
# ---------------------------------------------------------------------------


def test_verify_integrity_happy_path(tmp_path: Path) -> None:
    artefact = _write_artifact(tmp_path, "model.joblib", {"hello": "world"})
    _write_sidecar(artefact)

    digest = api_server._verify_model_integrity(artefact)

    assert digest == hashlib.sha256(artefact.read_bytes()).hexdigest()


def test_verify_integrity_mismatch_raises(tmp_path: Path) -> None:
    artefact = _write_artifact(tmp_path, "model.joblib", {"hello": "world"})
    _write_sidecar(artefact, digest="0" * 64)

    with pytest.raises(RuntimeError, match="integrity mismatch"):
        api_server._verify_model_integrity(artefact)


def test_verify_integrity_missing_sidecar_raises(tmp_path: Path) -> None:
    artefact = _write_artifact(tmp_path, "model.joblib", {"hello": "world"})
    # No sidecar written.

    with pytest.raises(RuntimeError, match="missing sidecar"):
        api_server._verify_model_integrity(artefact)


def test_verify_integrity_empty_sidecar_raises(tmp_path: Path) -> None:
    artefact = _write_artifact(tmp_path, "model.joblib", {"hello": "world"})
    sidecar = artefact.with_suffix(artefact.suffix + ".sha256")
    sidecar.write_text("", encoding="utf-8")

    with pytest.raises(RuntimeError, match="empty sidecar|missing sidecar"):
        api_server._verify_model_integrity(artefact)


# ---------------------------------------------------------------------------
# load_all_models load loop
# ---------------------------------------------------------------------------


def _build_model_dir_with_two_artifacts(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create a models dir with one valid lgbm artefact and one tampered xgb artefact."""
    models_dir = tmp_path / "models"
    models_dir.mkdir()

    valid = _write_artifact(
        models_dir,
        "price_prediction_model_lgbm.joblib",
        {"kind": "lgbm", "value": 1},
    )
    _write_sidecar(valid)

    bad = _write_artifact(
        models_dir,
        "price_prediction_model_xgb.joblib",
        {"kind": "xgb", "value": 2},
    )
    # Sidecar with wrong digest -> load must skip this artefact.
    _write_sidecar(bad, digest="0" * 64)

    return models_dir, valid, bad


def test_load_all_models_skips_mismatched_artifact(tmp_path: Path, monkeypatch) -> None:
    models_dir, valid, bad = _build_model_dir_with_two_artifacts(tmp_path)

    # Avoid touching real GCS during loading.
    monkeypatch.setattr(api_server, "_download_models_from_gcs", lambda _dir: None)

    cache = api_server.load_all_models(models_dir)

    assert "lgbm" in cache
    assert cache["lgbm"]["path"] == valid
    assert "xgb" not in cache, "tampered artefact must not be cached"


def test_load_all_models_skips_missing_sidecar(tmp_path: Path, monkeypatch) -> None:
    models_dir = tmp_path / "models"
    models_dir.mkdir()

    artefact = _write_artifact(
        models_dir,
        "price_prediction_model_lgbm.joblib",
        {"kind": "lgbm"},
    )
    # No sidecar at all.

    monkeypatch.setattr(api_server, "_download_models_from_gcs", lambda _dir: None)

    cache = api_server.load_all_models(models_dir)

    assert cache == {}, "artefact without sidecar must not be loaded"
    assert artefact.exists(), "artefact file should still exist on disk"


def test_load_all_models_skips_artifacts_that_fail_to_load(tmp_path: Path, monkeypatch) -> None:
    """A joblib.load failure must skip the artifact, not surface a broken model."""
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    artefact = _write_artifact(models_dir, "price_prediction_model_lgbm.joblib", {})
    _write_sidecar(artefact)

    monkeypatch.setattr(api_server, "_download_models_from_gcs", lambda _dir: None)

    def _raise(*_args, **_kwargs):
        raise ModuleNotFoundError("Can't get attribute 'SomeClass'")

    monkeypatch.setattr(api_server.joblib, "load", _raise)

    cache = api_server.load_all_models(models_dir)

    assert cache == {}, "load must skip artifacts that fail to deserialize"
