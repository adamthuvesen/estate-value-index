"""CLI smoke tests for estate_value_index.cli module."""

import json
import os
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
    subcommands = ["crawl", "batch", "backfill", "process", "features", "migrate", "costs"]
    for cmd in subcommands:
        result = subprocess.run(
            [sys.executable, "-m", "estate_value_index.cli", cmd, "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Subcommand '{cmd}' help failed"


def test_batch_scrape_dry_run():
    """Verify batch scrape --dry-run works without side effects."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "estate_value_index.cli",
            "batch",
            "--max-pages",
            "1",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "dry_run" in result.stdout.lower() or "dry run" in result.stdout.lower()


def test_batch_scrape_validation_negative_max_pages():
    """Verify negative --max-pages is rejected."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "estate_value_index.cli",
            "batch",
            "--max-pages",
            "-1",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "error" in result.stderr.lower() or "must be" in result.stderr.lower()


def test_batch_scrape_validation_negative_delay():
    """Verify negative --delay is rejected."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "estate_value_index.cli",
            "batch",
            "--delay",
            "-1",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "error" in result.stderr.lower() or "must be" in result.stderr.lower()


def test_batch_scrape_validation_negative_concurrency():
    """Verify negative --concurrency is rejected."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "estate_value_index.cli",
            "batch",
            "--concurrency",
            "0",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "error" in result.stderr.lower() or "must be" in result.stderr.lower()


def test_batch_scrape_exit_code_upload_without_promote():
    """Verify error exit code when upload requested without promote."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "estate_value_index.cli",
            "batch",
            "--upload-bq",
            "--max-pages",
            "1",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "promote" in result.stdout.lower()


def test_batch_scrape_exit_code_invalid_page_range():
    """Verify error exit code when start-page-min > start-page-max."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "estate_value_index.cli",
            "batch",
            "--start-page-min",
            "10",
            "--start-page-max",
            "5",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_monitor_costs_gcs_only_requires_bucket():
    """Verify --gcs-only requires --bucket."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "estate_value_index.cli",
            "costs",
            "--project-id",
            "test-project",
            "--gcs-only",
        ],
        capture_output=True,
        env={**os.environ, "GCS_BUCKET": ""},
        text=True,
    )
    assert result.returncode != 0
    output = (result.stderr + result.stdout).lower()
    assert "bucket" in output or "required" in output


def test_direct_module_entrypoint():
    """Verify direct module entrypoints work."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "estate_value_index.cli.crawl_booli",
            "--help",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_batch_scrape_json_flag():
    """Verify --json flag outputs structured JSON."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "estate_value_index.cli",
            "--json",  # Global flag comes before subcommand
            "batch",
            "--max-pages",
            "1",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert "dry_run" in output
    assert output["dry_run"] is True


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


def test_global_verbose_flag():
    """Verify --verbose flag is accepted."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "estate_value_index.cli",
            "--verbose",
            "batch",
            "--max-pages",
            "1",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
