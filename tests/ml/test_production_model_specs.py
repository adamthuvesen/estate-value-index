from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from estate_value_index.ml import production_models
from estate_value_index.ml.production_models import (
    LISTING_MODEL_ID,
    NO_LIST_MODEL_ID,
    ProductionModelSpec,
    _validate_production_spec,
    production_specs,
)


def test_default_production_specs_match_asking_price_contracts() -> None:
    no_list, listing = production_specs()

    assert no_list.requires_listing_price is False
    assert listing.requires_listing_price is True


def test_no_list_model_rejects_asking_price_features() -> None:
    spec = ProductionModelSpec(
        model_id=NO_LIST_MODEL_ID,
        feature_set="with_list_price_v1",
        requires_listing_price=False,
    )

    with pytest.raises(ValueError, match="asking-price signals"):
        _validate_production_spec(spec)


def test_listing_model_requires_listing_price_feature() -> None:
    spec = ProductionModelSpec(
        model_id=LISTING_MODEL_ID,
        feature_set="no_list_price_v1",
        requires_listing_price=True,
    )

    with pytest.raises(ValueError, match="must include listing_price"):
        _validate_production_spec(spec)


def test_tuning_runs_once_per_model_and_parameters_are_reused(monkeypatch, tmp_path) -> None:
    raw = pd.DataFrame(
        {
            "sold_date": pd.to_datetime(["2025-01-01", "2025-02-01", "2025-03-01", "2025-04-01"]),
            "sold_price": [4_000_000, 5_000_000, 6_000_000, 7_000_000],
        }
    )
    tuning_calls = []
    fit_calls = []

    monkeypatch.setattr(
        production_models,
        "filter_training_rows",
        lambda frame, *args, **kwargs: frame,
    )
    monkeypatch.setattr(
        production_models,
        "create_temporal_holdout_split",
        lambda frame, **kwargs: (frame.iloc[:2], frame.iloc[2:]),
    )

    def fake_tune(frame, *, spec, random_state):
        tuning_calls.append(spec.model_id)
        return {"num_leaves": 20 if spec.model_id == NO_LIST_MODEL_ID else 30}

    def fake_fit(frame, *, spec, lgbm_params, **kwargs):
        fit_calls.append((spec.model_id, lgbm_params.copy()))

        class Model:
            def predict(self, test_frame):
                return np.full(len(test_frame), 5_000_000.0)

        return Model()

    monkeypatch.setattr(production_models, "tune_production_hyperparameters", fake_tune)
    monkeypatch.setattr(production_models, "fit_tiered_production_model", fake_fit)
    monkeypatch.setattr(production_models, "_prediction_metrics", lambda *args: {"mae": 1.0})
    monkeypatch.setattr(
        production_models,
        "_calibration_report",
        lambda *args, **kwargs: {"served": "uncalibrated"},
    )
    monkeypatch.setattr(production_models, "compute_estimate_range_factors", lambda *args: {})
    monkeypatch.setattr(
        production_models,
        "_metrics_payload",
        lambda *args, lgbm_params, tuned, **kwargs: {
            "training_parameters": {"lightgbm": lgbm_params, "tuned": tuned}
        },
    )
    monkeypatch.setattr(production_models, "persist_production_model", lambda *args, **kwargs: {})

    production_models.train_and_persist_production_models(
        raw_frame=raw,
        model_dir=tmp_path,
        specs=production_specs(),
        tune=True,
    )

    assert tuning_calls == [NO_LIST_MODEL_ID, LISTING_MODEL_ID]
    assert fit_calls == [
        (NO_LIST_MODEL_ID, {"num_leaves": 20}),
        (NO_LIST_MODEL_ID, {"num_leaves": 20}),
        (LISTING_MODEL_ID, {"num_leaves": 30}),
        (LISTING_MODEL_ID, {"num_leaves": 30}),
    ]
