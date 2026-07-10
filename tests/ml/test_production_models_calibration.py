"""Phase 3: predict() applies the residual calibrator only for no_list_price high predictions."""

from __future__ import annotations

import numpy as np
import pandas as pd

from estate_value_index.ml.production_models import (
    LISTING_MODEL_ID,
    NO_LIST_MODEL_ID,
    TieredProductionModel,
    _select_blend,
)
from estate_value_index.ml.tiered_ensemble import TierSpec


class _StubCalibrator:
    """Returns a fixed SEK correction per row, standing in for the fitted pipeline."""

    def __init__(self, correction: float) -> None:
        self.correction = correction

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        return np.full(len(features), self.correction, dtype=float)


def _model(*, model_id: str, calibrator: object | None) -> TieredProductionModel:
    return TieredProductionModel(
        model_id=model_id,
        feature_set="fs",
        requires_listing_price=(model_id == LISTING_MODEL_ID),
        numeric_features=[],
        categorical_features=[],
        context=None,
        base_model=None,
        normalized_model=None,
        tier_models={},
        reference_index=0.0,
        market_blend_weight=0.0,
        overall_weights={},
        gated_weights_by_gate={},
        fallback_weights={},
        residual_calibrator=calibrator,
        calibration_min_prediction=8_000_000.0,
    )


def _engineered() -> pd.DataFrame:
    return pd.DataFrame({"living_area": [80.0, 60.0], "area": ["ostermalm", "rasunda"]})


def test_no_list_calibrates_only_high_predictions() -> None:
    model = _model(model_id=NO_LIST_MODEL_ID, calibrator=_StubCalibrator(500_000.0))
    gated = np.array([10_000_000.0, 5_000_000.0])

    out = model._apply_calibration(_engineered(), gated)

    # 10M is above the 8M threshold -> +500k; 5M is below -> untouched
    assert out.tolist() == [10_500_000.0, 5_000_000.0]


def test_no_list_correction_is_clipped() -> None:
    model = _model(model_id=NO_LIST_MODEL_ID, calibrator=_StubCalibrator(5_000_000.0))
    gated = np.array([10_000_000.0])

    out = model._apply_calibration(_engineered().head(1), gated)

    # 12% of 10M = 1.2M, but the 1M absolute cap is tighter
    assert out.tolist() == [11_000_000.0]


def test_listing_model_is_never_calibrated() -> None:
    model = _model(model_id=LISTING_MODEL_ID, calibrator=_StubCalibrator(500_000.0))
    gated = np.array([10_000_000.0, 12_000_000.0])

    out = model._apply_calibration(_engineered(), gated)

    assert out.tolist() == gated.tolist()


def test_no_list_without_calibrator_is_unchanged() -> None:
    model = _model(model_id=NO_LIST_MODEL_ID, calibrator=None)
    gated = np.array([10_000_000.0])

    out = model._apply_calibration(_engineered().head(1), gated)

    assert out.tolist() == gated.tolist()


def test_select_blend_uses_custom_gate_thresholds(monkeypatch) -> None:
    captured = {}
    oof = pd.DataFrame(
        {
            "actual_price": [4_000_000.0, 6_000_000.0, 11_000_000.0],
            "base_prediction": [4_000_000.0, 6_000_000.0, 11_000_000.0],
            "normalized_prediction": [4_000_000.0, 6_000_000.0, 11_000_000.0],
            "low_prediction": [4_000_000.0, 6_000_000.0, 11_000_000.0],
            "mid_prediction": [4_000_000.0, 6_000_000.0, 11_000_000.0],
            "high_prediction": [4_000_000.0, 6_000_000.0, 11_000_000.0],
        }
    )

    monkeypatch.setattr(
        "estate_value_index.ml.production_models._build_oof_training_data",
        lambda *args, **kwargs: oof,
    )
    monkeypatch.setattr(
        "estate_value_index.ml.production_models.select_best_market_blend_weight",
        lambda *args, **kwargs: {"normalized_weight": 0.0},
    )
    monkeypatch.setattr(
        "estate_value_index.ml.production_models.select_best_expert_weights",
        lambda *args, **kwargs: {"weights": {"global": 1.0, "low": 0.0, "mid": 0.0, "high": 0.0}},
    )

    def capture_gated_selection(y_true, predictions, gate_labels, **kwargs):
        captured["gate_labels"] = list(gate_labels)
        return {
            "weights_by_gate": {},
            "segments": {},
            "oof_mae": 0.0,
            "weight_step": 1.0,
            "min_segment_rows": 1,
        }

    monkeypatch.setattr(
        "estate_value_index.ml.production_models.select_gated_expert_weights",
        capture_gated_selection,
    )

    _select_blend(
        pd.DataFrame({"sold_date": pd.to_datetime(["2024-01-01"])}),
        "no_list_price_v1",
        2,
        42,
        (
            TierSpec("low", None, 5_000_000.0),
            TierSpec("mid", 5_000_000.0, 10_000_000.0),
            TierSpec("high", 8_000_000.0, None),
        ),
        1.0,
        1,
        gate_low_max=7_000_000.0,
        gate_high_min=9_000_000.0,
    )

    assert captured["gate_labels"] == ["low", "low", "high"]
