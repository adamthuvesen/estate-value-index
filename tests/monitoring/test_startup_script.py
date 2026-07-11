from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

from estate_value_index.model_artifacts import (
    LISTING_MODEL_ID,
    NO_LIST_MODEL_ID,
    production_artifact_names,
)


def _write_artifact(model_dir: Path, filename: str, payload: bytes | None = None) -> None:
    payload = payload or filename.encode("utf-8")
    path = model_dir / filename
    path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{digest}  {filename}\n", encoding="utf-8"
    )


def _run_startup(
    tmp_path: Path, model_dir: Path, **env_overrides: str
) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "MODEL_DIR": str(model_dir),
        "ENRICHMENT_DIR": str(tmp_path / "derived"),
        "START_SERVICES": "false",
        "GCS_ENABLED": "false",
        **env_overrides,
    }
    return subprocess.run(
        ["bash", "scripts/startup.sh"],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def test_startup_accepts_local_canonical_models(tmp_path: Path) -> None:
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    _write_artifact(model_dir, production_artifact_names(NO_LIST_MODEL_ID).model)
    _write_artifact(model_dir, production_artifact_names(LISTING_MODEL_ID).model)

    result = _run_startup(tmp_path, model_dir)

    assert result.returncode == 0, result.stderr
    assert "Preflight OK" in result.stdout


def test_startup_rejects_missing_required_model(tmp_path: Path) -> None:
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    _write_artifact(model_dir, production_artifact_names(NO_LIST_MODEL_ID).model)

    result = _run_startup(tmp_path, model_dir)

    assert result.returncode == 1
    assert "with_list_price.joblib: model missing" in result.stderr


def test_startup_rejects_missing_sidecar(tmp_path: Path) -> None:
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    no_list = production_artifact_names(NO_LIST_MODEL_ID).model
    with_list = production_artifact_names(LISTING_MODEL_ID).model
    _write_artifact(model_dir, no_list)
    (model_dir / with_list).write_bytes(b"model")

    result = _run_startup(tmp_path, model_dir)

    assert result.returncode == 1
    assert "with_list_price.joblib: sidecar missing" in result.stderr


def test_startup_requires_bucket_when_gcs_enabled(tmp_path: Path) -> None:
    result = _run_startup(tmp_path, tmp_path / "models", GCS_ENABLED="true", GCS_BUCKET="")

    assert result.returncode == 1
    assert "GCS_BUCKET is required when GCS_ENABLED=true" in result.stderr
