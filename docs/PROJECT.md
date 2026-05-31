# Project reference

Single place for **what this repo is** and **how it is deployed**. Details live in code (`src/estate_value_index/`, `web/`, `config/`). Feature names and line-by-line training logic are not duplicated here.

## What

Swedish listing data: **Scrapy** → **BigQuery** (raw + engineered tables) → **LightGBM** training → artifacts under `web/models/` (generated and ignored). **Next.js** (8080) and **FastAPI** (`api_server.py`, 8000) in one container, orchestrated in dev/prod with **Prefect** for batch flows. **ML monitoring** uses Evidently-based drift checks (see `src/estate_value_index/monitoring/`).

The public repo intentionally excludes any real listing data, geocodes, trained models, model metrics, and property-level prediction artifacts. Use `tests/fixtures/` for synthetic shapes and provide private artifacts through your own BigQuery/GCS/local environment.

**Focus now:** temporal split fixed (2026-04); retrain and re-baseline `MAX_MAE_THRESHOLD` to honest MAE; keep watching drift alert precision.

## Caveats (evaluation and inference)

- **Area keys:** Use `normalize_area_for_model()` in `src/estate_value_index/ml/preprocessing.py` for the same Booli-style `Property · Area · City` handling as training (FastAPI predict and feature materialization align on this).
- **Notebooks vs training:** Anything under `notebooks/` that uses random `train_test_split` or ad hoc paths is not the production chronological training story; use `train_model.py` and CI tests for baseline evaluation.
- **Production retrain:** After validation, models may be fit on all engineered data; treat holdout metrics as bounded, not automatic live generalization, without a fresh temporal backtest.
- **Heuristic features:** Some engineered signals (e.g. distance-style rules) are hand-tuned; re-check feature importances after retrains.
- **Rate limits:** FastAPI uses an in-process TTL cache and lock; effective limits are per worker unless you add a shared backend.
- **Large enrichment JSON:** Routes that scan `value_analysis` / area statistics JSON are acceptable at current sizes; consider indexing or pre-aggregation if files grow substantially.
- **GCP cost CLI:** `estate_value_index.ops.cost_monitoring` / CLI `costs` subcommand reports usage estimates, not invoiced billing.
- **Booli prefill vs ingestion:** Interactive `/api/fetch-listing` uses the same boolean coercion contract as ingestion (`normalization.to_bool` / `coerceBool` in `web/src/lib/booli-listing-parser.ts`); see `tests/fixtures/bool_coercion_cases.json`.

## Data flow

```text
Booli → spider → JSONL + upload path → process_listings → booli_raw.listings
  → materialize_features → booli_features.engineered_features
  → train_model.py / pipeline → web/models/* → Next /api/* → FastAPI /predict
```

## Stack

| Layer        | Tech |
| ------------ | ---- |
| Ingestion    | Scrapy |
| Warehouse    | BigQuery |
| Training     | LightGBM, optional Optuna |
| API          | FastAPI + Next.js 15 |
| Container    | Docker; supervisor: Next + FastAPI |
| Orchestration| Prefect 3 |
| Artifacts    | GCS (models, enrichment) when enabled |

## Where to look (code)

| Path | Role |
| ---- | ---- |
| `src/estate_value_index/pipelines/core/complete_pipeline.py` | Main automated pipeline (flags: `--help`) |
| `src/estate_value_index/ml/` | Features, `data_loader.py`, `training.py` |
| `src/estate_value_index/ingestion/` | Spiders, BQ load |
| `api_server.py` | Prediction service |
| `web/src/app/api/` | Next API routes; use `runtime = 'nodejs'` when needed |
| `train_model.py` | Local training CLI (orchestration in `ml/training_workflow/`) |
| `src/estate_value_index/ml/features/` | Feature engineering modules (split from legacy `_core.py`) |
| `src/estate_value_index/ingestion/booli/extractors/` | Booli field extractors (mixed into `BooliSpider`) |
| `scripts/deploy_cloud_run.sh` | Cloud Run deploy |
| `scripts/startup.sh` | Container: fetch models, start processes |

**Features:** implemented under `src/estate_value_index/ml/features/` (dozens of columns; importances change per train). **Do not** use a naive random time split for the real training story; area/time aggregates must respect `sold_date` to avoid leakage.

## BigQuery (typical)

- `booli_raw.listings` — processed listings (partitioning as in schema)
- `booli_features.engineered_features` — materialized feature rows

Project/dataset names come from `.env` (see [AGENTS.md](../AGENTS.md)).

## Runbooks (short)

```bash
# Dev
uv sync --all-extras && source .venv/bin/activate
pytest
cd web && npm run dev

# Train (common)
python train_model.py --use-features

# Orchestrated pipeline
python -m src.estate_value_index.pipelines.core.complete_pipeline --quick   # or --production, etc.
```

**Deploy production:** `./scripts/deploy_cloud_run.sh` — image does not bake models; set `GCS_BUCKET` and use GCS + `startup.sh` sync. `GCS_ENABLED` differs dev vs prod; CI often forces off.

## Security and reliability (condensed)

- **API:** Rate limits are bounded; real client IP behind Cloud Run only if `TRUST_PROXY_HEADERS=true` in `deploy_cloud_run.sh`. 500s return `correlation_id`, not stack traces. Predict runs off the event loop thread pool where used.
- **BigQuery:** `project_id` / numeric params validated or parameterized (`utils/bigquery_safety.py`). Treat dynamic SQL fragments (`where_clause`) as **operator-only**, not user input.
- **Models:** `joblib` loads require `.sha256` sidecars; `startup.sh` fails if required model download fails. Unusual pickle edge cases are documented in `api_server.py` if you need them.
- **Web:** Booli URL allow-list and timeouts in `web/src/lib/booli-url.ts` / `fetch-listing` route; API routes that need Node export `runtime = 'nodejs'`.
- **Shell/GCP:** Destructive scripts use `set -euo pipefail` and require explicit vars/flags.

## Config precedence

Environment variables → `config/pipeline_config.yaml` → code defaults. Required env: see [AGENTS.md](../AGENTS.md).
