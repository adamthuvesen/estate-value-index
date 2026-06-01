"""CLI package exports.

Subcommand modules are imported lazily so `uv run python -m estate_value_index.cli --help`
does not pay for ML, plotting, or cloud client imports.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "add_backfill_arguments": ("estate_value_index.cli.backfill_booli", "add_arguments"),
    "backfill_main": ("estate_value_index.cli.backfill_booli", "main"),
    "batch_main": ("estate_value_index.cli.batch_scrape", "main"),
    "crawl_main": ("estate_value_index.cli.crawl_booli", "main"),
    "features_main": ("estate_value_index.cli.materialize_features", "main"),
    "migrate_main": ("estate_value_index.cli.migrate_to_bigquery", "main"),
    "costs_main": ("estate_value_index.cli.monitor_costs", "main"),
    "process_main": ("estate_value_index.cli.process_listings", "main"),
    "areas_main": ("estate_value_index.cli.generate_area_statistics", "main"),
    "value_analysis_main": ("estate_value_index.cli.generate_value_analysis", "main"),
    "area_metrics_main": ("estate_value_index.cli.area_performance_metrics", "main"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
