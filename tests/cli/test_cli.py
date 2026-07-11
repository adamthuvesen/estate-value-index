"""CLI smoke tests for estate_value_index.cli module."""

import json
import subprocess
import sys


def test_cli_help():
    """Verify main CLI help works."""
    result = subprocess.run(
        [sys.executable, "-m", "estate_value_index.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "subcommands" in result.stdout.lower() or "commands" in result.stdout.lower()


def test_cli_subcommands_help():
    """Verify each subcommand shows help."""
    subcommands = ["backfill", "process", "features"]
    for cmd in subcommands:
        result = subprocess.run(
            [sys.executable, "-m", "estate_value_index.cli", cmd, "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Subcommand '{cmd}' help failed"


def test_backfill_dry_run_json_flag():
    """Verify backfill works through the unified dispatcher."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "estate_value_index.cli",
            "--json",
            "backfill",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-01-02",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["dry_run"] is True
    assert output["windows"] == [{"start": "2026-01-01", "end": "2026-01-02"}]
