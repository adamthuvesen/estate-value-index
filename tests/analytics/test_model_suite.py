from __future__ import annotations

from pathlib import Path

from estate_value_index.analytics import model_suite


def test_model_suite_defaults_use_compressed_feature_sets() -> None:
    assert model_suite.DEFAULT_NO_LIST_FEATURE_SET == "no_list_price_h3_market_street_rfe25"
    assert model_suite.DEFAULT_LISTING_FEATURE_SET == "listing_price_h3_market_street_aligned30"


def test_run_model_suite_experiment_writes_four_variant_summary(monkeypatch, tmp_path) -> None:
    calls = []

    def fake_simple(*, data_file, feature_set, output_dir, n_splits, random_state):
        calls.append(("simple", feature_set, output_dir, n_splits, random_state))
        return _simple_result(feature_set)

    def fake_max(*, data_file, feature_set, output_dir, n_splits, random_state):
        calls.append(("max", feature_set, output_dir, n_splits, random_state))
        return _max_result(feature_set)

    monkeypatch.setattr(model_suite, "run_market_normalized_experiment", fake_simple)
    monkeypatch.setattr(model_suite, "run_tiered_ensemble_experiment", fake_max)

    result = model_suite.run_model_suite_experiment(
        data_file=Path("data.jsonl"),
        output_dir=tmp_path,
        no_list_feature_set="no_list_price_h3_market_street",
        listing_feature_set="listing_price_h3_market_street",
        n_splits=3,
        random_state=7,
    )

    assert list(result["variants"]) == [
        "no_list_price_simple",
        "no_list_price_max",
        "listing_price_simple",
        "listing_price_max",
    ]
    assert calls == [
        ("simple", "no_list_price_h3_market_street", tmp_path / "experiments", 3, 7),
        ("max", "no_list_price_h3_market_street", tmp_path / "experiments", 3, 7),
        ("simple", "listing_price_h3_market_street", tmp_path / "experiments", 3, 7),
        ("max", "listing_price_h3_market_street", tmp_path / "experiments", 3, 7),
    ]
    assert (tmp_path / "model_suite.json").exists()
    markdown = (tmp_path / "model_suite.md").read_text(encoding="utf-8")
    assert "no_list_price_simple" in markdown
    assert "listing_price_max" in markdown


def _simple_result(feature_set: str) -> dict[str, object]:
    return {
        "metadata": {
            "feature_set": feature_set,
            "train_rows": 100,
            "test_rows": 20,
            "test_start": "2026-01-01",
            "test_end": "2026-02-01",
        },
        "blend": _metrics(100.0),
        "blend_selection": {"normalized_weight": 0.5, "oof_mae": 110.0},
        "by_price_band": [_band("12M+", 2, 200.0)],
    }


def _max_result(feature_set: str) -> dict[str, object]:
    return {
        "metadata": {
            "feature_set": feature_set,
            "train_rows": 100,
            "test_rows": 20,
            "test_start": "2026-01-01",
            "test_end": "2026-02-01",
        },
        "gated_ensemble": _metrics(90.0),
        "blend_selection": {"gated_ensemble": {"oof_mae": 95.0}},
        "gate": {"test_rows_by_gate": {"low": 5, "mid": 10, "high": 5}},
        "by_price_band": [_band("12M+", 2, 180.0)],
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


def _band(segment: str, rows: int, mae: float) -> dict[str, object]:
    return {
        "segment": segment,
        "rows": rows,
        "base_mae": mae + 10,
        "calibrated_mae": mae,
        "mae_delta": -10.0,
        "base_bias": -30.0,
        "calibrated_bias": -20.0,
        "bias_delta": 10.0,
        "base_underprediction_rate": 60.0,
        "calibrated_underprediction_rate": 50.0,
    }
