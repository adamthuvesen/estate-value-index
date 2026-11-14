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
    subcommands = ["backfill", "process", "areas"]
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


def test_unknown_env_keys_print_one_line_and_exit_2(tmp_path, monkeypatch, capsys):
    from estate_value_index.cli.__main__ import main
    from estate_value_index.utils.settings import Settings

    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    (tmp_path / ".env").write_text("BIGQUERY_DATASET_FEATURES=a\nBIGQUERY_TABLE_FEATURES=b\n")
    monkeypatch.chdir(tmp_path)

    assert main(["sync"]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "error: .env has unknown keys: BIGQUERY_DATASET_FEATURES, BIGQUERY_TABLE_FEATURES. "
        "Remove them (see .env.example).\n"
    )


def test_invalid_env_value_prints_one_line_per_field(tmp_path, monkeypatch, capsys):
    from estate_value_index.cli.__main__ import main
    from estate_value_index.utils.settings import Settings

    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    monkeypatch.setenv("GCS_ENABLED", "maybe")
    monkeypatch.chdir(tmp_path)

    assert main(["sync"]) == 2

    err = capsys.readouterr().err
    assert err.startswith("error: GCS_ENABLED: ")
    assert err.count("\n") == 1
