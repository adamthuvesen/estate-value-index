from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from estate_value_index.ml.training_workflow import runner
from estate_value_index.ml.training_workflow.config import TrainingConfig


def _raw_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "listing_id": ["1", "2"],
            "listing_price": [4_000_000.0, 5_000_000.0],
            "price_per_sqm": [80_000.0, 85_000.0],
            "sold_price": [4_200_000.0, 5_300_000.0],
            "sold_date": pd.to_datetime(["2024-01-01", "2024-02-01"]),
            "living_area": [52.0, 63.0],
            "area": ["Solna", "Solna"],
        }
    )


def test_load_and_split_blocks_materialized_holdout_evaluation(monkeypatch) -> None:
    monkeypatch.setattr(
        runner,
        "load_training_dataframe",
        lambda **kwargs: (_raw_frame(), True),
    )

    with pytest.raises(ValueError, match="Materialized features cannot be used"):
        runner._load_and_split(TrainingConfig(use_materialized_features=True))


def test_no_list_training_masks_ask_signals_before_feature_engineering(monkeypatch) -> None:
    captured: list[pd.DataFrame] = []

    monkeypatch.setattr(
        runner,
        "load_training_dataframe",
        lambda **kwargs: (_raw_frame(), False),
    )
    monkeypatch.setattr(runner, "load_feature_subset", lambda feature_set: (["living_area"], []))
    monkeypatch.setattr(runner, "filter_valid_listings", lambda df, **kwargs: df)
    monkeypatch.setattr(
        runner,
        "create_temporal_holdout_split",
        lambda df, **kwargs: (df.iloc[[0]].copy(), df.iloc[[1]].copy()),
    )

    def capture_features(df: pd.DataFrame, context=None) -> pd.DataFrame:  # noqa: ANN001
        captured.append(df.copy())
        return df.copy()

    monkeypatch.setattr(runner, "create_optimized_features", capture_features)
    monkeypatch.setattr(
        runner,
        "build_feature_context",
        lambda df: SimpleNamespace(
            numeric_fill_values={},
            categorical_fill_values={},
            reference_date=pd.Timestamp("2024-01-01"),
        ),
    )

    runner._load_and_split(TrainingConfig(feature_set="no_list_price_v1"))

    assert captured[0]["listing_price"].isna().all()
    assert captured[0]["price_per_sqm"].isna().all()
    assert captured[1]["listing_price"].isna().all()
    assert captured[1]["price_per_sqm"].isna().all()
