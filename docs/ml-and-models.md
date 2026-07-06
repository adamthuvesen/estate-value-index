# ML and models

Training uses engineered listing features and LightGBM-based tiered ensembles.
Keep training, feature context, and inference aligned; that contract matters
more than any one helper name.

Private model scoreboards, exact holdout slices, local backfill notes, and
feature-selection research belong under `docs/internal/`. That directory is
intentionally git-ignored.

## Where to work

- Training entrypoint: `train_model.py`
- Training workflow modules: `src/estate_value_index/ml/training_workflow/`
- Feature engineering: `src/estate_value_index/ml/features/`
- Data loading and preprocessing: `src/estate_value_index/ml/data_loader.py`, `src/estate_value_index/ml/preprocessing.py`
- Model serving: `api_server.py`
- Feature subsets: `config/feature_subsets.yaml`

## Training contract

- Use chronological splits for production-oriented evaluation; do not replace
  this with naive random row splits.
- Keep inference feature context aligned with training, especially area
  normalization and categorical handling.
- Use `normalize_area_for_model()` for Booli-style
  `Property - Area - City` area handling.
- Follow the trainer's pandas `category` + LightGBM categorical contract.
- H3 micro-area features must use prior local `price_per_sqm` history only.
  They prefer resolution 10 cells with enough prior sales, then resolution 9,
  then area/global fallbacks.
- H3 comp features add prior adjacent-cell PPSQM and same-size PPSQM fallbacks.
  They must exclude same-day rows during training and use train-fold context for
  holdout/inference.
- Market/economy features come from local CSVs in `data/reference/economy/` and
  use the latest previous month to avoid same-month lookahead. Refresh them with
  `uv run python scripts/fetch_economic_data.py --replace`.
- Feature sets that hide asking price must also exclude same-row
  asking-price-derived features such as `price_per_sqm`,
  `relative_area_price`, `total_cost_per_sqm`, `cost_benefit_ratio`, and
  `efficiency_premium`.
- If production retraining fits on all engineered data, treat holdout metrics as
  bounded evidence. Run a fresh temporal backtest before treating them as live
  generalization evidence.

## Current production models

- Serving uses two production artifacts:
  `price_prediction_model_no_list_price.joblib` and
  `price_prediction_model_with_list_price.joblib`.
- `/predict` defaults to `model: auto`: it uses the `with_list_price` model only
  when a positive `listing_price` is supplied, otherwise it uses the
  `no_list_price` model.
- The `no_list_price` model uses feature set `no_list_price_v1`.
- The `with_list_price` model uses feature set `with_list_price_v1`.
- Both artifacts are `price_tiered_ensemble` models: base price model,
  market-normalized model, and low/mid/high experts with OOF-selected gated
  blending.
- Keep detailed model-quality numbers and feature-selection rationale in
  `docs/internal/`, not the public docs tree.

## Model artifacts

- `web/models/` is generated output, ignored by git, and should not be
  hand-edited.
- Runtime model sync can come from GCS through `scripts/startup.sh`.
- Model integrity uses `.sha256` sidecars; do not bypass those checks casually.

## Checks to run

- General ML changes: `uv run pytest tests/ml tests/test_training.py tests/test_features.py`
- Leakage-sensitive changes: `uv run pytest tests/ml/test_temporal_leakage.py`
- Model serving/integrity: `uv run pytest tests/api/test_model_integrity.py tests/test_api_server.py`
- Feature materialization: `uv run pytest tests/ml/test_feature_materialization.py tests/test_data_loader.py`

## Useful commands

```bash
uv run python -m estate_value_index.cli train-production-models --data-source bigquery
uv run python -m estate_value_index.cli model-suite-experiment
uv run python -m estate_value_index.cli feature-count-experiment --method rfe --feature-set no_list_price_h3_market_street --normalized-weight 0.55 --counts 30 25 20 15 12 10 8
uv run python -m estate_value_index.cli feature-count-experiment --method rfe --feature-set listing_price_h3_market_street --normalized-weight 0.30 --counts 30 25 20 15 12 10 8
```
