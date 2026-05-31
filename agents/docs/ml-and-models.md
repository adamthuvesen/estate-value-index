# ML and models

Training uses engineered listing features and LightGBM. Keep training, feature context, and inference aligned; that contract matters more than any one helper name.

## Where to work

- Training entrypoint: `train_model.py`
- Training workflow modules: `src/estate_value_index/ml/training_workflow/`
- Feature engineering: `src/estate_value_index/ml/features/`
- Data loading and preprocessing: `src/estate_value_index/ml/data_loader.py`, `src/estate_value_index/ml/preprocessing.py`
- Model serving compatibility: `api_server.py`
- Feature subsets and recommended features: `config/feature_subsets.yaml`, `config/recommended_features.json`

## Training contract

- Use chronological splits for production-oriented evaluation; do not replace this with naive random row splits.
- Keep inference feature context aligned with training, especially area normalization and categorical handling.
- Use `normalize_area_for_model()` for Booli-style `Property - Area - City` area handling.
- Follow the trainer's pandas `category` + LightGBM categorical contract.
- If production retraining fits on all engineered data, keep holdout metrics separate from live generalization claims.

## Model artifacts

- `web/models/` is generated output, ignored by git, and should not be hand-edited.
- Runtime model sync can come from GCS through `scripts/startup.sh`.
- Model integrity uses `.sha256` sidecars; do not bypass those checks casually.
- Pickled legacy compatibility lives in `api_server.py`; be careful when renaming serving classes or import paths.

## Checks to run

- General ML changes: `pytest tests/ml tests/test_training.py tests/test_features.py`
- Leakage-sensitive changes: `pytest tests/ml/test_temporal_leakage.py`
- Model serving/integrity: `pytest tests/api/test_model_integrity.py tests/test_api_server.py`
- Feature materialization: `pytest tests/ml/test_feature_materialization.py tests/test_data_loader.py`
