from types import SimpleNamespace

import pandas as pd

from estate_value_index.cli import train_production_models
from estate_value_index.model_artifacts import LISTING_MODEL_ID, NO_LIST_MODEL_ID


def test_local_training_cli_requests_both_production_models(monkeypatch, tmp_path) -> None:
    raw_frame = pd.DataFrame({"listing_id": ["one"]})
    captured = {}

    monkeypatch.setattr(
        train_production_models,
        "load_raw_training_frame",
        lambda **kwargs: raw_frame,
    )

    def fake_train(**kwargs):
        captured.update(kwargs)
        result = SimpleNamespace(
            metrics={"heldout": {"mae": 1.0, "mape": 2.0, "within_10_pct": 3.0}},
            artifact_paths={},
        )
        return {NO_LIST_MODEL_ID: result, LISTING_MODEL_ID: result}

    monkeypatch.setattr(
        train_production_models,
        "train_and_persist_production_models",
        fake_train,
    )

    exit_code = train_production_models.main(
        ["--data-source", "json", "--data-file", "listings.jsonl", "--model-dir", str(tmp_path)]
    )

    assert exit_code == 0
    assert captured["raw_frame"] is raw_frame
    assert captured["model_dir"] == tmp_path
    assert [spec.model_id for spec in captured["specs"]] == [NO_LIST_MODEL_ID, LISTING_MODEL_ID]
