"""Tests for the area-performance metrics inverse-log guard."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

# Load the script as a module without importing the project's `scripts/` dir
# (which is not a package and would shadow other scripts at import time).
_SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "estate_value_index"
    / "cli"
    / "area_performance_metrics.py"
)


@pytest.fixture(scope="module")
def area_metrics_module():
    spec = importlib.util.spec_from_file_location(
        "area_performance_metrics_under_test", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_log_space_predictions_get_expm1(area_metrics_module):
    # Median ~ 15 → in log space → expm1 should be applied.
    y_log = np.array([14.5, 15.0, 15.5])
    out = area_metrics_module._maybe_inverse_log(y_log)
    np.testing.assert_allclose(out, np.expm1(y_log))


def test_linear_space_predictions_pass_through(area_metrics_module, capsys):
    # Median ~ 5,000,000 → already in SEK → pass through unchanged.
    y_linear = np.array([4_000_000.0, 5_000_000.0, 6_000_000.0])
    out = area_metrics_module._maybe_inverse_log(y_linear)
    np.testing.assert_array_equal(out, y_linear)

    captured = capsys.readouterr()
    assert "predictions already in linear space" in captured.err
