# Estate Value Index

Predicts sale prices for Swedish residential listings, end to end: ingest authorized
listing data, land it in BigQuery, engineer features, train LightGBM, and serve
predictions from a FastAPI + Next.js container on Cloud Run.

It exists as a working reference for the whole path — ingestion through serving — rather
than a model in a notebook. The interesting parts are the seams where real systems break:
temporal leakage in training, train/serve skew at inference, and untrusted input reaching
SQL and the file system.

The public repo ships code and synthetic fixtures only, not scraped listings or a
redistributable Booli dataset. Real listings, geocodes, trained models, private datasets,
and production metrics are intentionally excluded. Bring your own lawful data access,
BigQuery, GCS, and `.env` for production-like runs.

## Engineering decisions

These are the choices that shaped the system, and the failure modes they guard against.

- **Chronological splits, never random.** Production evaluation splits on `sold_date`; a naive
  random row split leaks future prices into training and flatters the metric. Area and
  time aggregates are built so they can't peek at rows from the future either. `MAX_MAE_THRESHOLD`
  is re-baselined against honest temporal MAE, not a shuffled holdout. See
  `tests/ml/test_temporal_leakage.py`.
- **Inference feature context matches training.** Train/serve skew is the quiet killer, so area
  normalization (`normalize_area_for_model()` for Booli's `Property - Area - City` strings) and
  the pandas `category` + LightGBM categorical contract are shared between the trainer and
  `api_server.py` rather than reimplemented per side.
- **Models are verified, not trusted.** Serving loads model artifacts with `.sha256` sidecars;
  `scripts/startup.sh` refuses to boot if a required download fails or a sidecar is missing,
  so a corrupted or partial sync fails loud instead of serving garbage.
- **Models live in GCS, not the image.** Training output is git-ignored and never baked into the
  container; `scripts/startup.sh` syncs artifacts from GCS at boot when `GCS_ENABLED=true`. The image
  stays generic and models version independently of deploys.
- **BigQuery SQL is parameterized or operator-only.** Dynamic SQL goes through
  `utils/bigquery_safety.py` (structured Filter API, bound parameters); ad hoc string
  fragments are treated as trusted operator input only, never user data.
  `tests/ml/test_filter_api_contract.py` and `tests/utils/test_no_unsafe_sql.py` keep call sites honest.
- **The runtime service account can only read its bucket.** Cloud Run runs under a dedicated
  least-privilege SA with bucket-scoped GCS object-read and nothing else — no BigQuery, no
  project Editor — because the request path only reads artifacts. `deploy_cloud_run.sh` attaches
  it and refuses to deploy if it's missing, so the service can't silently fall back to the broad
  default identity.
- **One-way dependency layering.** Imports flow `cli`/`pipelines` → domain (`ml`, `ingestion`,
  `analytics`) → `utils`. `utils/` imports no domain code; orchestration calls down, never up.

Some engineered signals are heuristic and hand-tuned, so feature importances get re-checked
after retrains rather than assumed stable.

## Stack

| Layer | Tech |
| ----- | ---- |
| Ingestion | Authorized API/export inputs, Scrapy adapter for parser development |
| Warehouse | BigQuery |
| ML | pandas, scikit-learn, LightGBM, optional Optuna |
| API | FastAPI |
| Web | Next.js 15, React 18 |
| Orchestration | Prefect 3 |
| Deploy | Docker, Cloud Run, GCS |
| Tooling | Python 3.11+, Node 20+, uv, pytest, Jest |

## How it fits together

```text
Authorized listing source → BigQuery raw listings → engineered features → LightGBM artifacts
  → FastAPI /predict + Next.js API routes (one Cloud Run container)
```

The composed path is `pipelines/core/complete_pipeline.py`, which chains ingestion, feature
materialization, training, and deploy. Each stage also runs on its own (`data_pipeline.py`,
`training_pipeline.py`, `deployment_pipeline.py`). Start with
[docs/architecture.md](docs/architecture.md) for the full map;
[AGENTS.md](AGENTS.md) holds the coding-agent rules.

## Setup

Prerequisites: Python 3.11+, Node 20+, `uv`. GCP/BigQuery/GCS access is needed for data and
production-like runs, not for the test suite.

```bash
git clone https://github.com/adamthuvesen/estate-value-index
cd estate-value-index

uv sync --all-extras

cd web && npm install && cd ..

cp .env.example .env   # then fill in GCP/BigQuery/GCS values
```

Minimal required environment (full list in [.env.example](.env.example)):

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

Config precedence is environment variables → [config/pipeline_config.yaml](config/pipeline_config.yaml)
→ code defaults. Inspect resolved settings with
`uv run python -m estate_value_index.utils.settings`.

## Public demo

You can inspect the no-secret fixture output without cloud access:

```bash
uv run python -m json.tool tests/fixtures/synthetic_value_analysis.json
```

Representative output:

```json
{
  "statistics": {
    "total_properties": 2,
    "undervalued_count": 1,
    "overvalued_count": 1,
    "model_performance": {
      "mae": 250000,
      "rmse": 310000,
      "mape": 4.5
    }
  }
}
```

This is a toy fixture, not a public benchmark. It proves the output shape and UI/API
contract. It does not reproduce private listings, geocodes, trained models, cloud state,
or production performance.

## Run locally

```bash
uv run uvicorn api_server:app --host 0.0.0.0 --port 8000
cd web && npm run dev
```

- Web app: http://localhost:3000
- API docs: http://localhost:8000/docs

Set `PREDICTION_API_URL` if the FastAPI service is not on `http://localhost:8000`.

## Data Access

This project is a modeling and systems prototype, not a data product. Before running
ingestion against any third-party site or API, make sure you have the right to access the
data, follow the source's terms, and do not bypass access controls. Prefer signed APIs,
licensed exports, or other permissioned sources for real training data. The included
fixtures are synthetic and are the only data intended for public redistribution.

## Common tasks

```bash
# Test (Python coverage gate is 70%)
uv run pytest
cd web && npm test && cd ..

# Train on materialized features; add --tune for Optuna search
uv run python train_model.py --use-features

# Run the pipeline (see --help for all flags)
uv run python -m estate_value_index.pipelines.core.complete_pipeline --quick      # fast local run
uv run python -m estate_value_index.pipelines.core.complete_pipeline --dry-run    # preview, no cloud work
uv run python -m estate_value_index.pipelines.core.complete_pipeline --retrain    # retrain existing data
uv run python -m estate_value_index.pipelines.core.complete_pipeline --retrain --deploy

# Ingest authorized listings
uv run python -m estate_value_index.cli crawl --max-pages 10

# Deploy to Cloud Run
./scripts/deploy_cloud_run.sh
```

## Repository map

| Path | Purpose |
| ---- | ------- |
| `src/estate_value_index/ingestion/` | Listing ingestion, parsing, BigQuery load |
| `src/estate_value_index/pipelines/` | Prefect flows and tasks |
| `src/estate_value_index/ml/` | Feature engineering, data loading, training |
| `src/estate_value_index/monitoring/` | Evidently drift checks |
| `src/estate_value_index/utils/` | Settings, GCP clients, GCS, BigQuery safety |
| `web/src/app/` | Next.js pages and API routes |
| `config/`, `schemas/` | Pipeline/feature config and BigQuery schemas |
| `scripts/` | Deploy, startup, materialization, ops helpers |
| `tests/` | Python test suite |

Deeper docs: [data-pipeline.md](docs/data-pipeline.md),
[ml-and-models.md](docs/ml-and-models.md),
[api-web-deploy.md](docs/api-web-deploy.md).

## License

MIT — see [LICENSE](LICENSE).
