# API, web, and deploy

The app serves predictions through FastAPI and a Next.js frontend/API layer in one deployable container.

## Where to work

- FastAPI prediction service: `api_server.py`
- Next.js pages and API routes: `web/src/app/`, `web/src/app/api/`
- Shared web parsing and URL utilities: `web/src/lib/`
- Container startup: `Dockerfile`, `scripts/startup.sh`
- Cloud Run deploy: `scripts/deploy_cloud_run.sh`

## API and web rules

- API routes that need Node APIs should export `runtime = 'nodejs'`.
- Do not use `localStorage` or `sessionStorage` in web artifacts.
- Booli URL handling should stay allow-listed and timeout-bound.
- Keep FastAPI errors from leaking stack traces; responses should expose correlation IDs where applicable.
- Prediction work should not block the event loop when existing code already offloads it.
- Use `TRUST_PROXY_HEADERS=true` only when the deploy path controls the proxy boundary; it is needed behind Cloud Run when rate limiting should use the real client IP.
- Next.js routes that read enrichment files should return opaque 500s and log details server-side.

## Deploy/runtime notes

- The container runs Next.js and FastAPI together.
- Models are not committed or baked into the image; `scripts/startup.sh` can sync required artifacts from your configured GCS bucket.
- `GCS_ENABLED` often differs between dev, CI, and production.
- Rate limiting is in-process unless a shared backend is added.
- `scripts/startup.sh` refuses to start if required model downloads fail or `.joblib.sha256` sidecars are missing.
- Deployment scripts use `set -euo pipefail`; keep destructive or cloud-mutating scripts explicit about required variables and dry-run behavior.

## Checks to run

- FastAPI/API changes: `uv run pytest tests/test_api.py tests/test_api_server.py tests/api`
- Web route changes: `cd web && npm test`
- Deploy/startup changes: `uv run pytest tests/test_deployment_integration.py tests/api/test_gcs_sidecar_upload.py`
- Full confidence before commit: `uv run pytest`, plus web tests for any `web/` change.
