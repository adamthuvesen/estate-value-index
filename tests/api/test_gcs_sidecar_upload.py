"""Tests for SHA256 sidecar generation in the model-artefact upload helper.

We avoid touching real GCS by patching ``GCSClient`` with a tmp-dir adapter
that mirrors the real upload semantics for the calls the helper makes.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import joblib
import pytest

from src.estate_value_index.utils import gcs as gcs_module


class _FakeBlob:
    def __init__(self, base_dir: Path, name: str) -> None:
        self._base = base_dir
        self.name = name
        self._path = base_dir / name

    def upload_from_filename(self, source: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_bytes(Path(source).read_bytes())

    def upload_from_string(self, contents, content_type=None) -> None:  # noqa: ARG002
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(contents, str):
            self._path.write_text(contents, encoding="utf-8")
        else:
            self._path.write_bytes(contents)

    def delete(self) -> None:
        if self._path.exists():
            self._path.unlink()

    def exists(self) -> bool:
        return self._path.exists()


class _FakeBucket:
    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir

    def blob(self, name: str) -> _FakeBlob:
        return _FakeBlob(self._base, name)


class _FakeGCSClient:
    """Stand-in for :class:`GCSClient` that writes to a tmp directory."""

    def __init__(self, base_dir: Path, bucket_name: str = "fake-bucket") -> None:
        self.enabled = True
        self.bucket_name = bucket_name
        self._base = base_dir
        self._bucket = _FakeBucket(base_dir)

    def upload_file(self, local_path, gcs_path: str) -> str:
        local_path = Path(local_path)
        blob = self._bucket.blob(gcs_path)
        blob.upload_from_filename(str(local_path))
        return f"gs://{self.bucket_name}/{gcs_path}"


@pytest.fixture
def fake_model_dir(tmp_path: Path) -> Path:
    """Lay out the four artefacts that ``upload_model_artifacts`` looks for."""
    prefix = "price_prediction_model_no_list"
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    joblib.dump({"kind": "no_list"}, model_dir / f"{prefix}.joblib")
    (model_dir / f"{prefix}_feature_context.json").write_text("{}", encoding="utf-8")
    (model_dir / f"{prefix}_metrics.json").write_text("{}", encoding="utf-8")
    (model_dir / f"{prefix}_feature_importance.json").write_text("{}", encoding="utf-8")
    return model_dir


def test_upload_writes_sidecar_alongside_joblib(
    fake_model_dir: Path, tmp_path: Path, monkeypatch
) -> None:
    """``.joblib`` upload must also upload a matching ``.joblib.sha256``."""
    bucket_dir = tmp_path / "bucket"
    bucket_dir.mkdir()

    fake_client = _FakeGCSClient(bucket_dir)

    monkeypatch.setattr(gcs_module, "is_gcs_enabled", lambda: True)
    monkeypatch.setattr(gcs_module, "GCSClient", lambda *a, **kw: fake_client)

    artefacts = gcs_module.upload_model_artifacts(fake_model_dir, "price_prediction_model_no_list")

    # Both artefact and sidecar end up in the fake bucket layout.
    uploaded_joblib = bucket_dir / "models" / "price_prediction_model_no_list.joblib"
    uploaded_sidecar = bucket_dir / "models" / "price_prediction_model_no_list.joblib.sha256"

    assert uploaded_joblib.exists(), "model file must be uploaded"
    assert uploaded_sidecar.exists(), "sidecar file must be uploaded"

    # Sidecar contents are valid sha256sum format and match the artefact bytes.
    digest_line = uploaded_sidecar.read_text(encoding="utf-8").strip()
    digest, *_rest = digest_line.split()
    expected = hashlib.sha256(uploaded_joblib.read_bytes()).hexdigest()
    assert digest == expected

    # The returned artefacts mapping references both URIs.
    assert artefacts["model"].endswith("price_prediction_model_no_list.joblib")
    assert artefacts["model_sha256"].endswith("price_prediction_model_no_list.joblib.sha256")


def test_sidecar_upload_failure_rolls_back_artefact(
    fake_model_dir: Path, tmp_path: Path, monkeypatch
) -> None:
    """If the sidecar upload fails, the partial ``.joblib`` upload is removed."""
    bucket_dir = tmp_path / "bucket"
    bucket_dir.mkdir()

    fake_client = _FakeGCSClient(bucket_dir)

    real_upload = fake_client.upload_file

    def upload_with_sidecar_failure(local_path, gcs_path: str) -> str:
        if gcs_path.endswith(".sha256"):
            raise RuntimeError("simulated sidecar upload failure")
        return real_upload(local_path, gcs_path)

    fake_client.upload_file = upload_with_sidecar_failure  # type: ignore[assignment]

    monkeypatch.setattr(gcs_module, "is_gcs_enabled", lambda: True)
    monkeypatch.setattr(gcs_module, "GCSClient", lambda *a, **kw: fake_client)

    # The helper currently swallows GCS exceptions and returns {} on failure.
    result = gcs_module.upload_model_artifacts(fake_model_dir, "price_prediction_model_no_list")

    uploaded_joblib = bucket_dir / "models" / "price_prediction_model_no_list.joblib"
    uploaded_sidecar = bucket_dir / "models" / "price_prediction_model_no_list.joblib.sha256"

    assert not uploaded_joblib.exists(), (
        "partial joblib upload must be rolled back when the sidecar fails"
    )
    assert not uploaded_sidecar.exists()
    # Caller-visible: failure produces an empty mapping; no half-uploaded model leaks.
    assert "model" not in result
    assert "model_sha256" not in result


def test_compute_sha256_matches_hashlib(tmp_path: Path) -> None:
    payload = b"some-bytes" * 100
    p = tmp_path / "blob.bin"
    p.write_bytes(payload)

    assert gcs_module.compute_sha256(p) == hashlib.sha256(payload).hexdigest()


def test_write_sha256_sidecar_format(tmp_path: Path) -> None:
    p = tmp_path / "model.joblib"
    p.write_bytes(b"hello")

    sidecar = gcs_module.write_sha256_sidecar(p)

    assert sidecar.name == "model.joblib.sha256"
    contents = sidecar.read_text(encoding="utf-8").strip()
    digest, basename = contents.split()
    assert digest == hashlib.sha256(b"hello").hexdigest()
    assert basename == "model.joblib"
