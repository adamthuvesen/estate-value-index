"""Four-variant model suite experiments."""

from __future__ import annotations

import json
from pathlib import Path

from estate_value_index.ml.market_normalized_target import (
    DEFAULT_DATA_FILE,
    run_market_normalized_experiment,
)
from estate_value_index.ml.residual_calibration import _fmt_pct, _fmt_sek
from estate_value_index.ml.tiered_ensemble import run_tiered_ensemble_experiment
from estate_value_index.utils.settings import get_random_state

DEFAULT_OUTPUT_DIR = Path("reports/model_suite_experiments")
DEFAULT_NO_LIST_FEATURE_SET = "no_list_price_v1"
DEFAULT_LISTING_FEATURE_SET = "with_list_price_v1"


def run_model_suite_experiment(
    *,
    data_file: Path | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    no_list_feature_set: str = DEFAULT_NO_LIST_FEATURE_SET,
    listing_feature_set: str = DEFAULT_LISTING_FEATURE_SET,
    n_splits: int = 4,
    random_state: int | None = None,
) -> dict[str, object]:
    """Run simple and max variants for both listing-price availability modes."""
    if n_splits < 2:
        raise ValueError("n_splits must be at least 2")

    output_dir.mkdir(parents=True, exist_ok=True)
    experiment_dir = output_dir / "experiments"
    seed = get_random_state() if random_state is None else random_state

    no_list_simple = run_market_normalized_experiment(
        data_file=data_file,
        feature_set=no_list_feature_set,
        output_dir=experiment_dir,
        n_splits=n_splits,
        random_state=seed,
    )
    no_list_max = run_tiered_ensemble_experiment(
        data_file=data_file,
        feature_set=no_list_feature_set,
        output_dir=experiment_dir,
        n_splits=n_splits,
        random_state=seed,
    )
    listing_simple = run_market_normalized_experiment(
        data_file=data_file,
        feature_set=listing_feature_set,
        output_dir=experiment_dir,
        n_splits=n_splits,
        random_state=seed,
    )
    listing_max = run_tiered_ensemble_experiment(
        data_file=data_file,
        feature_set=listing_feature_set,
        output_dir=experiment_dir,
        n_splits=n_splits,
        random_state=seed,
    )

    result = {
        "metadata": {
            "data_file": str(data_file or DEFAULT_DATA_FILE),
            "output_dir": str(output_dir),
            "n_splits": n_splits,
            "random_state": seed,
            "no_list_feature_set": no_list_feature_set,
            "listing_feature_set": listing_feature_set,
        },
        "variants": {
            "no_list_price_simple": _simple_variant(no_list_simple),
            "no_list_price_max": _max_variant(no_list_max),
            "listing_price_simple": _simple_variant(listing_simple),
            "listing_price_max": _max_variant(listing_max),
        },
        "source_reports": {
            "no_list_price_simple": _report_paths(
                experiment_dir, no_list_feature_set, "market_normalized"
            ),
            "no_list_price_max": _report_paths(
                experiment_dir, no_list_feature_set, "tiered_ensemble"
            ),
            "listing_price_simple": _report_paths(
                experiment_dir, listing_feature_set, "market_normalized"
            ),
            "listing_price_max": _report_paths(
                experiment_dir, listing_feature_set, "tiered_ensemble"
            ),
        },
    }
    _write_outputs(result, output_dir)
    return result


def _simple_variant(result: dict[str, object]) -> dict[str, object]:
    metrics = result["blend"]
    return {
        "kind": "simple",
        "feature_set": result["metadata"]["feature_set"],
        "train_rows": result["metadata"]["train_rows"],
        "test_rows": result["metadata"]["test_rows"],
        "test_start": result["metadata"]["test_start"],
        "test_end": result["metadata"]["test_end"],
        "metrics": metrics,
        "blend_selection": result["blend_selection"],
        "price_bands": result["by_price_band"],
    }


def _max_variant(result: dict[str, object]) -> dict[str, object]:
    metrics = result["gated_ensemble"]
    return {
        "kind": "max",
        "feature_set": result["metadata"]["feature_set"],
        "train_rows": result["metadata"]["train_rows"],
        "test_rows": result["metadata"]["test_rows"],
        "test_start": result["metadata"]["test_start"],
        "test_end": result["metadata"]["test_end"],
        "metrics": metrics,
        "blend_selection": result["blend_selection"],
        "gate": result["gate"],
        "price_bands": result["by_price_band"],
    }


def _report_paths(output_dir: Path, feature_set: str, suffix: str) -> dict[str, str]:
    stem = output_dir / f"{feature_set}_{suffix}"
    return {
        "json": str(stem.with_suffix(".json")),
        "markdown": str(stem.with_suffix(".md")),
    }


def _write_outputs(result: dict[str, object], output_dir: Path) -> None:
    json_path = output_dir / "model_suite.json"
    markdown_path = output_dir / "model_suite.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown_path.write_text(_to_markdown(result), encoding="utf-8")


def _to_markdown(result: dict[str, object]) -> str:
    metadata = result["metadata"]
    lines = [
        "# Model Suite Experiment",
        "",
        f"Data: `{metadata['data_file']}`",
        f"No-list feature set: `{metadata['no_list_feature_set']}`",
        f"Listing-aware feature set: `{metadata['listing_feature_set']}`",
        f"OOF splits: `{metadata['n_splits']}`",
        "",
        "## Scoreboard",
        _scoreboard_table(result["variants"]),
        "",
        "## High-End Slice",
        _high_end_table(result["variants"]),
        "",
        "## Source Reports",
        _source_report_table(result["source_reports"]),
        "",
    ]
    return "\n".join(lines)


def _scoreboard_table(variants: dict[str, object]) -> str:
    lines = [
        "| Variant | Kind | Train | Test | MAE | MAPE | Within 10% | Bias | Underpredicted |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, variant in variants.items():
        metrics = variant["metrics"]
        lines.append(
            "| "
            + " | ".join(
                [
                    name,
                    variant["kind"],
                    f"{variant['train_rows']:,}",
                    f"{variant['test_rows']:,}",
                    _fmt_sek(metrics["mae"]),
                    _fmt_pct(metrics["mape"] * 100),
                    _fmt_pct(metrics["within_10_pct"]),
                    _fmt_sek(metrics["mean_bias"]),
                    _fmt_pct(metrics["underprediction_rate"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _high_end_table(variants: dict[str, object]) -> str:
    lines = [
        "| Variant | 12M+ rows | 12M+ MAE | 12M+ bias | 12M+ underpredicted |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, variant in variants.items():
        high_end = _price_band(variant, "12M+")
        if high_end is None:
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    name,
                    f"{high_end['rows']:,}",
                    _fmt_sek(high_end["calibrated_mae"]),
                    _fmt_sek(high_end["calibrated_bias"]),
                    _fmt_pct(high_end["calibrated_underprediction_rate"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _source_report_table(reports: dict[str, dict[str, str]]) -> str:
    lines = [
        "| Variant | Markdown | JSON |",
        "| --- | --- | --- |",
    ]
    for name, paths in reports.items():
        lines.append(f"| {name} | `{paths['markdown']}` | `{paths['json']}` |")
    return "\n".join(lines)


def _price_band(variant: dict[str, object], segment: str) -> dict[str, object] | None:
    for row in variant["price_bands"]:
        if row["segment"] == segment:
            return row
    return None
