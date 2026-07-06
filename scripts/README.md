# Scripts

Most automation goes through `uv run python -m estate_value_index.cli ...` (see `docs/architecture.md`).

Cloud-mutating scripts require an explicit project via `--project` or environment
variables. They must not fall back to a real project name when config is missing.

```bash
./scripts/setup_bigquery.sh --project your-gcp-project-id
./scripts/create_predictions_table.sh --project your-gcp-project-id
./scripts/cloud_run_disable.sh --project your-gcp-project-id
./scripts/vertex_ai/build_and_push.sh --project your-gcp-project-id --dry-run
```

## Manual / exploratory

These are not imported by the pipeline; run from the repo root with `uv run` or an activated venv.

| Script | Purpose |
| ------ | ------- |
| `analyze_feature_correlation.py` | Ad-hoc feature correlation analysis |
| `fetch_economic_data.py` | Pull external economic series (if configured) |

GCP cost monitoring is a CLI command, not a script here:
`uv run python -m estate_value_index.cli costs` (thin wrapper → `estate_value_index.ops.cost_monitoring`).
