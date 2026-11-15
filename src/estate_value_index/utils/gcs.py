"""Google Cloud Storage utilities for data and model management."""

import hashlib
import logging
import posixpath
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from estate_value_index.utils.approval import require_approval
from estate_value_index.utils.settings import get_settings, is_gcs_enabled

if TYPE_CHECKING:
    from estate_value_index.utils.clients import StorageBlob, StorageBucket, StorageClient

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
    return get_settings().require_gcs_bucket()


def split_gcs_uri(uri: str) -> tuple[str, str]:
    """Split ``gs://bucket/prefix`` into ``(bucket, prefix)``; reject anything else."""
    parsed = urlparse(uri)
    if parsed.scheme != "gs" or not parsed.netloc:
        raise ValueError(f"Not a gs:// URI: {uri!r}")
    return parsed.netloc, parsed.path.strip("/")


class GCSClient:
    """Wrapper for Google Cloud Storage operations with local fallback."""

    def __init__(self, bucket_name: str | None = None):
        self.enabled = is_gcs_enabled()
        self.bucket_name = bucket_name
        self._client: StorageClient | None = None
        self._bucket: StorageBucket | None = None

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

    def _blob(self, gcs_path: str) -> StorageBlob:
        if self._bucket is None:
            raise RuntimeError("GCS bucket is not initialised")
        return self._bucket.blob(gcs_path)

    def upload_file(self, local_path: str | Path, gcs_path: str, *, approved: bool = False) -> str:
        """Upload a local file to GCS. Returns the GCS URI (or the local path when disabled)."""
        local_path = Path(local_path)
        if not self.enabled:
            return str(local_path)

        require_approval(f"upload {local_path.name} to GCS", approved)
        blob = self._blob(gcs_path)
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
        blob = self._blob(gcs_path)
        blob.download_to_filename(str(local_path))
        logger.info("Downloaded gs://%s/%s to %s", self.bucket_name, gcs_path, local_path)
        return local_path

    def exists(self, gcs_path: str) -> bool:
        if not self.enabled:
            return Path(gcs_path).exists()
        return self._blob(gcs_path).exists()

    def delete(self, gcs_path: str) -> None:
        self._blob(gcs_path).delete()


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


def _resolve_model_artifact_destination(gcs_prefix: str) -> tuple[str | None, str]:
    settings = get_settings()
    env_artifacts_uri = (settings.model_artifacts_uri or "").strip()
    env_artifacts_prefix = (settings.model_artifacts_prefix or "").strip()

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
        client.delete(artefact_dest)
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
    approved: bool,
) -> None:
    sidecar_path = write_sha256_sidecar(local_file)
    sidecar_dest = _destination_path(resolved_prefix, sidecar_path.name)
    artefact_dest = _destination_path(resolved_prefix, local_file.name)

    uploaded_artefact_uri: str | None = None
    try:
        uploaded_artefact_uri = client.upload_file(local_file, artefact_dest, approved=approved)
        client.upload_file(sidecar_path, sidecar_dest, approved=approved)
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
    approved: bool,
) -> None:
    for key, suffix in (
        ("context", "_feature_context.json"),
        ("metrics", "_metrics.json"),
        ("importance", "_feature_importance.json"),
    ):
        path = model_dir / f"{model_prefix}{suffix}"
        if path.exists():
            artifacts[key] = client.upload_file(
                path, _destination_path(resolved_prefix, path.name), approved=approved
            )


def upload_model_artifacts(
    model_dir: str | Path,
    model_prefix: str,
    gcs_prefix: str = "models",
    *,
    approved: bool = False,
) -> dict[str, str]:
    """Upload model artifacts to GCS, returning a map of ``{kind: gs:// URI}``."""
    model_dir = Path(model_dir)

    if not is_gcs_enabled():
        logger.info("GCS disabled, skipping upload")
        return {}

    require_approval("upload model artifacts to GCS", approved)

    resolved_bucket, resolved_prefix = _resolve_model_artifact_destination(gcs_prefix)

    try:
        client = GCSClient(bucket_name=resolved_bucket)
        artifacts: dict[str, str] = {}

        model_file = model_dir / f"{model_prefix}.joblib"
        if not model_file.exists():
            raise FileNotFoundError(f"Model artifact not found: {model_file}")

        _upload_joblib_with_sidecar(
            client, model_file, "model", resolved_prefix, artifacts, approved
        )
        _upload_json_model_artifacts(
            client, model_dir, model_prefix, resolved_prefix, artifacts, approved
        )

        return artifacts

    except Exception as e:
        logger.error("GCS upload failed: %s", e)
        raise RuntimeError("GCS model artifact upload failed") from e


def download_model_artifacts(model_uri: str, local_dir: Path, filenames: tuple[str, ...]) -> Path:
    """Download the named artifact files from ``model_uri`` into ``local_dir``.

    Raises ``FileNotFoundError`` naming every missing file, so a partial run is loud.
    """
    from estate_value_index.utils.clients import get_storage_client

    bucket_name, prefix = split_gcs_uri(model_uri)
    bucket = get_storage_client().bucket(bucket_name)
    blobs = {filename: bucket.blob(_destination_path(prefix, filename)) for filename in filenames}
    missing = [filename for filename, blob in blobs.items() if not blob.exists()]
    if missing:
        raise FileNotFoundError(f"Missing model artifacts under {model_uri}: {', '.join(missing)}")

    local_dir.mkdir(parents=True, exist_ok=True)
    for filename, blob in blobs.items():
        blob.download_to_filename(str(local_dir / filename))
    logger.info("Downloaded %d model artifacts from %s to %s", len(blobs), model_uri, local_dir)
    return local_dir


def promote_model_artifacts(
    model_uri: str,
    filenames: tuple[str, ...],
    *,
    production_prefix: str = "models",
    approved: bool = False,
) -> list[str]:
    """Copy validated artifacts from ``model_uri`` to the production prefix that serving reads."""
    require_approval("promote model artifacts to the production GCS path", approved)
    from estate_value_index.utils.clients import get_storage_client

    bucket_name, prefix = split_gcs_uri(model_uri)
    bucket = get_storage_client().bucket(bucket_name)
    promoted = []
    for filename in filenames:
        destination = _destination_path(production_prefix, filename)
        bucket.copy_blob(bucket.blob(_destination_path(prefix, filename)), bucket, destination)
        promoted.append(f"gs://{bucket_name}/{destination}")
    logger.info(
        "Promoted %d model artifacts to gs://%s/%s", len(promoted), bucket_name, production_prefix
    )
    return promoted
