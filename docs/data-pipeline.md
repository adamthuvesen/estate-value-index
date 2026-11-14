# Data pipeline

The data path starts with authorized listing ingestion output, lands raw listings in BigQuery,
then feeds model training or serving artifacts. The public
repo contains code and synthetic fixtures only. Redistributable listing data is not included.

## Main flow

```text
evi backfill --load: fetch -> process -> booli_raw.listings -> geocode -> sync back
  -> evi train-production-models | evi vertex-train -> evi check-model -> evi promote-model
  -> evi value-analysis / areas / overall-stats -> evi upload-enrichment
```

## Where to work

- Signed Booli API adapter: `src/estate_value_index/ingestion/booli/api.py`
- Ingestion utilities and loaders: `src/estate_value_index/ingestion/`
- The one ingestion path: `src/estate_value_index/ingestion/ingest.py` (`ingest_listings`),
  called by `evi backfill` and the workflow
- BigQuery load and its row contract: `ingestion/bigquery_upload.py`, `ingestion/listing_row.py`
  (one bad row stops the load, with a count)
- Sync and geocoding: `ingestion/sync.py`, `ingestion/geocoding.py`
- Orchestration: `.github/workflows/ml-pipeline.yml`
- BigQuery schemas: `schemas/bq_raw_listings.json`
- Settings: `src/estate_value_index/utils/settings.py`
- Web enrichment JSON (`data/derived/`, synced to GCS): `area_statistics.json`,
  `value_analysis.json`, and `overall_statistics.json` (city-wide stats for `/stats`;
  regenerate with `uv run python -m estate_value_index.cli overall-stats`)

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

Optional knobs: `GCS_ENABLED`, `MAX_MEDIAN_APE_THRESHOLD`, `INGESTION_MIN_VALIDATION_RATE`, `DATA_SOURCE`, `BOOLI_TRAIN_DATA`. The `Settings` model lists every key; an unknown key in `.env` is an error.

Signed Booli API credentials for ingestion runs:

```bash
BOOLI_API_CALLER_ID=your-booli-caller-id
BOOLI_API_PRIVATE_KEY=your-booli-private-key
```

The signed API path writes the raw-listing JSONL schema consumed by processing and
BigQuery upload. Authorized exports may provide the same schema directly.

Precedence: environment -> `.env` -> the `Settings` defaults.

BigQuery datasets:

- **booli_raw:** raw listings (e.g. `listings`, partitioned)
- **booli_features:** engineered features (e.g. `engineered_features`, partitioned)

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

- General pipeline/data changes: `just check`; drive the real CLI with `just verify`
- BigQuery safety: `uv run pytest tests/utils/test_bigquery_safety.py tests/utils/test_no_unsafe_sql.py tests/ml/test_filter_api_contract.py`
- Temporal behavior: `uv run pytest tests/ml/test_temporal_leakage.py tests/test_time_series_utils.py`
- Ingestion behavior: `uv run pytest tests/ingestion tests/test_ingestion_utils.py`
