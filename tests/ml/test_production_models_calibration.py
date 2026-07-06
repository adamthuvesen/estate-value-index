"""Phase 3: predict() applies the residual calibrator only for no_list high predictions."""

from __future__ import annotations

import numpy as np
import pandas as pd

from estate_value_index.ml.production_models import TieredProductionModel


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
        requires_listing_price=(model_id == "listing"),
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
    model = _model(model_id="no_list", calibrator=_StubCalibrator(500_000.0))
    gated = np.array([10_000_000.0, 5_000_000.0])

    out = model._apply_calibration(_engineered(), gated)

    # 10M is above the 8M threshold -> +500k; 5M is below -> untouched
    assert out.tolist() == [10_500_000.0, 5_000_000.0]


def test_no_list_correction_is_clipped() -> None:
    model = _model(model_id="no_list", calibrator=_StubCalibrator(5_000_000.0))
    gated = np.array([10_000_000.0])

    out = model._apply_calibration(_engineered().head(1), gated)

    # 12% of 10M = 1.2M, but the 1M absolute cap is tighter
    assert out.tolist() == [11_000_000.0]


def test_listing_model_is_never_calibrated() -> None:
    model = _model(model_id="listing", calibrator=_StubCalibrator(500_000.0))
    gated = np.array([10_000_000.0, 12_000_000.0])

    out = model._apply_calibration(_engineered(), gated)

    assert out.tolist() == gated.tolist()


def test_no_list_without_calibrator_is_unchanged() -> None:
    model = _model(model_id="no_list", calibrator=None)
    gated = np.array([10_000_000.0])

    out = model._apply_calibration(_engineered().head(1), gated)

    assert out.tolist() == gated.tolist()
