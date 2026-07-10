"""CLI package entrypoint with unified dispatcher."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module


@dataclass(frozen=True)
class Command:
    help: str
    module: str
    handler: str = "main"
    supports_json: bool = False
    supports_verbose: bool = False


_COMMANDS: dict[str, Command] = {
    "crawl": Command("Scrape listings from Booli", "estate_value_index.cli.crawl_booli"),
    "batch": Command(
        "Run batch scraping with validation",
        "estate_value_index.cli.batch_scrape",
        supports_json=True,
        supports_verbose=True,
    ),
    "backfill": Command(
        "Backfill Booli listings by sold-date windows",
        "estate_value_index.cli.backfill_booli",
        supports_json=True,
    ),
    "process": Command("Process raw listings", "estate_value_index.cli.process_listings"),
    "features": Command(
        "Materialize features to BigQuery", "estate_value_index.cli.materialize_features"
    ),
    "migrate": Command("Migrate data to BigQuery", "estate_value_index.cli.migrate_to_bigquery"),
    "costs": Command("Monitor GCP costs", "estate_value_index.cli.monitor_costs"),
    "areas": Command(
        "Generate area statistics JSON for the web UI",
        "estate_value_index.cli.generate_area_statistics",
    ),
    "overall-stats": Command(
        "Generate city-wide statistics JSON for the web Stats page",
        "estate_value_index.cli.generate_overall_statistics",
    ),
    "value-analysis": Command(
        "Generate value analysis enrichment JSON",
        "estate_value_index.cli.generate_value_analysis",
    ),
    "area-metrics": Command(
        "Print area-level model performance metrics",
        "estate_value_index.cli.area_performance_metrics",
    ),
    "micro-areas": Command(
        "Generate H3 micro-area premium reports",
        "estate_value_index.cli.micro_areas",
    ),
    "calibration-experiment": Command(
        "Run residual calibration model experiments",
        "estate_value_index.cli.calibration_experiment",
    ),
    "ppsqm-experiment": Command(
        "Run PPSQM target blend experiments",
        "estate_value_index.cli.ppsqm_experiment",
    ),
    "market-normalized-experiment": Command(
        "Run market-normalized target experiments",
        "estate_value_index.cli.market_normalized_experiment",
    ),
    "high-end-weighting-experiment": Command(
        "Run high-end sample weighting experiments",
        "estate_value_index.cli.high_end_weighting_experiment",
    ),
    "specialist-experiment": Command(
        "Run gated high-end specialist experiments",
        "estate_value_index.cli.specialist_experiment",
    ),
    "premium-specialist-experiment": Command(
        "Run premium-over-comp specialist experiments",
        "estate_value_index.cli.premium_specialist_experiment",
    ),
    "tiered-ensemble-experiment": Command(
        "Run tiered low/mid/high ensemble experiments",
        "estate_value_index.cli.tiered_ensemble_experiment",
    ),
    "model-suite-experiment": Command(
        "Run the four-variant model suite experiment",
        "estate_value_index.cli.model_suite_experiment",
    ),
    "feature-count-experiment": Command(
        "Run top-k feature count experiments",
        "estate_value_index.cli.feature_count_experiment",
    ),
    "train-production-models": Command(
        "Train the two production prediction models",
        "estate_value_index.cli.train_production_models",
    ),
}


def _load_handler(command_name: str) -> Callable[[list[str] | None], int]:
    command = _COMMANDS[command_name]
    return getattr(import_module(command.module), command.handler)


def main(argv: list[str] | None = None) -> int:
    """Parse global flags and dispatch subcommand args to the owning module."""
    parser = argparse.ArgumentParser(
        description="Estate Value Index CLI",
        prog="uv run python -m estate_value_index.cli",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output structured JSON instead of human-readable text",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Increase output verbosity",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands", required=True)

    for name, command in _COMMANDS.items():
        subparsers.add_parser(name, help=command.help, add_help=False)

    args, remaining = parser.parse_known_args(argv)
    command = _COMMANDS[args.command]
    handler_args = list(remaining)
    if args.json and command.supports_json:
        handler_args.insert(0, "--json")
    if args.verbose and command.supports_verbose:
        handler_args.insert(0, "--verbose")

    return _load_handler(args.command)(handler_args)


if __name__ == "__main__":
    sys.exit(main())
