"""Top-k feature count experiments."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pandas as pd

from estate_value_index.analytics.market_normalized_target import (
    DEFAULT_DATA_FILE,
    _fit_market_normalized_predictions,
    blend_market_predictions,
)
from estate_value_index.analytics.residual_calibration import (
    PreparedModelData,
    _compare_groups,
    _fit_base_model,
    _fmt_pct,
    _fmt_sek,
    _load_temporal_raw_split,
    _prediction_metrics,
    _prepare_matrices,
    _prepare_model_data,
    _price_band,
)
from estate_value_index.utils.settings import get_random_state

DEFAULT_OUTPUT_DIR = Path("reports/feature_count_experiments")
DEFAULT_FEATURE_COUNTS = (20, 15, 12, 10, 8)


def run_feature_count_experiment(
    *,
    data_file: Path | None = None,
    feature_set: str = "no_list_price_h3_market_street",
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    feature_counts: tuple[int, ...] = DEFAULT_FEATURE_COUNTS,
    normalized_weight: float,
    random_state: int | None = None,
) -> dict[str, object]:
    """Rank features from the full model and test fixed top-k subsets."""
    if not 0.0 <= normalized_weight <= 1.0:
        raise ValueError("normalized_weight must be between 0 and 1")
    if not feature_counts:
        raise ValueError("At least one feature count is required")
    if any(count < 1 for count in feature_counts):
        raise ValueError("feature counts must be positive")

    seed = get_random_state() if random_state is None else random_state
    raw_train, raw_test = _load_temporal_raw_split(data_file, feature_set)
    prepared = _prepare_model_data(raw_train, raw_test, feature_set)

    ranking = _rank_features(prepared, seed)
    baseline = _evaluate_prepared_subset(
        prepared,
        random_state=seed,
        normalized_weight=normalized_weight,
        selected_features=prepared.all_features,
    )
    evaluations = []
    for count in feature_counts:
        selected_features = [row["feature"] for row in ranking[: min(count, len(ranking))]]
        subset = _subset_prepared(prepared, selected_features)
        evaluation = _evaluate_prepared_subset(
            subset,
            random_state=seed,
            normalized_weight=normalized_weight,
            selected_features=selected_features,
        )
        evaluation["feature_count"] = len(selected_features)
        evaluation["requested_feature_count"] = count
        evaluation["selected_features"] = selected_features
        evaluation["delta_vs_full"] = _metric_delta(
            baseline["blend"],
            evaluation["blend"],
        )
        evaluations.append(evaluation)

    result = {
        "metadata": {
            "feature_set": feature_set,
            "data_file": str(data_file or DEFAULT_DATA_FILE),
            "train_rows": int(len(raw_train)),
            "test_rows": int(len(raw_test)),
            "test_start": str(raw_test["sold_date"].min().date()),
            "test_end": str(raw_test["sold_date"].max().date()),
            "normalized_weight": normalized_weight,
            "ranking_source": "full feature-set LightGBM split-model importances",
        },
        "baseline_full": baseline,
        "evaluations": evaluations,
        "feature_ranking": ranking,
    }
    _write_outputs(result, output_dir)
    return result


def run_recursive_feature_count_experiment(
    *,
    data_file: Path | None = None,
    feature_set: str = "no_list_price_h3_market_street",
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    feature_counts: tuple[int, ...] = DEFAULT_FEATURE_COUNTS,
    normalized_weight: float,
    random_state: int | None = None,
) -> dict[str, object]:
    """Run recursive feature elimination to each requested top-k size."""
    if not 0.0 <= normalized_weight <= 1.0:
        raise ValueError("normalized_weight must be between 0 and 1")
    if not feature_counts:
        raise ValueError("At least one feature count is required")
    if any(count < 1 for count in feature_counts):
        raise ValueError("feature counts must be positive")

    seed = get_random_state() if random_state is None else random_state
    raw_train, raw_test = _load_temporal_raw_split(data_file, feature_set)
    prepared = _prepare_model_data(raw_train, raw_test, feature_set)
    baseline = _evaluate_prepared_subset(
        prepared,
        random_state=seed,
        normalized_weight=normalized_weight,
        selected_features=prepared.all_features,
    )

    current_prepared = prepared
    current_ranking = _rank_features(current_prepared, seed)
    evaluations = []
    for count in sorted(set(feature_counts), reverse=True):
        selected_features = [
            row["feature"] for row in current_ranking[: min(count, len(current_ranking))]
        ]
        subset = _subset_prepared(prepared, selected_features)
        evaluation = _evaluate_prepared_subset(
            subset,
            random_state=seed,
            normalized_weight=normalized_weight,
            selected_features=selected_features,
        )
        evaluation["feature_count"] = len(selected_features)
        evaluation["requested_feature_count"] = count
        evaluation["selected_features"] = selected_features
        evaluation["delta_vs_full"] = _metric_delta(
            baseline["blend"],
            evaluation["blend"],
        )
        evaluations.append(evaluation)
        current_prepared = subset
        current_ranking = _rank_features(current_prepared, seed)

    result = {
        "metadata": {
            "feature_set": feature_set,
            "data_file": str(data_file or DEFAULT_DATA_FILE),
            "train_rows": int(len(raw_train)),
            "test_rows": int(len(raw_test)),
            "test_start": str(raw_test["sold_date"].min().date()),
            "test_end": str(raw_test["sold_date"].max().date()),
            "normalized_weight": normalized_weight,
            "selection_method": "recursive_feature_elimination",
            "ranking_source": "LightGBM split-model importances recomputed after each drop",
        },
        "baseline_full": baseline,
        "evaluations": evaluations,
        "feature_ranking": _rank_features(prepared, seed),
    }
    _write_outputs(result, output_dir)
    return result


def _rank_features(prepared: PreparedModelData, random_state: int) -> list[dict[str, object]]:
    fit = _fit_base_model(prepared, random_state)
    X_train, _, _, _ = _prepare_matrices(prepared)
    raw_importance = pd.Series(fit.model.feature_importances_, index=X_train.columns).astype(float)
    total = raw_importance.sum()
    if total > 0:
        normalized = raw_importance / total
    else:
        normalized = raw_importance.copy()
    type_by_feature = {
        **dict.fromkeys(prepared.numeric_features, "numeric"),
        **dict.fromkeys(prepared.categorical_features, "categorical"),
    }
    rows = []
    for rank, (feature, importance) in enumerate(
        normalized.sort_values(ascending=False).items(),
        start=1,
    ):
        rows.append(
            {
                "rank": rank,
                "feature": feature,
                "type": type_by_feature.get(feature, "unknown"),
                "normalized_importance": float(importance),
                "raw_importance": float(raw_importance[feature]),
            }
        )
    return rows


def _subset_prepared(
    prepared: PreparedModelData,
    selected_features: list[str],
) -> PreparedModelData:
    selected = set(selected_features)
    numeric_features = [feature for feature in prepared.numeric_features if feature in selected]
    categorical_features = [
        feature for feature in prepared.categorical_features if feature in selected
    ]
    all_features = numeric_features + categorical_features
    if not all_features:
        raise ValueError("No selected features exist in the prepared data")
    return replace(
        prepared,
        numeric_features=numeric_features,
        categorical_features=categorical_features,
        all_features=all_features,
    )


def _evaluate_prepared_subset(
    prepared: PreparedModelData,
    *,
    random_state: int,
    normalized_weight: float,
    selected_features: list[str],
) -> dict[str, object]:
    base_fit = _fit_base_model(prepared, random_state)
    normalized_fit = _fit_market_normalized_predictions(
        prepared,
        random_state,
        fallback_predictions=base_fit.predictions,
    )
    blended = blend_market_predictions(
        base_fit.predictions,
        normalized_fit.predictions,
        normalized_weight=normalized_weight,
    )
    y_test = prepared.test_engineered["sold_price"].reset_index(drop=True)
    diagnostic_frame = prepared.test_engineered.copy().reset_index(drop=True)
    diagnostic_frame["base_prediction"] = base_fit.predictions
    diagnostic_frame["calibrated_prediction"] = blended
    diagnostic_frame["price_band"] = diagnostic_frame["sold_price"].apply(_price_band)
    diagnostic_frame["sold_month"] = (
        pd.to_datetime(diagnostic_frame["sold_date"]).dt.to_period("M").astype(str)
    )
    diagnostic_frame["central_area"] = diagnostic_frame["area"].isin(
        {"ostermalm", "vasastan", "sodermalm", "kungsholmen"}
    )

    return {
        "feature_count": len(selected_features),
        "selected_features": selected_features,
        "base": _prediction_metrics(y_test, base_fit.predictions),
        "normalized": _prediction_metrics(y_test, normalized_fit.predictions),
        "blend": _prediction_metrics(y_test, blended),
        "market_normalization": {
            "reference_index": normalized_fit.reference_index,
            "normalized_train_rows": normalized_fit.train_rows,
            "fallback_prediction_rows": normalized_fit.fallback_prediction_rows,
        },
        "by_price_band": _compare_groups(diagnostic_frame, "price_band"),
        "by_month": _compare_groups(diagnostic_frame, "sold_month"),
        "by_central_area": _compare_groups(diagnostic_frame, "central_area"),
    }


def _metric_delta(
    baseline: dict[str, float],
    candidate: dict[str, float],
) -> dict[str, float]:
    return {
        "mae": candidate["mae"] - baseline["mae"],
        "rmse": candidate["rmse"] - baseline["rmse"],
        "mape": candidate["mape"] - baseline["mape"],
        "within_10_pct": candidate["within_10_pct"] - baseline["within_10_pct"],
        "mean_bias": candidate["mean_bias"] - baseline["mean_bias"],
        "underprediction_rate": candidate["underprediction_rate"]
        - baseline["underprediction_rate"],
    }


def _write_outputs(result: dict[str, object], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    feature_set = str(result["metadata"]["feature_set"])
    suffix = "feature_count"
    if result["metadata"].get("selection_method") == "recursive_feature_elimination":
        suffix = "feature_count_rfe"
    json_path = output_dir / f"{feature_set}_{suffix}.json"
    markdown_path = output_dir / f"{feature_set}_{suffix}.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown_path.write_text(_to_markdown(result), encoding="utf-8")


def _to_markdown(result: dict[str, object]) -> str:
    metadata = result["metadata"]
    lines = [
        f"# Feature Count Experiment: `{metadata['feature_set']}`",
        "",
        f"Data: `{metadata['data_file']}`",
        f"Split: {metadata['train_rows']:,} train / {metadata['test_rows']:,} test, "
        f"{metadata['test_start']} to {metadata['test_end']}",
        f"Fixed normalized blend weight: `{metadata['normalized_weight']:.2f}`",
        f"Ranking source: {metadata['ranking_source']}",
        "",
        "## Scoreboard",
        _scoreboard_table(result),
        "",
        "## Top Features",
        _feature_table(result["feature_ranking"][:25]),
        "",
        "## Selected Feature Sets",
        _selected_features(result["evaluations"]),
        "",
    ]
    return "\n".join(lines)


def _scoreboard_table(result: dict[str, object]) -> str:
    baseline = result["baseline_full"]
    rows = [("full", baseline, None)] + [
        (
            str(evaluation["feature_count"]),
            evaluation,
            evaluation["delta_vs_full"],
        )
        for evaluation in result["evaluations"]
    ]
    lines = [
        "| Features | MAE | MAE delta | MAPE | Within 10% | Bias | Underpredicted |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for label, evaluation, delta in rows:
        metrics = evaluation["blend"]
        mae_delta = "" if delta is None else _fmt_sek(delta["mae"])
        lines.append(
            "| "
            + " | ".join(
                [
                    label,
                    _fmt_sek(metrics["mae"]),
                    mae_delta,
                    _fmt_pct(metrics["mape"] * 100),
                    _fmt_pct(metrics["within_10_pct"]),
                    _fmt_sek(metrics["mean_bias"]),
                    _fmt_pct(metrics["underprediction_rate"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _feature_table(rows: list[dict[str, object]]) -> str:
    lines = [
        "| Rank | Feature | Type | Importance |",
        "| ---: | --- | --- | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['rank']} | `{row['feature']}` | {row['type']} | "
            f"{row['normalized_importance']:.4f} |"
        )
    return "\n".join(lines)


def _selected_features(evaluations: list[dict[str, object]]) -> str:
    lines = []
    for evaluation in evaluations:
        features = ", ".join(f"`{feature}`" for feature in evaluation["selected_features"])
        lines.append(f"### Top {evaluation['feature_count']}")
        lines.append("")
        lines.append(features)
        lines.append("")
    return "\n".join(lines)
