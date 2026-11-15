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
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import joblib
import pytest

import api_server
from estate_value_index.model_artifacts import installed_package_version, production_artifact_names

FINGERPRINT = {"rows": 1200, "max_sold_date": "2026-10-31", "sha256": "f" * 64}


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


def _write_metrics(models_dir: Path, model_id: str, **overrides: object) -> None:
    metrics: dict[str, object] = {
        "package_version": installed_package_version(),
        "data_fingerprint": FINGERPRINT,
    }
    metrics.update(overrides)
    path = models_dir / production_artifact_names(model_id).metrics
    path.write_text(json.dumps(metrics), encoding="utf-8")


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

    with pytest.raises(RuntimeError, match=r"empty sidecar|missing sidecar"):
        api_server._verify_model_integrity(artefact)


# ---------------------------------------------------------------------------
# load_all_models load loop
# ---------------------------------------------------------------------------


def _build_model_dir_with_two_artifacts(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create one valid no_list_price artifact and one tampered with_list_price artifact."""
    models_dir = tmp_path / "models"
    models_dir.mkdir()

    valid = _write_artifact(
        models_dir,
        "price_prediction_model_no_list_price.joblib",
        SimpleNamespace(requires_listing_price=False, model_type="price_tiered_ensemble"),
    )
    _write_sidecar(valid)
    _write_metrics(models_dir, "no_list_price")

    bad = _write_artifact(
        models_dir,
        "price_prediction_model_with_list_price.joblib",
        {"kind": "with_list_price", "value": 2},
    )
    # Sidecar with wrong digest -> load must skip this artefact.
    _write_sidecar(bad, digest="0" * 64)

    return models_dir, valid, bad


def test_load_all_models_skips_mismatched_artifact(tmp_path: Path) -> None:
    models_dir, valid, _bad = _build_model_dir_with_two_artifacts(tmp_path)

    cache = api_server.load_all_models(models_dir)

    assert "no_list_price" in cache
    assert cache["no_list_price"]["path"] == valid
    assert "with_list_price" not in cache, "tampered artefact must not be cached"
    assert cache["no_list_price"]["info"].data_fingerprint.rows == 1200


def _valid_no_list_artifact(models_dir: Path) -> None:
    models_dir.mkdir()
    artefact = _write_artifact(
        models_dir,
        "price_prediction_model_no_list_price.joblib",
        SimpleNamespace(requires_listing_price=False, model_type="price_tiered_ensemble"),
    )
    _write_sidecar(artefact)


@pytest.mark.parametrize(
    "overrides", [{"package_version": "0.0.1"}, {"package_version": None}], ids=["old", "none"]
)
def test_load_all_models_refuses_a_different_package_version(
    tmp_path: Path, overrides: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    models_dir = tmp_path / "models"
    _valid_no_list_artifact(models_dir)
    _write_metrics(models_dir, "no_list_price", **overrides)

    assert api_server.load_all_models(models_dir) == {}
    assert "retrain the model" in caplog.text


def test_load_all_models_refuses_a_missing_metrics_artifact(tmp_path: Path) -> None:
    models_dir = tmp_path / "models"
    _valid_no_list_artifact(models_dir)

    assert api_server.load_all_models(models_dir) == {}


def test_invalid_range_factors_fall_back_to_none(tmp_path: Path) -> None:
    models_dir = tmp_path / "models"
    _valid_no_list_artifact(models_dir)
    _write_metrics(models_dir, "no_list_price", estimate_range_factors={"buckets": "bad"})

    cache = api_server.load_all_models(models_dir)
    assert cache["no_list_price"]["estimate_range_factors"] is None


def test_load_all_models_skips_missing_sidecar(tmp_path: Path) -> None:
    models_dir = tmp_path / "models"
    models_dir.mkdir()

    artefact = _write_artifact(
        models_dir,
        "price_prediction_model_no_list_price.joblib",
        {"kind": "no_list_price"},
    )
    # No sidecar at all.

    cache = api_server.load_all_models(models_dir)

    assert cache == {}, "artefact without sidecar must not be loaded"
    assert artefact.exists(), "artefact file should still exist on disk"


def test_load_all_models_skips_artifacts_that_fail_to_load(tmp_path: Path, monkeypatch) -> None:
    """A joblib.load failure must skip the artifact, not surface a broken model."""
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    artefact = _write_artifact(models_dir, "price_prediction_model_no_list_price.joblib", {})
    _write_sidecar(artefact)

    def _raise(*_args, **_kwargs):
        raise ModuleNotFoundError("Can't get attribute 'SomeClass'")

    monkeypatch.setattr(api_server.joblib, "load", _raise)

    cache = api_server.load_all_models(models_dir)

    assert cache == {}, "load must skip artifacts that fail to deserialize"


def test_load_all_models_skips_obsolete_model_contract(tmp_path: Path) -> None:
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    artefact = _write_artifact(
        models_dir,
        "price_prediction_model_no_list_price.joblib",
        {"kind": "obsolete"},
    )
    _write_sidecar(artefact)

    assert api_server.load_all_models(models_dir) == {}
