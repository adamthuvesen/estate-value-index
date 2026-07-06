"""Offline residual calibration proof for the production tiered ``no_list`` model.

Checks whether the residual calibrator inside ``TieredProductionModel`` improves
the served no-list model on the newest temporal holdout. The calibrator must
improve overall MAE, or stay within 10k SEK while improving bias, the
underprediction rate, and high-end (12M+) MAE/bias.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from estate_value_index.analytics.residual_calibration import (
    DEFAULT_DATA_FILE,
    DEFAULT_OUTPUT_DIR,
    _build_result_payload,
    _to_markdown,
)
from estate_value_index.ml import create_temporal_holdout_split
from estate_value_index.ml.production_models import (
    DEFAULT_NO_LIST_FEATURE_SET,
    NO_LIST_MODEL_ID,
    ProductionModelSpec,
    _engineer_for_model,
    filter_training_rows,
    fit_tiered_production_model,
    load_raw_training_frame,
)
from estate_value_index.utils.settings import get_random_state, get_test_size

logger = logging.getLogger(__name__)

REPORT_STEM = "no_list_production_residual_calibration"
HIGH_END_PRICE = 12_000_000.0
MAX_MAE_WORSENING = 10_000.0


def run_production_residual_calibration_experiment(
    *,
    data_file: Path | None = None,
    feature_set: str = DEFAULT_NO_LIST_FEATURE_SET,
    n_splits: int = 3,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    random_state: int | None = None,
) -> dict[str, object]:
    """Calibrate the production tiered ``no_list`` model and report before/after."""
    if n_splits < 2:
        raise ValueError("n_splits must be at least 2")

    seed = get_random_state() if random_state is None else random_state
    raw = load_raw_training_frame(data_source="json", data_file=data_file or DEFAULT_DATA_FILE)
    filtered = filter_training_rows(raw, feature_set)
    raw_train, raw_test = create_temporal_holdout_split(
        filtered,
        test_size=get_test_size(),
        date_column="sold_date",
    )

    spec = ProductionModelSpec(
        model_id=NO_LIST_MODEL_ID,
        feature_set=feature_set,
        requires_listing_price=False,
    )
    # The no_list model fits and attaches the calibrator during training.
    model = fit_tiered_production_model(
        raw_train,
        spec=spec,
        n_splits=n_splits,
        random_state=seed,
    )
    if model.residual_calibrator is None:
        raise RuntimeError("Production no_list model did not attach a residual calibrator")

    test_engineered = _engineer_for_model(raw_test, model)
    eval_test = raw_test.reset_index(drop=True)
    base_predictions = model.predict(eval_test, apply_calibration=False)
    calibrated_predictions = model.predict(eval_test, apply_calibration=True)
    correction = np.asarray(calibrated_predictions, dtype=float) - np.asarray(
        base_predictions, dtype=float
    )

    result = _build_result_payload(
        feature_set=feature_set,
        data_file=data_file or DEFAULT_DATA_FILE,
        raw_train=raw_train,
        raw_test=raw_test,
        base_predictions=base_predictions,
        calibrated_predictions=calibrated_predictions,
        residual_adjustment=correction,
        test_frame=test_engineered,
        oof=pd.DataFrame(index=range(0)),
        n_splits=n_splits,
    )
    result["gate"] = _gate_summary(result)
    _write_report(result, output_dir)
    return result


def _gate_summary(result: dict[str, object]) -> dict[str, object]:
    base = result["base"]
    calibrated = result["calibrated"]
    delta = result["delta"]
    high_end = _price_band_metrics(result, "12M+")

    mae_ok = float(delta["mae"]) <= MAX_MAE_WORSENING
    bias_ok = abs(float(calibrated["mean_bias"])) < abs(float(base["mean_bias"]))
    underprediction_ok = abs(float(calibrated["underprediction_rate"]) - 50.0) <= abs(
        float(base["underprediction_rate"]) - 50.0
    )
    high_end_mae_ok = True
    high_end_bias_ok = True
    if high_end is not None:
        high_end_mae_ok = float(high_end["calibrated_mae"]) <= float(high_end["base_mae"])
        high_end_bias_ok = abs(float(high_end["calibrated_bias"])) <= abs(
            float(high_end["base_bias"])
        )

    checks = {
        "overall_mae": mae_ok,
        "mean_bias_improves": bias_ok,
        "underprediction_toward_50": underprediction_ok,
        "high_end_mae": high_end_mae_ok,
        "high_end_bias": high_end_bias_ok,
    }
    return {
        "checks": checks,
        "mae_delta": float(delta["mae"]),
        "max_mae_worsening": MAX_MAE_WORSENING,
        "passed": all(checks.values()),
    }


def _price_band_metrics(result: dict[str, object], segment: str) -> dict[str, object] | None:
    for row in result.get("by_price_band", []):
        if row["segment"] == segment:
            return row
    return None


def _write_report(result: dict[str, object], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    gate = result["gate"]
    (output_dir / f"{REPORT_STEM}.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    failed = [name for name, ok in gate["checks"].items() if not ok]
    verdict = "PASS" if gate["passed"] else f"FAIL ({', '.join(failed)})"
    gate_line = f"\n## Gate\nMAE delta: {gate['mae_delta']:,.0f} SEK. **{verdict}**\n"
    (output_dir / f"{REPORT_STEM}.md").write_text(
        _to_markdown(result) + gate_line,
        encoding="utf-8",
    )
