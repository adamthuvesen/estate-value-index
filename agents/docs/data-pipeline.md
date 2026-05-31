# Data pipeline

The data path is listing ingestion output into BigQuery raw listings, engineered feature materialization, then model training or serving artifacts.

## Main flow

```text
Listing spider -> JSONL/upload path -> process listings -> booli_raw.listings
  -> materialize features -> booli_features.engineered_features
  -> train_model.py or complete_pipeline.py
```

## Where to work

- Spider and extraction logic: `src/estate_value_index/ingestion/booli/`
- Ingestion utilities and loaders: `src/estate_value_index/ingestion/`
- Pipeline orchestration: `src/estate_value_index/pipelines/core/complete_pipeline.py`
- Pipeline tasks: `src/estate_value_index/pipelines/tasks/`
- BigQuery schemas: `schemas/bq_raw_listings.json`, `schemas/bq_features_engineered.json`
- Pipeline config: `config/pipeline_config.yaml`

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

## Checks to run

- General pipeline/data changes: `pytest`
- BigQuery safety: `pytest tests/utils/test_bigquery_safety.py tests/ml/test_where_clause_call_sites.py`
- Temporal behavior: `pytest tests/ml/test_temporal_leakage.py tests/test_time_series_utils.py`
- Ingestion behavior: `pytest tests/ingestion tests/test_ingestion_parsers.py tests/test_ingestion_utils.py`
