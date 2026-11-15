"""CLI package entrypoint with unified dispatcher."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module

from pydantic import ValidationError


@dataclass(frozen=True)
class Command:
    help: str
    module: str
    handler: str = "main"
    supports_json: bool = False


_COMMANDS: dict[str, Command] = {
    "backfill": Command(
        "Fetch Booli listings by sold-date window; --load also writes BigQuery",
        "estate_value_index.cli.backfill_booli",
        supports_json=True,
    ),
    "process": Command("Process raw listings", "estate_value_index.cli.process_listings"),
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
    "sync": Command(
        "Copy BigQuery listings to the local production file and check them",
        "estate_value_index.cli.sync_listings",
    ),
    "train-production-models": Command(
        "Train the two production prediction models",
        "estate_value_index.cli.train_production_models",
    ),
    "vertex-train": Command(
        "Train on Vertex AI, wait for the job, and download the artifacts",
        "estate_value_index.cli.vertex_train",
    ),
    "check-model": Command(
        "Fail unless the trained model meets the MdAPE quality gate",
        "estate_value_index.cli.model_release",
        handler="check_main",
    ),
    "promote-model": Command(
        "Copy validated Vertex artifacts to the production GCS path",
        "estate_value_index.cli.model_release",
        handler="promote_main",
    ),
    "upload-enrichment": Command(
        "Upload the derived web JSON files to GCS",
        "estate_value_index.cli.publish_enrichment",
    ),
}


def _load_handler(command_name: str) -> Callable[[list[str] | None], int]:
    command = _COMMANDS[command_name]
    return getattr(import_module(command.module), command.handler)


def _report_invalid_settings(error: ValidationError) -> int:
    unknown = [
        str(issue["loc"][0]).upper()
        for issue in error.errors()
        if issue["type"] == "extra_forbidden"
    ]
    if unknown:
        print(
            f"error: .env has unknown keys: {', '.join(unknown)}. Remove them (see .env.example).",
            file=sys.stderr,
        )
    for issue in error.errors():
        if issue["type"] != "extra_forbidden":
            field = ".".join(str(part) for part in issue["loc"]).upper()
            print(f"error: {field}: {issue['msg']}", file=sys.stderr)
    return 2


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
    try:
        return _load_handler(args.command)(handler_args)
    except ValidationError as error:
        if error.title != "Settings":
            raise
        return _report_invalid_settings(error)


if __name__ == "__main__":
    sys.exit(main())
