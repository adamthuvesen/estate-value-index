"""Google Cloud Storage utilities for data and model management."""

import hashlib
import json
import logging
import os
import posixpath
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from estate_value_index.exceptions import ConfigurationError
from estate_value_index.utils.settings import is_gcs_enabled

logger = logging.getLogger(__name__)


def compute_sha256(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    """Lowercase hex SHA256 digest of a file's bytes."""
    path = Path(path)
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def write_sha256_sidecar(artefact_path: str | Path) -> Path:
    """Write a ``<artefact>.sha256`` sidecar in ``sha256sum`` format."""
    artefact_path = Path(artefact_path)
    digest = compute_sha256(artefact_path)
    sidecar = artefact_path.with_suffix(artefact_path.suffix + ".sha256")
    sidecar.write_text(f"{digest}  {artefact_path.name}\n", encoding="utf-8")
    return sidecar


def get_gcs_bucket() -> str:
    """Return the configured GCS bucket name, raising if it is unset."""
    bucket = os.getenv("GCS_BUCKET")
    if not bucket:
        raise ConfigurationError("GCS_BUCKET is not set; required when GCS is enabled.")
    return bucket


class GCSClient:
    """Wrapper for Google Cloud Storage operations with local fallback."""

    def __init__(self, bucket_name: str | None = None):
        self.enabled = is_gcs_enabled()
        self.bucket_name = bucket_name
        self._client = None
        self._bucket = None

        if self.enabled:
            # Resolve the bucket only when GCS is actually used, so disabled
            # (local-fallback) runs never require GCS_BUCKET to be set.
            self.bucket_name = bucket_name or get_gcs_bucket()
            try:
                from estate_value_index.utils.clients import get_storage_client

                self._client = get_storage_client()
                self._bucket = self._client.bucket(self.bucket_name)
            except ImportError as exc:
                raise ImportError(
                    "google-cloud-storage is required for GCS support. "
                    "Install with: pip install google-cloud-storage"
                ) from exc
            except Exception as exc:
                raise RuntimeError(f"Failed to initialize GCS client: {exc}") from exc

    def upload_file(self, local_path: str | Path, gcs_path: str) -> str:
        """Upload a local file to GCS. Returns the GCS URI (or the local path when disabled)."""
        local_path = Path(local_path)
        if not self.enabled:
            return str(local_path)

        blob = self._bucket.blob(gcs_path)
        blob.upload_from_filename(str(local_path))
        gcs_uri = f"gs://{self.bucket_name}/{gcs_path}"
        logger.info("Uploaded %s to %s", local_path, gcs_uri)
        return gcs_uri

    def download_file(self, gcs_path: str, local_path: str | Path) -> Path:
        """Download a file from GCS. When disabled, returns the local path if it exists."""
        local_path = Path(local_path)
        if not self.enabled:
            if not local_path.exists():
                raise FileNotFoundError(f"Local file not found: {local_path}")
            return local_path

        local_path.parent.mkdir(parents=True, exist_ok=True)
        blob = self._bucket.blob(gcs_path)
        blob.download_to_filename(str(local_path))
        logger.info("Downloaded gs://%s/%s to %s", self.bucket_name, gcs_path, local_path)
        return local_path

    def upload_json(self, data: dict, gcs_path: str) -> str:
        """Upload a dict as JSON; when disabled, write to a temp file and return its path."""
        if not self.enabled:
            temp_file = Path(tempfile.gettempdir()) / Path(gcs_path).name
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return str(temp_file)

        blob = self._bucket.blob(gcs_path)
        blob.upload_from_string(
            json.dumps(data, indent=2, ensure_ascii=False), content_type="application/json"
        )
        gcs_uri = f"gs://{self.bucket_name}/{gcs_path}"
        logger.info("Uploaded JSON to %s", gcs_uri)
        return gcs_uri

    def download_json(self, gcs_path: str) -> dict:
        """Download and parse JSON from GCS, falling back to a local path when disabled."""
        if not self.enabled:
            local_path = Path(gcs_path)
            if not local_path.exists():
                local_path = Path("data") / gcs_path
            with open(local_path, encoding="utf-8") as f:
                return json.load(f)

        blob = self._bucket.blob(gcs_path)
        return json.loads(blob.download_as_text())

    def exists(self, gcs_path: str) -> bool:
        if not self.enabled:
            return Path(gcs_path).exists()
        return self._bucket.blob(gcs_path).exists()

    def list_files(self, prefix: str = "") -> list[str]:
        """List files under ``prefix``; when disabled, list local files under that dir."""
        if not self.enabled:
            local_dir = Path(prefix) if prefix else Path(".")
            if local_dir.is_dir():
                return [str(p) for p in local_dir.rglob("*") if p.is_file()]
            return []

        blobs = self._client.list_blobs(self.bucket_name, prefix=prefix)
        return [blob.name for blob in blobs]


def resolve_data_path(
    default_local: str | Path, gcs_path: str | None = None, auto_download: bool = True
) -> Path:
    """Resolve a data path: download from GCS when enabled, otherwise use the local file."""
    default_local = Path(default_local)

    if not is_gcs_enabled():
        return default_local

    gcs_path = gcs_path or str(default_local)
    client = GCSClient()

    if not auto_download:
        return default_local

    if not client.exists(gcs_path):
        raise FileNotFoundError(f"File not found in GCS: gs://{client.bucket_name}/{gcs_path}")

    return client.download_file(gcs_path, default_local)


def upload_blob(
    bucket_name: str,
    source_file_name: str,
    destination_blob_name: str,
) -> None:
    """Upload a file to a GCS bucket using a fresh client."""
    from estate_value_index.utils.clients import get_storage_client

    bucket = get_storage_client().bucket(bucket_name)
    bucket.blob(destination_blob_name).upload_from_filename(source_file_name)


def upload_html_to_gcs(
    html_content: str,
    bucket_name: str,
    destination_blob_name: str,
) -> None:
    """Upload an HTML string to a GCS bucket as ``text/html``."""
    from estate_value_index.utils.clients import get_storage_client

    bucket = get_storage_client().bucket(bucket_name)
    bucket.blob(destination_blob_name).upload_from_string(html_content, content_type="text/html")


def _resolve_model_artifact_destination(gcs_prefix: str) -> tuple[str | None, str]:
    env_artifacts_uri = os.getenv("MODEL_ARTIFACTS_URI", "").strip()
    env_artifacts_prefix = os.getenv("MODEL_ARTIFACTS_PREFIX", "").strip()

    resolved_bucket: str | None = None
    resolved_prefix = gcs_prefix.strip("/")

    if env_artifacts_uri:
        parsed = urlparse(env_artifacts_uri)
        if parsed.scheme == "gs" and parsed.netloc:
            resolved_bucket = parsed.netloc
            resolved_prefix = parsed.path.lstrip("/")
        else:
            resolved_prefix = env_artifacts_uri.strip("/")
    elif env_artifacts_prefix:
        resolved_prefix = env_artifacts_prefix.strip("/")

    return resolved_bucket, resolved_prefix


def _destination_path(resolved_prefix: str, filename: str) -> str:
    return posixpath.join(resolved_prefix, filename) if resolved_prefix else filename


def _rollback_partial_upload(client: GCSClient, artefact_dest: str) -> None:
    if not client.enabled:
        return
    try:
        client._bucket.blob(artefact_dest).delete()
    except Exception as cleanup_exc:  # pragma: no cover - best-effort
        logger.warning(
            "Failed to roll back partial upload %s: %s",
            artefact_dest,
            cleanup_exc,
        )


def _upload_joblib_with_sidecar(
    client: GCSClient,
    local_file: Path,
    key: str,
    resolved_prefix: str,
    artifacts: dict[str, str],
) -> None:
    sidecar_path = write_sha256_sidecar(local_file)
    sidecar_dest = _destination_path(resolved_prefix, sidecar_path.name)
    artefact_dest = _destination_path(resolved_prefix, local_file.name)

    uploaded_artefact_uri: str | None = None
    try:
        uploaded_artefact_uri = client.upload_file(local_file, artefact_dest)
        client.upload_file(sidecar_path, sidecar_dest)
    except Exception:
        if uploaded_artefact_uri is not None:
            _rollback_partial_upload(client, artefact_dest)
        raise

    artifacts[key] = uploaded_artefact_uri
    artifacts[f"{key}_sha256"] = f"gs://{client.bucket_name}/{sidecar_dest}"


def _upload_json_model_artifacts(
    client: GCSClient,
    model_dir: Path,
    model_prefix: str,
    resolved_prefix: str,
    artifacts: dict[str, str],
) -> None:
    for key, suffix in (
        ("context", "_feature_context.json"),
        ("metrics", "_metrics.json"),
        ("importance", "_feature_importance.json"),
    ):
        path = model_dir / f"{model_prefix}{suffix}"
        if path.exists():
            artifacts[key] = client.upload_file(path, _destination_path(resolved_prefix, path.name))


def upload_model_artifacts(
    model_dir: str | Path, model_prefix: str, gcs_prefix: str = "models"
) -> dict[str, str]:
    """Upload model artifacts to GCS, returning a map of ``{kind: gs:// URI}``."""
    model_dir = Path(model_dir)

    if not is_gcs_enabled():
        logger.info("GCS disabled, skipping upload")
        return {}

    resolved_bucket, resolved_prefix = _resolve_model_artifact_destination(gcs_prefix)

    try:
        client = GCSClient(bucket_name=resolved_bucket)
        artifacts: dict[str, str] = {}

        model_file = model_dir / f"{model_prefix}.joblib"
        if not model_file.exists():
            raise FileNotFoundError(f"Model artifact not found: {model_file}")

        _upload_joblib_with_sidecar(client, model_file, "model", resolved_prefix, artifacts)
        _upload_json_model_artifacts(client, model_dir, model_prefix, resolved_prefix, artifacts)

        return artifacts

    except Exception as e:
        logger.error("GCS upload failed: %s", e)
        raise RuntimeError("GCS model artifact upload failed") from e
