# Scripts

Most automation goes through `python -m estate_value_index.cli …` (see `docs/PROJECT.md`).

## Manual / exploratory

These are not imported by the pipeline; run from the repo root with `uv run` or an activated venv.

| Script | Purpose |
| ------ | ------- |
| `analyze_feature_correlation.py` | Ad-hoc feature correlation analysis |
| `fetch_economic_data.py` | Pull external economic series (if configured) |
| `monitor_costs.py` | Thin wrapper → `estate_value_index.ops.cost_monitoring` |

## Deprecated names (removed)

Legacy entrypoints `clean_areas.py`, `merge_listings.py`, `impute_days_on_market.py` no longer exist; they are mentioned in agent docs only as **do not use**.
