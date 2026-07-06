# AGENTS.md

**estate-value-index** is a Swedish real estate ML system: authorized listing ingestion -> **BigQuery** -> **LightGBM** -> **Next.js** + **FastAPI**. Python 3.11+ with **uv**; Node 20+ for `web/`.

User-level guidance (tone, principles, git etiquette) lives in `~/.claude/CLAUDE.md` and `~/dotfiles/agents/AGENTS.md` and is *not* duplicated here. This file is for project-specific facts.

**Read next**

- [docs/architecture.md](docs/architecture.md): architecture, runtime shape, and system boundaries
- [docs/data-pipeline.md](docs/data-pipeline.md): ingestion, BigQuery, feature materialization, and pipeline rules
- [docs/ml-and-models.md](docs/ml-and-models.md): training, feature context, model artifacts, and ML checks
- [docs/api-web-deploy.md](docs/api-web-deploy.md): FastAPI, Next.js, container startup, and deploy notes

---

## Critical rules

**MUST**

- `uv sync --all-extras`, then run Python via `uv run ...` (no manual `activate` needed; `uv run` always uses the project venv)
- Run **`uv run pytest`** before commit; for web changes also `cd web && npm test` (and lint/typecheck as needed)
- Read the matching guide under [docs/](docs/) when you touch pipeline, ML, API, or deploy
- Use `--dry-run` on CLIs that support it when outcomes are uncertain

**NEVER**

- Commit to **main** directly (use a branch/PR)
- Hand-edit **web/models/** (training outputs)
- Use **localStorage** / **sessionStorage** in **web** artifacts
- **Trust** ad hoc strings in BigQuery SQL; use operator-only / parameterized patterns (see [src/estate_value_index/utils/bigquery_safety.py](src/estate_value_index/utils/bigquery_safety.py), [docs/data-pipeline.md](docs/data-pipeline.md))

---

## Essential commands

```bash
uv sync --all-extras           # create/update the .venv
uv run pytest                  # run tests (no manual activate needed)
cd web && npm run dev          # app on localhost:3000
```

**Train (typical):** `GCS_ENABLED=false uv run python -m estate_value_index.cli train-production-models --data-source bigquery --model-dir web/models`  
**Pipeline (orchestrated):** e.g. `uv run python -m estate_value_index.pipelines.core.complete_pipeline --quick` (see [docs/data-pipeline.md](docs/data-pipeline.md) and `complete_pipeline --help`)
**Deploy:** `./scripts/deploy_cloud_run.sh` (see [docs/api-web-deploy.md](docs/api-web-deploy.md))

---

## Environment & BigQuery

Required `.env` vars, optional knobs, config precedence, and BigQuery dataset/table names: [docs/data-pipeline.md](docs/data-pipeline.md#environment). Precedence is environment -> [config/pipeline_config.yaml](config/pipeline_config.yaml) -> code defaults.

---

## Key file pointers

| Path | Role |
| ---- | ---- |
| `src/estate_value_index/cli/train_production_models.py` | Production training entry |
| [api_server.py](api_server.py) | FastAPI prediction service |
| `src/estate_value_index/ml/` | Features, loader, training |
| `src/estate_value_index/pipelines/core/complete_pipeline.py` | Main orchestrated pipeline |
| `web/src/app/api/` | Next.js API routes (`runtime = 'nodejs'` where needed) |
| [config/pipeline_config.yaml](config/pipeline_config.yaml) | Thresholds, ingestion defaults |
| [tests/conftest.py](tests/conftest.py) | Shared fixtures |
| [Dockerfile](Dockerfile) / [scripts/startup.sh](scripts/startup.sh) | Container, GCS model sync |

---

## Gotchas

Read the matching guide before editing. The gotchas live with the code they bite:

- **Temporal leakage, feature context, categoricals**: [docs/ml-and-models.md](docs/ml-and-models.md)
- **Models (GCS sync, not baked in image), `GCS_ENABLED` across CI/dev/prod**: [docs/api-web-deploy.md](docs/api-web-deploy.md)

If a doc disagrees with code, fix the doc in the same change.

**Exploration:** [tests/conftest.py](tests/conftest.py).

**Workflow:** search for existing patterns; test incrementally. **Versions:** **uv** (not pip), Python 3.11+, Node 20+, Next.js 15, LightGBM
