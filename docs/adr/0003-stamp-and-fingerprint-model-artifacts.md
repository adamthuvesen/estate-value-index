# Stamp model artifacts with a package version and a data fingerprint, and refuse unstamped ones

Status: accepted (2026-11-12)

Training writes `package_version` and `data_fingerprint` (row count, newest `sold_date`, content hash of the training frame) into each model's metrics file. The API loader (`api_server.py::_check_package_version`) refuses an artifact whose `package_version` is missing or differs from the installed package, and `/health` reports both values per model. We chose a fingerprint over a BigQuery snapshot pin because the listings table is mutable.

## Considered options

- Warn and serve an unstamped model. Rejected: a model trained with different feature code than the code that serves it gives silently wrong prices.
- Pin a BigQuery snapshot per training run. Rejected: it costs storage and a snapshot lifecycle, and it still does not tie the model to the code version.

## Consequences

- A version bump makes models from the earlier version stop loading. Retrain after each bump, before the next deploy. Models already in GCS have no stamp, so the first deploy of this change needs a retrain first, or `/health` returns 503.
- The stamp proves the code version, not that the data is good. Data quality stays with the row contract and the quality gate.
- Changing the stamp format breaks every existing artifact, so treat it as a persisted interface.
