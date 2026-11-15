from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from estate_value_index.ml.features import pipeline as pipeline_module
from estate_value_index.ml.features.context import FeatureEngineeringContext
from estate_value_index.ml.features.pipeline import SimplePredictionPipeline


class _SumModel:
    def predict(self, features: pd.DataFrame) -> np.ndarray:
        return features["size"].to_numpy(dtype=float)


def test_predict_accepts_feature_names_given_as_a_tuple_and_a_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engineered = pd.DataFrame({"size": [0.0, 1.0], "kind": ["a", "b"]})
    monkeypatch.setattr(
        pipeline_module, "create_optimized_features", lambda frame, context: engineered
    )
    pipeline = SimplePredictionPipeline(
        _SumModel(),
        numeric_features=("size",),
        categorical_features=["kind"],
        context=FeatureEngineeringContext.__new__(FeatureEngineeringContext),
    )
    monkeypatch.setattr(pipeline, "_fill_missing_values", lambda features: features)

    predictions = pipeline.predict(pd.DataFrame({"raw": [1, 2]}))

    assert predictions == pytest.approx(np.expm1([0.0, 1.0]))
