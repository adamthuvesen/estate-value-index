# AGENTS.md

**estate-value-index** predicts Swedish real estate values: authorized listing
ingestion -> BigQuery -> LightGBM -> Next.js + FastAPI. Python 3.11+ via
**uv**; Node 20+ for `web/`; Next.js 16; Prefect 3.

This file is project facts only. Tone, principles, and git etiquette live in
the user-level `~/.claude/CLAUDE.md` and `~/dotfiles/agents/AGENTS.md`.

## Read next

Read the matching guide before touching that part of the system:

- [docs/architecture.md](docs/architecture.md): system shape, entry points, dependency direction, conventions
- [docs/data-pipeline.md](docs/data-pipeline.md): ingestion, BigQuery, environment vars, leakage rules
- [docs/ml-and-models.md](docs/ml-and-models.md): training contract, feature context, model artifacts
- [docs/api-web-deploy.md](docs/api-web-deploy.md): FastAPI, Next.js routes, container, Cloud Run

`docs/internal/` (git-ignored) holds model metrics, experiment reports, and
research notes. Put performance numbers and experiment results there, never in
the public docs tree. Index: `docs/internal/README.md`. The root `reports/`
directory (git-ignored) holds historical raw experiment artifacts; the
writeups live in `docs/internal/experiments/`.

## Rules

- Run Python via `uv run ...` after `uv sync --all-extras`. Never pip, never manual activate.
- Run `uv run pytest` before commit; `cd web && npm test` for web changes.
- Never commit to `main` directly; branch and PR.
- Never hand-edit `web/models/` (generated training output).
- Never use `localStorage` / `sessionStorage` in web code.
- Never interpolate ad hoc strings into BigQuery SQL. Use the parameterized /
  operator-only patterns in [src/estate_value_index/utils/bigquery_safety.py](src/estate_value_index/utils/bigquery_safety.py).
- Respect `sold_date` chronology: temporal splits for evaluation, no future
  rows in aggregates. Check: `uv run pytest tests/ml/test_temporal_leakage.py`.
- Use `--dry-run` on CLIs that support it when the outcome is uncertain.
- If a doc disagrees with code, fix the doc in the same change.

## Commands

```bash
uv sync --all-extras             # create/update the .venv
uv run pytest                    # tests
cd web && npm run dev            # app on localhost:3000
./scripts/deploy_cloud_run.sh    # deploy (see docs/api-web-deploy.md)
```

Typical local training:

```bash
GCS_ENABLED=false uv run python -m estate_value_index.cli train-production-models \
  --data-source bigquery --model-dir web/models
```

Add `--tune` only when parameter search is wanted. It runs one Optuna study per
production model and takes longer than routine retraining.

Orchestrated pipeline: `uv run python -m estate_value_index.pipelines.core.complete_pipeline --quick`
(see `--help` and [docs/data-pipeline.md](docs/data-pipeline.md)).

Config precedence: environment -> [config/pipeline_config.yaml](config/pipeline_config.yaml)
-> code defaults. Required env vars: [docs/data-pipeline.md](docs/data-pipeline.md#environment).

## Where things live

- Entry points, boundaries, and the full module map: [docs/architecture.md](docs/architecture.md)
- FastAPI prediction service: [api_server.py](api_server.py)
- ML (features, loading, training): `src/estate_value_index/ml/`
- Shared test fixtures (start here for exploration): [tests/conftest.py](tests/conftest.py)
- Container and GCS model sync: [Dockerfile](Dockerfile), [scripts/startup.sh](scripts/startup.sh)

## Gotchas

The traps live with the code they bite; the guides carry the detail:

- Temporal leakage, feature context, categorical handling: [docs/ml-and-models.md](docs/ml-and-models.md)
- Models sync from GCS at startup (not baked into the image); `GCS_ENABLED`
  differs across CI/dev/prod: [docs/api-web-deploy.md](docs/api-web-deploy.md)
