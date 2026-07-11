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


_COMMANDS: dict[str, Command] = {
    "backfill": Command(
        "Backfill Booli listings by sold-date windows",
        "estate_value_index.cli.backfill_booli",
        supports_json=True,
    ),
    "process": Command("Process raw listings", "estate_value_index.cli.process_listings"),
    "features": Command(
        "Materialize features to BigQuery", "estate_value_index.cli.materialize_features"
    ),
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
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands", required=True)

    for name, command in _COMMANDS.items():
        subparsers.add_parser(name, help=command.help, add_help=False)

    args, remaining = parser.parse_known_args(argv)
    command = _COMMANDS[args.command]
    handler_args = list(remaining)
    if args.json and command.supports_json:
        handler_args.insert(0, "--json")
    return _load_handler(args.command)(handler_args)


if __name__ == "__main__":
    sys.exit(main())
