# Stamp model artifacts with a package version, a commit SHA, and a data fingerprint, and refuse unstamped ones

Status: accepted (2026-11-12)

Training writes `package_version`, `commit_sha`, and `data_fingerprint` (row count, newest `sold_date`, content hash of the training frame) into each model's metrics file. `commit_sha` is `GITHUB_SHA` when set, else `git rev-parse HEAD`, else `unknown`. The API loader (`api_server.py::_check_package_version`) refuses an artifact whose `package_version` is missing or differs from the installed package, and `/health` reports all three values per model. We chose a fingerprint over a BigQuery snapshot pin because the listings table is mutable.

## Considered options

- Warn and serve an unstamped model. Rejected: a model trained with different feature code than the code that serves it gives silently wrong prices.
- Pin a BigQuery snapshot per training run. Rejected: it costs storage and a snapshot lifecycle, and it still does not tie the model to the code version.

## Consequences

- Every Vertex retrain in `ml-pipeline.yml` builds the trainer image from the run's commit, tags it with that SHA, and passes that exact tag to `evi vertex-train`. The image, the stamp, and the commit match. A `:latest` image is never used in CI.
- A version bump makes models from the earlier version stop loading. Retrain after each bump, before the next deploy. Models already in GCS have no stamp, so the first deploy of this change needs a retrain first, or `/health` returns 503.
- `package_version` is the only stamp the loader checks. Nothing bumps it automatically (`pyproject.toml` pins `1.0.0`), so it detects a deliberate bump or a changed stamp format, not a change to feature code. Bump it by hand when feature code changes in a way old models cannot serve.
- `commit_sha` proves which commit trained the model, for audit and for matching a model to a deploy. The loader does not check it, because a commit that changed only docs or tests would otherwise force a retrain. It does not prove the commit's code is what serves the model.
- The stamps do not prove the data is good. Data quality stays with the row contract and the quality gate.
- Changing the stamp format breaks every existing artifact, so treat it as a persisted interface.
