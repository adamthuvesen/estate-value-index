# Estate Value Index

Swedish real estate price prediction from listing data to a served web app.

The repo contains the full path: Scrapy ingestion, BigQuery loading/materialization, model training, runtime model artifact loading, a FastAPI prediction service, a Next.js frontend, and deploy/runtime scripts for Cloud Run.


## Start Here

Read [AGENTS.md](AGENTS.md) for coding-agent rules and routes into [agents/docs/](agents/docs/). Start with [agents/docs/architecture.md](agents/docs/architecture.md) for the system overview.

## What It Does

- Ingests Swedish property listing data via a Scrapy pipeline.
- Loads raw listings into BigQuery.
- Builds engineered features into a feature table.
- Trains LightGBM models with production-oriented chronological evaluation.
- Serves predictions through FastAPI and Next.js API routes.
- Runs as a combined web/API container, with model artifacts synced from GCS when configured.

## Stack

| Layer | Tech |
| ----- | ---- |
| Ingestion | Scrapy |
| Warehouse | BigQuery |
| ML | pandas, scikit-learn, LightGBM, optional Optuna |
| API | FastAPI |
| Web | Next.js 15, React 18 |
| Orchestration | Prefect 3 |
| Deploy | Docker, Cloud Run, GCS |
| Tooling | Python 3.11+, Node 20+, uv, pytest, Jest |

## Quickstart

Prerequisites:

- Python 3.11+
- Node 20+
- `uv`
- GCP/BigQuery/GCS access for data and production-like runs

```bash
git clone <repository-url>
cd estate-value-index

uv sync --all-extras
source .venv/bin/activate

cd web
npm install
cd ..

cp .env.example .env
```

Edit `.env` with your GCP, BigQuery, and GCS settings. The required defaults are documented in [.env.example](.env.example) and [AGENTS.md](AGENTS.md).

## Run Locally

Start FastAPI on `localhost:8000` and Next.js on `localhost:3000`:

```bash
./start.sh
```

- Web app: http://localhost:3000
- FastAPI: http://localhost:8000
- API docs: http://localhost:8000/docs
- API logs: `logs/api_server.log`

You can also run the web app directly:

```bash
cd web
npm run dev
```

## Common Workflows

### Test

```bash
pytest

cd web
npm test
```

Useful focused tests:

```bash
uv run pytest tests/ml/test_temporal_leakage.py
uv run pytest tests/api/test_model_integrity.py tests/test_api_server.py
uv run pytest tests/utils/test_bigquery_safety.py tests/ml/test_where_clause_call_sites.py
```

### Train

```bash
uv run python train_model.py --use-features
```

For tuning:

```bash
uv run python train_model.py --use-features --tune
```

### Run The Pipeline

```bash
# Fast local-oriented run
uv run python -m estate_value_index.pipelines.core.complete_pipeline --quick

# Preview pipeline configuration without running cloud work
uv run python -m estate_value_index.pipelines.core.complete_pipeline --dry-run

# Retrain on existing data without deploying
uv run python -m estate_value_index.pipelines.core.complete_pipeline --retrain

# Production deploy path; requires explicit cloud env and protected workflows
uv run python -m estate_value_index.pipelines.core.complete_pipeline --retrain --deploy
```

See all flags:

```bash
uv run python -m estate_value_index.pipelines.core.complete_pipeline --help
```

### Ingest listings

```bash
uv run python -m estate_value_index.cli.crawl_booli --max-pages 10
```

### Deploy

```bash
./scripts/deploy_cloud_run.sh
```

Models are usually not baked into the image. Runtime model/enrichment artifacts are synced through GCS when `GCS_ENABLED=true`; see [scripts/startup.sh](scripts/startup.sh).

## Configuration

Configuration precedence:

```text
environment variables -> config/pipeline_config.yaml -> code defaults
```

Minimal required environment:

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

Check settings with:

```bash
uv run python -m estate_value_index.utils.settings
```

## Repository Map

| Path | Purpose |
| ---- | ------- |
| `src/estate_value_index/ingestion/` | Listing ingestion, parsing, and BigQuery load code |
| `src/estate_value_index/pipelines/` | Prefect pipeline orchestration and tasks |
| `src/estate_value_index/ml/` | Feature engineering, data loading, training workflows |
| `src/estate_value_index/monitoring/` | Evidently-based drift checks |
| `web/src/app/` | Next.js pages and API routes |
| `web/models/` | Generated model artifacts; do not hand-edit |
| `config/` | Pipeline and feature configuration |
| `schemas/` | BigQuery and prediction schemas |
| `scripts/` | Operational scripts, deploy, startup, materialization helpers |
| `tests/` | Python test suite |

## Documentation

- [agents/docs/architecture.md](agents/docs/architecture.md) - system boundaries and runtime shape.
- [agents/docs/data-pipeline.md](agents/docs/data-pipeline.md) - ingestion, BigQuery, pipeline, and data-quality rules.
- [agents/docs/ml-and-models.md](agents/docs/ml-and-models.md) - training contract, artifacts, and ML checks.
- [agents/docs/api-web-deploy.md](agents/docs/api-web-deploy.md) - FastAPI, Next.js, container, and deploy notes.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for the full text.
