---
name: verify-estate-value-index
description: "Drives the real evi CLI and the api_server ASGI app (train, serve, derived JSON, spend refusal) on seeded synthetic listings in a temp copy. Use to run, launch, drive, or verify estate-value-index, or to prove a change to it works."
---

# Verify estate-value-index

`verify` copies the checkout to a temp dir and runs the real `evi` CLI and `api_server` there with `sys.executable` and a temp HOME. Nothing reaches GCP, BigQuery, Vertex, Cloud Run, or Booli. Tripwire shims for `gcloud`, `gsutil`, `bq`, `docker`, and `curl` lead PATH and fail a drive that calls them. HTTP proxies point at a dead port, and `NO_GCE_CHECK` stops credential probing.

## Run

From the repo root, after `uv sync --all-extras` and `npm ci --prefix web`:

- `just verify` runs the drives whose paths match changed files, or `spend-refusal` when none match.
- `just verify all` runs every drive. It takes about 20 s and must stay under 60 s.
- `just verify list` shows each drive, what it proves, and the paths it covers.
- `just verify train serve` runs named drives.
- `just verify control` plants one defect (the data fingerprint counts one row too many) in a temp copy. It passes only when the `train` drive fails with exactly that text.

## Drives

| Drive | Asserts |
| --- | --- |
| `train` | `train-production-models --data-source json` writes both models with sidecar, context, metrics, and importance files. The sidecar matches the model bytes. Metrics carry the package version, a commit SHA, and a data fingerprint whose row count equals the fixture's. |
| `serve` | `/health` reports both models, their versions, and the training fingerprints. Predict returns a plausible SEK value and a typed `estimate_range_factors`. Three malformed requests return 422. An artifact with no version stamp, or the wrong one, is not loaded and `/health` returns 503. |
| `analytics` | `value-analysis`, `areas`, and `overall-stats` write files that validate against `analytics/web_json.py`. `just types-check` reports the generated TypeScript types current. |
| `spend-refusal` | Without `--approved`, the BigQuery load (`backfill --load`), `vertex-train`, `promote-model`, `sync`, `upload-enrichment`, and train with GCS enabled each raise `ApprovalRequired`, the exception imported from `utils/approval.py`. The train case creates no model dir. One real process exits non-zero with only stderr. `vertex_ai/build_and_push.sh` without `--approved` prints a refusal and exits non-zero before it reaches `gcloud`. |

`serve` and `analytics` read the models that `train` made in the same run. They fail, never skip, when training fails.

## Reading results

Each drive prints `PASS|FAIL <drive> <seconds>s <detail>`. A FAIL detail names the expected and the actual value, the command and its exit code, or the tripwire hit. The run ends with `evidence: .verify/runs/<utc>-<sha7>[-dirty]/`, which holds one `<drive>.<step>.json` per command (argv, env, exit, stdout, stderr) and `summary.json`. A run that changes the real checkout adds `FAIL checkout`. A drive that exits the run early, or a probe that prints no `PROBE_RESULT` line, fails. The helper never retries.

## Fixtures

`fixtures.py` generates 400 synthetic listings with `random.Random(20261112)`. The values are made up. Never commit real listings: the repo is public. The generator writes the BigQuery raw-listing columns from `schemas/bq_raw_listings.json`. Every row passes the training filters, so the fingerprint row count equals 400.

## Limits and gotchas

- Tripwires catch PATH commands only. Python clients fail on the dead proxy and the missing credentials.
- `train` uses `--n-splits 2` to stay fast. The default is 4.
- `spend-refusal` asserts the exception type, not the message wording. `utils/approval.py` has no token constant, so the type is the stable token.
- The skill's Python is type-checked as its own project: `just check` runs `basedpyright -p .agents/skills/verify-estate-value-index/pyrightconfig.json` and passes the extensionless `verify` to ruff by name.
