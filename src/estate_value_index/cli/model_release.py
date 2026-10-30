"""``evi check-model`` and ``evi promote-model``: the quality gate and the production copy."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from estate_value_index.model_artifacts import (
    DEFAULT_MODEL_PREFIX,
    NO_LIST_MODEL_ID,
    production_artifact_names,
    required_production_artifact_files,
)
from estate_value_index.utils.gcs import promote_model_artifacts
from estate_value_index.utils.settings import get_settings


def model_quality_failures(metrics: dict[str, object], max_median_ape: float) -> list[str]:
    """Return why the metrics fail the MdAPE gate; an empty list means they pass."""
    median_ape = metrics.get("median_ape")
    if not isinstance(median_ape, int | float):
        return ["median_ape is missing from the metrics file"]
    if median_ape > max_median_ape:
        return [f"MdAPE {median_ape:.2%} exceeds the threshold {max_median_ape:.2%}"]
    return []


def check_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="evi check-model",
        description="Fail unless the no_list_price model meets the MdAPE quality gate.",
    )
    parser.add_argument("--model-dir", type=Path, default=Path("web/models"))
    parser.add_argument("--model-prefix", default=DEFAULT_MODEL_PREFIX)
    parser.add_argument(
        "--max-median-ape",
        type=float,
        default=None,
        help="Default: MAX_MEDIAN_APE_THRESHOLD from the settings.",
    )
    args = parser.parse_args(argv)

    threshold = (
        get_settings().max_median_ape_threshold
        if args.max_median_ape is None
        else args.max_median_ape
    )
    metrics_path = (
        args.model_dir / production_artifact_names(NO_LIST_MODEL_ID, args.model_prefix).metrics
    )
    if not metrics_path.exists():
        print(f"Error: metrics file not found: {metrics_path}", file=sys.stderr)
        return 1
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    failures = model_quality_failures(metrics, threshold)
    if failures:
        for failure in failures:
            print(f"Quality gate failed: {failure}", file=sys.stderr)
        return 1
    print(f"Quality gate passed: MdAPE {metrics['median_ape']:.2%} <= {threshold:.2%}")
    return 0


def promote_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="evi promote-model",
        description="Copy validated Vertex artifacts to gs://<bucket>/models/, which serving reads.",
    )
    parser.add_argument("--model-uri", required=True, help="gs:// URI the Vertex trainer wrote to.")
    parser.add_argument("--model-prefix", default=DEFAULT_MODEL_PREFIX)
    parser.add_argument("--approved", action="store_true", help="Allow the production GCS write.")
    args = parser.parse_args(argv)

    promoted = promote_model_artifacts(
        args.model_uri,
        required_production_artifact_files(args.model_prefix),
        approved=args.approved,
    )
    print(json.dumps({"promoted": promoted}, indent=2))
    return 0
