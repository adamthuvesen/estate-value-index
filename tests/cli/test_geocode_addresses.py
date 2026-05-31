"""Tests for geocode_addresses CLI."""

from __future__ import annotations

import pytest

from estate_value_index.cli.geocode_addresses import main


@pytest.mark.unit
def test_main_invalid_project_id_exits_cleanly(capsys: pytest.CaptureFixture[str]) -> None:
    """Malformed --project-id fails with a message, not a traceback."""
    code = main(["--project-id", "foo;DROP TABLE", "--dry-run"])
    assert code == 1
    out = capsys.readouterr().out
    err = capsys.readouterr().err
    assert "invalid GCP project_id" in out
    assert "Traceback" not in out + err
