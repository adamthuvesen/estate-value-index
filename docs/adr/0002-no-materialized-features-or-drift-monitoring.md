# Delete materialized features and drift monitoring

Status: accepted (2026-11-12)

Production training hard-coded `use_materialized_features=False`, so the materialized-features layer (about 1.6k lines) ran nowhere in production. Drift monitoring (about 670 lines) ran on a schedule that was disabled. We deleted both (commit `a6956f6`). Features are computed in one place, `ml/features/`, for training and serving alike.

## Considered options

- Enable the materialized path. Rejected: a second feature path means train/serve skew, the failure this repo guards against most.
- Keep the code disabled. Rejected: dead code that nobody runs drifts from the live path and misleads agents.

## Consequences

- No automated drift signal exists. The quality gate `evi check-model` (MdAPE threshold) and a fresh temporal backtest are the only checks on model quality.
- If drift monitoring is wanted, build it on the shared feature code in `ml/features/`. Do not add a second feature path. Git history holds the old code.
