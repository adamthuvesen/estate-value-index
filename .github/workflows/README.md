# GitHub Actions workflows

Three workflows are defined for tests, deployment, and model training.

| Workflow | Trigger | Purpose |
| --- | --- | --- |
| `ci.yml` | Push to `main`, `develop`, or `ml-production-time`; pull request to `main` or `develop` | Python and web checks, plus affected Docker builds |
| `deploy.yml` | Manual | Cloud Run deployment |
| `ml-pipeline.yml` | Manual | Ingestion, local or Vertex AI training, the quality gate, model promotion, and analytics. Deploy with `deploy.yml` |

## CI

The following checks are run by `ci.yml`:

- Python 3.11 dependencies are installed with `uv sync --all-extras`.
- Ruff lint and format checks are run.
- The Python test suite is run with coverage.
- oxlint, the oxfmt format check, Jest, and TypeScript checks are run under `web/`.
- The serving and Vertex AI Dockerfiles are built when affected paths change.

Coverage output is uploaded as the `coverage-report` artifact.

## ML pipeline

`ml-pipeline.yml` is started from `workflow_dispatch`. Each step is one `evi` command:
`backfill --load` (full mode) or `sync`, `train-production-models` or `vertex-train`,
`check-model`, `promote-model` (Vertex modes), the three analytics commands, and
`upload-enrichment` (Vertex modes). A GitHub environment named
`staging` or `production` supplies its cloud configuration.

Modes:

| Mode | Ingestion | Training |
| --- | --- | --- |
| `retrain` | Existing BigQuery data is used | Vertex AI |
| `full` | The authorized source is ingested first | Vertex AI |
| `vertex` | Existing BigQuery data is used | Vertex AI |
| `local` | Existing BigQuery data is used | GitHub runner |

Manual inputs:

| Input | Default | Meaning |
| --- | --- | --- |
| `environment` | `staging` | GitHub environment containing GCP variables and secrets |
| `mode` | `retrain` | Pipeline mode listed above |
| `max_pages` | `5` | Source page limit per sold-date window in `full` mode |
| `start_date` | empty | First sold date in `full` mode; empty uses the `evi backfill` default |
| `config_file` | all-locations Booli config | Ingestion configuration |
| `tune` | `false` | Tune one LightGBM parameter set for each production model |
| `rebuild_container` | `false` | Vertex AI training image rebuild |
| `approved` | `false` | Required for every mode except `local` |

Examples:

```bash
gh workflow run ml-pipeline.yml -f environment=staging -f mode=local -f tune=false
gh workflow run ml-pipeline.yml -f environment=production -f mode=vertex -f tune=true -f approved=true
gh workflow run ml-pipeline.yml -f environment=production -f mode=full -f approved=true
gh workflow run deploy.yml -f environment=production -f approved=true
```

Tuning runs two Optuna studies: one for `no_list_price` and one for
`with_list_price`. Each study reads only that model's temporal training fold.
The selected parameters are then reused for its evaluation, tier, out-of-fold,
and final fits. Expect a tuned run to take longer than the default
fixed-parameter run.

Model promotion is stopped when the MdAPE check fails.

## Cloud Run deployment

`deploy.yml` builds and pushes the serving image, then deploys it to Cloud Run.
Models are downloaded from GCS by `scripts/startup.sh` when the container starts.
The dedicated `evi-cloud-run-runtime@<project>.iam.gserviceaccount.com` runtime
service account is attached to the service.

```bash
gh workflow run deploy.yml -f environment=staging
gh workflow run deploy.yml -f environment=production
```

## Required cloud configuration

The workflows read these GitHub environment variables as needed:

- `GCP_PROJECT_ID`
- `GCP_REGION`
- `GCS_BUCKET`
- `CLOUD_RUN_SERVICE_NAME`
- `BIGQUERY_PROJECT_ID`
- `BIGQUERY_DATASET_RAW`
- `BIGQUERY_TABLE_LISTINGS`
- `BIGQUERY_DATASET_FEATURES`
- `BIGQUERY_TABLE_FEATURES`

These environment secrets are used for Workload Identity Federation:

- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_SERVICE_ACCOUNT`

Two additional environment secrets are required by `ml-pipeline.yml` in `full`
mode:

- `BOOLI_API_CALLER_ID`
- `BOOLI_API_PRIVATE_KEY`

Long-lived service-account JSON keys should not be stored in repository secrets.
The deployer identity needs the permissions named in each workflow header. The
Cloud Run runtime identity is limited to reading its GCS artifacts.

## Troubleshooting

Workflow runs can be inspected with:

```bash
gh workflow list
gh run list --workflow=ci.yml
gh run list --workflow=ml-pipeline.yml
gh run view <run-id>
gh run watch
```

When authentication fails, the selected GitHub environment and its Workload
Identity Federation values should be checked first. Docker build failures should
be traced through the failed build step and the referenced Dockerfile.

## Related documentation

- [Architecture](../../docs/architecture.md)
- [Data pipeline](../../docs/data-pipeline.md)
- [ML and models](../../docs/ml-and-models.md)
- [API, web, and deploy](../../docs/api-web-deploy.md)
- [Repository rules](../../AGENTS.md)
