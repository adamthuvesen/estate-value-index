# AGENTS.md

**estate-value-index** is a Swedish real estate ML system: **Scrapy** → **BigQuery** → **LightGBM** → **Next.js** + **FastAPI**. Python 3.11+ with **uv**; Node 20+ for `web/`.

**Read next**

- [agents/docs/architecture.md](agents/docs/architecture.md) — architecture, runtime shape, and system boundaries
- [agents/docs/data-pipeline.md](agents/docs/data-pipeline.md) — ingestion, BigQuery, feature materialization, and pipeline rules
- [agents/docs/ml-and-models.md](agents/docs/ml-and-models.md) — training, feature context, model artifacts, and ML checks
- [agents/docs/api-web-deploy.md](agents/docs/api-web-deploy.md) — FastAPI, Next.js, container startup, and deploy notes

---

## Critical rules

**MUST**

- `uv sync --all-extras`, then run Python via `uv run …` (no manual `activate` needed; `uv run` always uses the project venv)
- Run **`uv run pytest`** before commit; for web changes also `cd web && npm test` (and lint/typecheck as needed)
- Read the matching guide under [agents/docs/](agents/docs/) when you touch pipeline, ML, API, or deploy
- Use `--dry-run` on CLIs that support it when outcomes are uncertain

**NEVER**

- Commit to **main** directly (use a branch/PR)
- Hand-edit **web/models/** (training outputs)
- Use deprecated scripts: `clean_areas.py`, `merge_listings.py`, `impute_days_on_market.py`
- Use **localStorage** / **sessionStorage** in **web** artifacts
- **Trust** ad hoc strings in BigQuery SQL; use operator-only / parameterized patterns (see `utils/bigquery_safety.py`, [agents/docs/data-pipeline.md](agents/docs/data-pipeline.md))

---

## Essential commands

```bash
uv sync --all-extras           # create/update the .venv
uv run pytest                  # run tests (no manual activate needed)
cd web && npm run dev          # app on localhost:3000
```

**Train (typical):** `uv run python train_model.py --use-features`  
**Pipeline (orchestrated):** e.g. `uv run python -m estate_value_index.pipelines.core.complete_pipeline --quick` (see [agents/docs/data-pipeline.md](agents/docs/data-pipeline.md) and `complete_pipeline --help`)
**Deploy:** `./scripts/deploy_cloud_run.sh` (see [agents/docs/api-web-deploy.md](agents/docs/api-web-deploy.md))

---

## Environment (`.env` — required)

```bash
GCP_PROJECT_ID=your-gcp-project-id
GCP_REGION=europe-north1
BIGQUERY_PROJECT_ID=your-gcp-project-id
BIGQUERY_DATASET_RAW=booli_raw
BIGQUERY_TABLE_LISTINGS=listings
BIGQUERY_DATASET_FEATURES=booli_features
BIGQUERY_TABLE_FEATURES=engineered_features
GCS_BUCKET=your-gcs-bucket
```

**Optional (examples):** `GCS_ENABLED`, `MAX_MAE_THRESHOLD`, `DATA_SOURCE`, `MODEL_PREFIX`, `MODEL_OUTPUT_DIR`, `DEBUG`, `TRUST_PROXY_HEADERS`. **Precedence:** environment → [config/pipeline_config.yaml](config/pipeline_config.yaml) → code defaults.

---

## BigQuery (names)

- **booli_raw** — raw listings (e.g. `listings`, partitioned)
- **booli_features** — engineered features (e.g. `engineered_features`, partitioned)

---

## Key file pointers

| Path | Role |
| ---- | ---- |
| [train_model.py](train_model.py) | Training entry |
| [api_server.py](api_server.py) | FastAPI prediction service |
| `src/estate_value_index/ml/` | Features, loader, training |
| `src/estate_value_index/pipelines/core/complete_pipeline.py` | Main orchestrated pipeline |
| `web/src/app/api/` | Next.js API routes (`runtime = 'nodejs'` where needed) |
| [config/pipeline_config.yaml](config/pipeline_config.yaml) | Thresholds, ingestion defaults |
| [tests/conftest.py](tests/conftest.py) | Shared fixtures |
| [Dockerfile](Dockerfile) / [scripts/startup.sh](scripts/startup.sh) | Container, GCS model sync |

---

## Top gotchas

1. **Temporal leakage** — respect `sold_date` / chronological training; no naive random row split for production training.
2. **Feature context** — inference must match training (`build_feature_context` in `ml/`).
3. **Models** — not committed or baked in image; GCS + `startup.sh` when configured.
4. **Categoricals** — follow trainer: pandas `category` + LightGBM; details in `ml/`.
5. **GCS in CI** — often `GCS_ENABLED=false` to avoid creds issues.

**Exploration:** [tests/conftest.py](tests/conftest.py).

**Workflow:** search for existing patterns; test incrementally. **Versions:** **uv** (not pip) · Python 3.11+ · Node 20+ · Next.js 15 · LightGBM
