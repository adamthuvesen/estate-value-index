from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from estate_value_index.cli.model_release import check_main
from estate_value_index.model_artifacts import NO_LIST_MODEL_ID, production_artifact_names


def _write_metrics(model_dir: Path, metrics: dict[str, Any]) -> None:
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / production_artifact_names(NO_LIST_MODEL_ID).metrics).write_text(
        json.dumps(metrics)
    )


def test_check_model_passes_under_the_threshold(tmp_path: Path) -> None:
    _write_metrics(tmp_path, {"median_ape": 0.05})
    assert check_main(["--model-dir", str(tmp_path)]) == 0


@pytest.mark.parametrize("metrics", [{"median_ape": 0.09}, {"mae": 1.0}])
def test_check_model_fails_over_the_threshold_or_without_mdape(
    tmp_path: Path, metrics: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    _write_metrics(tmp_path, metrics)
    assert check_main(["--model-dir", str(tmp_path)]) == 1
    assert "Quality gate failed" in capsys.readouterr().err


def test_check_model_fails_without_a_metrics_file(tmp_path: Path) -> None:
    assert check_main(["--model-dir", str(tmp_path)]) == 1
