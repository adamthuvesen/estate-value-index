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
| Orchestration | `evi` CLI + GitHub Actions (`ml-pipeline.yml`, `deploy.yml`) |
| Artifacts | GCS for models and enrichment data when enabled |

## Main path and entry points

There is no orchestration framework. The `evi` CLI owns every step, and
`.github/workflows/ml-pipeline.yml` calls the steps in order. `deploy.yml` is the
one deploy path. Every step that spends or writes to production (`backfill --load`,
`vertex-train`, `promote-model`, `upload-enrichment`) refuses without the approval flag.

| Entry point | What it runs |
| ----------- | ------------ |
| `evi backfill [--process] [--load]` | The one ingestion path (`ingestion/ingest.py`): fetch sold-date windows; `--load` also processes, writes BigQuery, geocodes, syncs back, and backs up to GCS |
| `evi sync` | BigQuery listings -> local production file, checked |
| `evi train-production-models` | Local training of the two production models |
| `evi vertex-train` | The same trainer on Vertex AI (`vertex_ai/` container); waits and downloads the artifacts. Job id and model URI come from the `gcloud --format=json` response |
| `evi check-model` | The MdAPE quality gate (`MAX_MEDIAN_APE_THRESHOLD`) |
| `evi promote-model` | Copy validated Vertex artifacts to `gs://<bucket>/models/` |
| `evi value-analysis`, `evi areas`, `evi overall-stats` | The three derived web JSON files |
| `evi upload-enrichment` | Publish `data/derived/*.json` to GCS |
| `api_server.py` | FastAPI prediction service |

## System boundaries

| Area | Where |
| ---- | ----- |
| Entry points | `src/estate_value_index/cli/` |
| Ingestion | `src/estate_value_index/ingestion/` (Booli client, processing, BigQuery load and row contract, sync, geocoding) |
| Area names | `src/estate_value_index/areas.py`: the single owner of Booli tokens, cleaned names, model keys, and display names |
| Feature engineering and training | `src/estate_value_index/ml/` (incl. `ml/features/` with the production feature sets in `registry.py`, `ml/training_workflow/`, `ml/production_models.py` and its model stack, `ml/reference/` packaged CSVs) |
| Analytics generation | `src/estate_value_index/analytics/` (web-JSON generators, their contract in `web_json.py`, and the GCS publish) |
| Shared utilities | `src/estate_value_index/utils/` (settings, GCP client factory, GCS, BigQuery safety, JSONL reader) |
| Prediction API | `api_server.py` |
| Web app and Next API routes | `web/src/app/`, `web/src/app/api/`; generated types in `web/src/lib/generated/` |
| Schemas | `schemas/` |
| Deploy/runtime | `Dockerfile`, `scripts/startup.sh`, `.github/workflows/deploy.yml` |

## Dependency direction

Imports flow one way, top to bottom. The import-linter `Layers` contract in `pyproject.toml` enforces it in `just check`:

```text
cli                    (entry points)
   -> analytics        (statistics built on ml)
      -> ml | ingestion  (independent: neither imports the other)
         -> areas      (area names)
            -> utils   (settings, clients, gcs, bigquery_safety, approval, jsonl)
               -> exceptions
```

- `utils/` and `exceptions` are the bottom layers.
- `ml/` and `ingestion/` are siblings. Shared area-name logic lives in `areas.py` below both.
- Process, network, and Google Cloud SDK modules are allowed only in the owner modules listed in the `Process modules`, `Network clients`, and `Google Cloud SDKs` contracts (plus ruff `TID251` for `urllib.request` and `os.system`-style calls). `cli/vertex_train.py` is the only module that starts a process.
- Functions that spend money or write to production take `approved: bool = False` and call `utils/approval.py` `require_approval` first.
- Analytics computation lives in `analytics/`; the CLI (`cli/generate_*`) is a thin shell over it.

## Shared conventions

- **Config:** `utils/settings.py` holds one `pydantic-settings` model (`Settings`, `extra="forbid"`). Read it with `get_settings()`.
- **Model metadata:** each `*_metrics.json` carries `package_version` and `data_fingerprint` (row count, newest `sold_date`, content hash of the training frame). `api_server.py` refuses an artifact whose `package_version` differs from the installed package, and `/health` reports both per model.
- **Web types:** `just types` generates `web/src/lib/generated/api-types.ts` from the Pydantic models' JSON Schema (`scripts/export_web_schema.py`); `just check` fails on drift.
- **GCP clients:** create BigQuery / Storage clients via the cached factory in `utils/clients.py` (`get_bq_client`, `get_storage_client`). Do not instantiate `bigquery.Client()` / `storage.Client()` ad hoc.
- **Errors:** raise the domain exceptions in `exceptions.py` (`DataError`, `ModelError`, `InfrastructureError`, etc.) rather than swallowing failures in the data path.
- **Logging:** `logging.getLogger(__name__)` per module; no decorative emoji in log output.

## Runtime shape

- Python package code lives under `src/estate_value_index/`.
- `api_server.py` is the FastAPI prediction service and loads model artifacts (integrity-verified via `.sha256` sidecars).
- `web/` is the Next.js app; API routes proxy or enrich prediction-facing flows.
- `scripts/` contains operational CLIs and deploy helpers. Prefer dry runs where available.
- Environment variables (and `.env`) drive configuration; environment wins, then the `Settings` defaults.

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
