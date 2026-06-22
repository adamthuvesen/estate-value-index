# Data pipeline

The data path is listing ingestion output into BigQuery raw listings, engineered feature materialization, then model training or serving artifacts.

## Main flow

```text
Booli -> spider -> JSONL + upload path -> process_listings -> booli_raw.listings
  -> materialize_features -> booli_features.engineered_features
  -> train_model.py / pipeline -> web/models/* -> Next /api/* -> FastAPI /predict
```

## Where to work

- Spider and extraction logic: `src/estate_value_index/ingestion/booli/`
- Ingestion utilities and loaders: `src/estate_value_index/ingestion/`
- Pipeline orchestration: `src/estate_value_index/pipelines/core/complete_pipeline.py`
- Pipeline tasks: `src/estate_value_index/pipelines/tasks/`
- BigQuery schemas: `schemas/bq_raw_listings.json`, `schemas/bq_features_engineered.json`
- Pipeline config: `config/pipeline_config.yaml`

## Environment

Required `.env` vars:

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

Optional knobs (examples): `GCS_ENABLED`, `MAX_MAE_THRESHOLD`, `DATA_SOURCE`, `MODEL_PREFIX`, `MODEL_OUTPUT_DIR`, `DEBUG`, `TRUST_PROXY_HEADERS`.

Precedence: environment → `config/pipeline_config.yaml` → code defaults.

BigQuery datasets:

- **booli_raw** — raw listings (e.g. `listings`, partitioned)
- **booli_features** — engineered features (e.g. `engineered_features`, partitioned)

## BigQuery rules

- Typical raw table: `booli_raw.listings`.
- Typical feature table: `booli_features.engineered_features`.
- Project, dataset, and table names come from environment variables first.
- Use helpers such as `src/estate_value_index/utils/bigquery_safety.py` for validation and parameterized/operator-only SQL.
- Treat dynamic SQL fragments like `where_clause` as trusted operator fragments only, never direct user input.

## Leakage and data quality

- Respect `sold_date` and chronological semantics when building training data.
- Area/time aggregates must not peek into future rows.
- Notebooks that use random `train_test_split` are exploratory, not the production training story.
- Make silent failures loud: skipped rows, wrong schemas, and false-success uploads should be visible in logs or tests.
- Interactive `/api/fetch-listing` uses the same boolean coercion contract as ingestion (`normalization.to_bool` / `coerceBool`); shared examples live in `tests/fixtures/bool_coercion_cases.json`.

## Checks to run

- General pipeline/data changes: `uv run pytest`
- BigQuery safety: `uv run pytest tests/utils/test_bigquery_safety.py tests/utils/test_no_unsafe_sql.py tests/ml/test_filter_api_contract.py`
- Temporal behavior: `uv run pytest tests/ml/test_temporal_leakage.py tests/test_time_series_utils.py`
- Ingestion behavior: `uv run pytest tests/ingestion tests/test_ingestion_parsers.py tests/test_ingestion_utils.py`
