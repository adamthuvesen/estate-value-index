"""Train and persist the two production prediction models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from estate_value_index.ml.production_models import (
    DEFAULT_LISTING_FEATURE_SET,
    DEFAULT_MODEL_PREFIX,
    DEFAULT_NO_LIST_FEATURE_SET,
    load_raw_training_frame,
    production_specs,
    train_and_persist_production_models,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train the two production model artifacts")
    parser.add_argument(
        "--data-source",
        choices=["json", "bigquery"],
        default="bigquery",
        help="Training data source.",
    )
    parser.add_argument("--data-file", type=Path, default=None)
    parser.add_argument("--model-dir", type=Path, default=Path("web/models"))
    parser.add_argument("--model-prefix", default=DEFAULT_MODEL_PREFIX)
    parser.add_argument("--no-list-feature-set", default=DEFAULT_NO_LIST_FEATURE_SET)
    parser.add_argument("--listing-feature-set", default=DEFAULT_LISTING_FEATURE_SET)
    parser.add_argument("--n-splits", type=int, default=4)
    parser.add_argument(
        "--tune",
        action="store_true",
        help="Tune one LightGBM parameter set per production model before fitting the ensemble.",
    )
    parser.add_argument("--random-state", type=int, default=None)
    parser.add_argument("--summary", type=Path, default=None)
    args = parser.parse_args(argv)

    specs = production_specs(
        no_list_feature_set=args.no_list_feature_set,
        listing_feature_set=args.listing_feature_set,
    )
    raw_frame = load_raw_training_frame(data_source=args.data_source, data_file=args.data_file)
    results = train_and_persist_production_models(
        raw_frame=raw_frame,
        model_dir=args.model_dir,
        model_prefix=args.model_prefix,
        specs=specs,
        n_splits=args.n_splits,
        random_state=args.random_state,
        tune=args.tune,
    )

    summary = {
        model_id: {
            "metrics": result.metrics,
            "artifacts": result.artifact_paths,
        }
        for model_id, result in results.items()
    }
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    for model_id, result in results.items():
        heldout = result.metrics["heldout"]
        print(
            f"{model_id}: MAE {heldout['mae']:,.0f} SEK; "
            f"MAPE {heldout['mape']:.2f}%; "
            f"within 10% {heldout['within_10_pct']:.2f}%"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
