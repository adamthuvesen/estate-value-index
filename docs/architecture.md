# Architecture

This repo predicts Swedish real estate values from authorized listing data. The main flow is:

```text
Permissioned listing source -> BigQuery raw listings -> engineered features -> LightGBM artifacts
  -> Next.js API/routes + FastAPI prediction service
```

The public repo excludes real listing data, geocodes, trained models, model
metrics, and property-level prediction artifacts. Use
`tests/fixtures/` for synthetic shapes and provide private artifacts through
your own lawful data source, BigQuery, GCS, or local environment.

## Stack

| Layer | Tech |
| ----- | ---- |
| Ingestion | Signed API and authorized export inputs |
| Warehouse | BigQuery |
| Training | LightGBM, optional Optuna |
| API | FastAPI + Next.js 16 |
| Container | Docker; supervisor runs Next.js + FastAPI |
| Orchestration | Prefect 3 |
| Artifacts | GCS for models and enrichment data when enabled |

## Main path and entry points

The composed end-to-end path is `pipelines/core/complete_pipeline.py`, which chains
ingestion, feature materialization, training, and deployment. The four flows under
`pipelines/core/` are each independently runnable:

| Entry point | What it runs |
| ----------- | ------------ |
| `pipelines/core/complete_pipeline.py` | The full ingest -> features -> train -> deploy path (composes the others) |
| `pipelines/core/data_pipeline.py` | Ingest + process + load to BigQuery |
| `pipelines/core/training_pipeline.py` | Feature materialization + Vertex AI training |
| `pipelines/core/deployment_pipeline.py` | Cloud Run deployment of the prediction service |
| `uv run python -m estate_value_index.cli <cmd>` | Unified CLI dispatcher (`cli/__main__.py`): `backfill`, `process`, `features`, `areas`, `overall-stats`, `value-analysis`, `area-metrics`, `train-production-models` |
| `api_server.py` | FastAPI prediction service |

## System boundaries

| Area | Where |
| ---- | ----- |
| Ingestion | `src/estate_value_index/ingestion/`, `uv run python -m estate_value_index.cli backfill`, `uv run python -m estate_value_index.cli process` |
| Pipeline orchestration | `src/estate_value_index/pipelines/core/` (flows), `pipelines/tasks/` (Prefect tasks) |
| Feature engineering and training | `src/estate_value_index/ml/` (incl. `ml/features/`, `ml/training_workflow/`, `ml/production_models.py` and its model stack: `market_normalized_target`, `residual_calibration`, `tiered_ensemble`) |
| Analytics generation | `src/estate_value_index/analytics/` (web-JSON generators: area statistics, value analysis, overall statistics) |
| Monitoring | `src/estate_value_index/monitoring/` (drift detection) |
| Shared utilities | `src/estate_value_index/utils/` (settings, GCP client factory, GCS, BigQuery safety) |
| Prediction API | `api_server.py` |
| Web app and Next API routes | `web/src/app/`, `web/src/app/api/` |
| Config and schemas | `config/`, `schemas/` |
| Deploy/runtime | `Dockerfile`, `scripts/startup.sh`, `scripts/deploy_cloud_run.sh` |

## Dependency direction

Imports flow one way, top to bottom. Keep it that way:

```text
cli / pipelines        (entry points, orchestration)
   -> analytics / ml / ingestion / monitoring   (domain logic)
      -> utils         (settings, clients, gcs, bigquery_safety; no domain imports)
```

- `utils/` is the bottom layer: it must not import from `ml/`, `ingestion/`, `pipelines/`, etc.
- `pipelines/` and `cli/` are top layers: domain modules (`ml/`, `analytics/`, `ingestion/`) must not import from them. Orchestration calls down into domain logic, never the reverse.
- Analytics computation lives in `analytics/`; both the CLI (`cli/generate_*`) and the Prefect tasks (`pipelines/tasks/analytics.py`) are thin shells that call down into it.

## Shared conventions

- **Config:** `utils/settings.py` is the raw env/flag/YAML layer (`EnvConfig`, `load_env_config()`, `get_*`/`is_*`). Pipeline-shaped, typed config objects (`BigQueryConfig`, `TrainingFlowConfig`) live in `pipelines/utils/config.py` and build on top of it.
- **GCP clients:** create BigQuery / Storage clients via the cached factory in `utils/clients.py` (`get_bq_client`, `get_storage_client`). Do not instantiate `bigquery.Client()` / `storage.Client()` ad hoc.
- **Errors:** raise the domain exceptions in `exceptions.py` (`DataError`, `ModelError`, `InfrastructureError`, etc.) rather than swallowing failures in the data path.
- **Logging:** `logging.getLogger(__name__)` per module; no decorative emoji in log output.

## Runtime shape

- Python package code lives under `src/estate_value_index/`.
- `api_server.py` is the FastAPI prediction service and loads model artifacts (integrity-verified via `.sha256` sidecars).
- `web/` is the Next.js app; API routes proxy or enrich prediction-facing flows.
- `scripts/` contains operational CLIs and deploy helpers. Prefer dry runs where available.
- `config/pipeline_config.yaml` and environment variables drive pipeline behavior; environment wins over config, then code defaults.

## Operational caveats

- Routes that scan `value_analysis` or area statistics JSON are acceptable at current sizes; index or pre-aggregate them if the files grow substantially.

## Generated artifacts

- `web/models/` is generated training output, ignored by git, and not included in the public repo. Do not hand-edit it.
- GCS can provide model/enrichment artifacts at runtime through `scripts/startup.sh`.
- Analysis images and generated reports should stay out of the public docs tree unless they are curated for readers.

## Related guides

- Pipeline and BigQuery changes: [data-pipeline.md](data-pipeline.md)
- Model and training changes: [ml-and-models.md](ml-and-models.md)
- API, web, and deploy changes: [api-web-deploy.md](api-web-deploy.md)
