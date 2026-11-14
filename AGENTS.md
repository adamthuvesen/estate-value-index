# AGENTS.md

**estate-value-index** predicts Swedish real estate values: authorized listing
ingestion -> BigQuery -> LightGBM -> Next.js + FastAPI. Python 3.14 via **uv**;
Node 24 for `web/`. The `evi` CLI and GitHub Actions are the only orchestrators.

Terms: [GLOSSARY.md](GLOSSARY.md). Decisions: [docs/adr/](docs/adr/).

## Commands

```bash
uv sync --all-extras    # setup: Python environment
npm ci --prefix web     # setup: web dependencies
just check              # lint, format, types, tests; CI runs the same
just fix                # apply safe automatic fixes
just verify             # drive the real CLI and API on synthetic data
just slow               # full suite with the coverage gate, plus the web build
just types              # regenerate web/src/lib/generated/api-types.ts
```

Prove user-facing changes with the `verify-estate-value-index` skill in
`.agents/skills/verify-estate-value-index` (`just verify all`).

`evi --help` lists the pipeline steps. Config precedence: environment -> `.env`
-> the defaults in `src/estate_value_index/utils/settings.py`.

## Layout

- `src/estate_value_index/`: `cli/` entry points, `analytics/`, `ml/`, `ingestion/`, `areas.py`, `utils/`
- `api_server.py`: FastAPI prediction service
- `web/`: Next.js app and API routes
- `vertex_ai/`: Vertex AI trainer container
- `.github/workflows/`: `ci.yml`, `ml-pipeline.yml`, `deploy.yml` (the one deploy path)
- `schemas/`: BigQuery schemas
- `tests/conftest.py`: shared fixtures

Guides: [architecture](docs/architecture.md), [data pipeline](docs/data-pipeline.md),
[ML and models](docs/ml-and-models.md), [API, web, deploy](docs/api-web-deploy.md).

## Enforced Rules

| Rule | Enforced by |
| --- | --- |
| Spending money or writing to production refuses without approval | `src/estate_value_index/utils/approval.py::require_approval`, `tests/utils/test_approval_gates.py::test_require_approval_refuses_with_system_exit` |
| Module layers import in one direction | `pyproject.toml::Layers` |
| Only `cli/vertex_train.py` starts a process | `pyproject.toml::Process modules` |
| Only the owner modules use network clients | `pyproject.toml::Network clients` |
| Only the owner modules import Google Cloud SDKs | `pyproject.toml::Google Cloud SDKs` |
| Raw listings, derived data, and trained models stay out of git | `.gitignore::data/raw/booli/*`, `.gitignore::web/models/*` |
| Training and evaluation respect `sold_date` chronology | `tests/ml/test_temporal_leakage.py::test_validate_temporal_leakage_rejects_boundary` |
| BigQuery SQL uses bound parameters | `tests/utils/test_no_unsafe_sql.py::test_no_unreviewed_dynamic_sql` |
| One bad listing row stops the BigQuery load | `src/estate_value_index/ingestion/listing_row.py::validate_listing_rows` |
| Area names have one owner and fixed forms | `tests/test_areas.py::test_area_forms_match_the_replaced_implementations` |
| The API refuses a model with a missing or different package version | `api_server.py::_check_package_version`, `tests/api/test_model_integrity.py::test_load_all_models_refuses_a_different_package_version` |
| The API refuses a model whose `.sha256` sidecar does not match | `api_server.py::_verify_model_integrity` |
| Web TypeScript types match the Pydantic models | `justfile::types-check` |

## Limits code cannot enforce

- Never approve a spend or production write yourself. The user approves it.
- Use `--dry-run` on CLIs that support it when the outcome is uncertain.
- Put model metrics, experiment results, and research notes in `docs/internal/`
  (git-ignored, absent on a fresh clone), never in the public docs tree.
- Models sync from GCS at startup and are not baked into the image. `GCS_ENABLED`
  differs across CI, dev, and prod: [docs/api-web-deploy.md](docs/api-web-deploy.md).
