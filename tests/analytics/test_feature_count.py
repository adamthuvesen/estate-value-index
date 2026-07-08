from __future__ import annotations

from pathlib import Path

import pandas as pd

from estate_value_index.analytics import feature_count
from estate_value_index.analytics.residual_calibration import PreparedModelData


def test_run_feature_count_experiment_selects_ranked_top_k(monkeypatch, tmp_path) -> None:
    prepared = PreparedModelData(
        train_engineered=pd.DataFrame(),
        test_engineered=pd.DataFrame(),
        numeric_features=["a", "b", "c"],
        categorical_features=["area"],
        all_features=["a", "b", "c", "area"],
    )
    raw_train = pd.DataFrame({"sold_date": pd.to_datetime(["2026-01-01", "2026-01-02"])})
    raw_test = pd.DataFrame({"sold_date": pd.to_datetime(["2026-02-01"])})
    calls = []

    monkeypatch.setattr(
        feature_count,
        "_load_temporal_raw_split",
        lambda data_file, feature_set: (raw_train, raw_test),
    )
    monkeypatch.setattr(
        feature_count,
        "_prepare_model_data",
        lambda raw_train, raw_test, feature_set: prepared,
    )
    monkeypatch.setattr(
        feature_count,
        "_rank_features",
        lambda prepared, random_state: [
            _ranking_row(1, "b"),
            _ranking_row(2, "area", feature_type="categorical"),
            _ranking_row(3, "a"),
            _ranking_row(4, "c"),
        ],
    )

    def fake_evaluate(prepared, *, random_state, normalized_weight, selected_features):
        calls.append(list(selected_features))
        return {
            "feature_count": len(selected_features),
            "selected_features": list(selected_features),
            "base": _metrics(120.0),
            "normalized": _metrics(110.0),
            "blend": _metrics(100.0 + len(selected_features)),
            "by_price_band": [],
            "by_month": [],
            "by_central_area": [],
        }

    monkeypatch.setattr(feature_count, "_evaluate_prepared_subset", fake_evaluate)

    result = feature_count.run_feature_count_experiment(
        data_file=Path("data.jsonl"),
        feature_set="example_set",
        output_dir=tmp_path,
        feature_counts=(2, 3),
        normalized_weight=0.55,
        random_state=7,
    )

    assert calls == [
        ["a", "b", "c", "area"],
        ["b", "area"],
        ["b", "area", "a"],
    ]
    assert result["evaluations"][0]["selected_features"] == ["b", "area"]
    assert result["evaluations"][1]["selected_features"] == ["b", "area", "a"]
    assert (tmp_path / "example_set_feature_count.json").exists()
    markdown = (tmp_path / "example_set_feature_count.md").read_text(encoding="utf-8")
    assert "Top 2" in markdown
    assert "`area`" in markdown


def test_run_recursive_feature_count_experiment_recomputes_after_each_drop(
    monkeypatch,
    tmp_path,
) -> None:
    prepared = PreparedModelData(
        train_engineered=pd.DataFrame(),
        test_engineered=pd.DataFrame(),
        numeric_features=["a", "b", "c", "d"],
        categorical_features=[],
        all_features=["a", "b", "c", "d"],
    )
    raw_train = pd.DataFrame({"sold_date": pd.to_datetime(["2026-01-01", "2026-01-02"])})
    raw_test = pd.DataFrame({"sold_date": pd.to_datetime(["2026-02-01"])})
    ranked_inputs = []

    monkeypatch.setattr(
        feature_count,
        "_load_temporal_raw_split",
        lambda data_file, feature_set: (raw_train, raw_test),
    )
    monkeypatch.setattr(
        feature_count,
        "_prepare_model_data",
        lambda raw_train, raw_test, feature_set: prepared,
    )

    def fake_rank(prepared, random_state):
        ranked_inputs.append(list(prepared.all_features))
        if prepared.all_features == ["a", "b", "c"]:
            return [_ranking_row(1, "b"), _ranking_row(2, "a"), _ranking_row(3, "c")]
        return [
            _ranking_row(1, "a"),
            _ranking_row(2, "b"),
            _ranking_row(3, "c"),
            _ranking_row(4, "d"),
        ]

    monkeypatch.setattr(feature_count, "_rank_features", fake_rank)
    monkeypatch.setattr(
        feature_count,
        "_evaluate_prepared_subset",
        lambda prepared, *, random_state, normalized_weight, selected_features: {
            "feature_count": len(selected_features),
            "selected_features": list(selected_features),
            "base": _metrics(120.0),
            "normalized": _metrics(110.0),
            "blend": _metrics(100.0 + len(selected_features)),
            "by_price_band": [],
            "by_month": [],
            "by_central_area": [],
        },
    )

    result = feature_count.run_recursive_feature_count_experiment(
        data_file=Path("data.jsonl"),
        feature_set="example_set",
        output_dir=tmp_path,
        feature_counts=(3, 2),
        normalized_weight=0.55,
        random_state=7,
    )

    assert result["evaluations"][0]["selected_features"] == ["a", "b", "c"]
    assert result["evaluations"][1]["selected_features"] == ["b", "a"]
    assert ["a", "b", "c"] in ranked_inputs
    assert (tmp_path / "example_set_feature_count_rfe.json").exists()


def _ranking_row(rank: int, feature: str, *, feature_type: str = "numeric") -> dict[str, object]:
    return {
        "rank": rank,
        "feature": feature,
        "type": feature_type,
        "normalized_importance": 1.0 / rank,
        "raw_importance": float(100 - rank),
    }


def _metrics(mae: float) -> dict[str, float]:
    return {
        "mae": mae,
        "rmse": mae * 2,
        "mape": 0.05,
        "within_10_pct": 80.0,
        "mean_bias": -10.0,
        "median_bias": -5.0,
        "underprediction_rate": 55.0,
    }
