# The `evi` CLI and GitHub Actions are the only orchestrator

Status: accepted (2026-11-12)

The repo had a Prefect layer (about 2.5k lines) that wrapped `gcloud` and shell scripts, and it read script output with regexes. It also had three deploy paths: `deploy.yml`, `scripts/deploy_cloud_run.sh`, and a Prefect deployment flow. We deleted the Prefect layer. Each pipeline step is now an `evi` command, `ml-pipeline.yml` calls them in order, and `deploy.yml` is the one deploy path. Vertex AI is the `vertex_ai/` trainer container plus one submit command, `evi vertex-train`, which reads the job id and model URI from the `gcloud --format=json` response.

## Considered options

- Keep Prefect and fix the regex parsing. Rejected: the flows duplicated what the CLI already did, and three deploy paths could disagree.
- Move to another orchestrator (Airflow, Dagster). Rejected: one repo with five steps and no schedule does not need a server.

## Consequences

- We lose the Prefect UI, retries, and scheduling. A scheduled run now means a GitHub Actions `schedule` trigger. Retries are a rerun of the workflow.
- Every spend or production-write step needs the approval flag in the workflow, and `deploy.yml` needs `approved=true`. Nothing runs these steps without it.
- Adding an orchestrator again means moving the step order out of `ml-pipeline.yml`, so do it only when steps need a long-running scheduler or fan-out.
