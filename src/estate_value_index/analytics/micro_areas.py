from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from estate_value_index.ml.features.micro_area import (
    H3_BASE_RESOLUTION,
    H3_FALLBACK_RESOLUTION,
    MICRO_AREA_MIN_PRIOR_COUNT,
    add_h3_cells,
    observed_price_per_sqm,
)

"""Micro-area analysis outputs based on H3 cells."""

DEFAULT_INPUT = Path(
    "data/raw/booli/backfill_full_unfiltered_20260706_36areas/all_dedup_apartments_enriched.jsonl"
)
FALLBACK_INPUT = Path("data/raw/booli/booli_listings_prod.json")
DEFAULT_OUTPUT_DIR = Path("reports/micro_areas")


def load_listing_records(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return pd.DataFrame()

    if path.suffix == ".jsonl":
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        payload = json.loads(text)
        records = payload if isinstance(payload, list) else [payload]
    return pd.DataFrame.from_records(records)


def generate_micro_area_report(
    data_file: Path | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    min_count: int = MICRO_AREA_MIN_PRIOR_COUNT,
) -> dict[str, Any]:
    source = data_file or (DEFAULT_INPUT if DEFAULT_INPUT.exists() else FALLBACK_INPUT)
    df = load_listing_records(source)
    if df.empty:
        raise ValueError(f"No listings found in {source}")

    df = add_h3_cells(df)
    df["price_per_sqm_signal"] = observed_price_per_sqm(df)
    df = df.dropna(subset=["area", "h3_res10", "price_per_sqm_signal"]).copy()
    if df.empty:
        raise ValueError("No listings with area, coordinates, and price_per_sqm signal")

    area_stats = (
        df.groupby("area", observed=True)["price_per_sqm_signal"]
        .agg(area_median_ppsqm="median", area_count="count")
        .reset_index()
    )
    cell_stats = (
        df.groupby(["area", "h3_res10", "h3_res9"], observed=True)["price_per_sqm_signal"]
        .agg(cell_median_ppsqm="median", cell_count="count")
        .reset_index()
    )
    cell_stats = cell_stats.merge(area_stats, on="area", how="left")
    cell_stats["premium_vs_area_pct"] = (
        (cell_stats["cell_median_ppsqm"] / cell_stats["area_median_ppsqm"] - 1.0) * 100
    ).round(1)
    cell_stats = cell_stats.sort_values(["premium_vs_area_pct", "cell_count"], ascending=False)

    eligible = cell_stats[cell_stats["cell_count"] >= min_count].copy()
    top_premiums = eligible.head(50)
    top_discounts = eligible.sort_values(["premium_vs_area_pct", "cell_count"]).head(50)

    area_spread = (
        eligible.groupby("area", observed=True)
        .agg(
            cells=("h3_res10", "count"),
            listings=("cell_count", "sum"),
            median_premium_pct=("premium_vs_area_pct", "median"),
            p10_premium_pct=("premium_vs_area_pct", lambda s: s.quantile(0.1)),
            p90_premium_pct=("premium_vs_area_pct", lambda s: s.quantile(0.9)),
        )
        .reset_index()
    )
    area_spread["spread_p90_p10_pct"] = (
        area_spread["p90_premium_pct"] - area_spread["p10_premium_pct"]
    ).round(1)
    area_spread = area_spread.sort_values("spread_p90_p10_pct", ascending=False)

    output_dir.mkdir(parents=True, exist_ok=True)
    cell_stats.to_csv(output_dir / "micro_area_cells.csv", index=False)
    top_premiums.to_csv(output_dir / "top_micro_area_premiums.csv", index=False)
    top_discounts.to_csv(output_dir / "top_micro_area_discounts.csv", index=False)
    area_spread.to_csv(output_dir / "area_micro_area_spread.csv", index=False)

    summary = {
        "source": str(source),
        "rows": int(len(df)),
        "h3_base_resolution": H3_BASE_RESOLUTION,
        "h3_fallback_resolution": H3_FALLBACK_RESOLUTION,
        "min_count": int(min_count),
        "cells": int(len(cell_stats)),
        "eligible_cells": int(len(eligible)),
        "eligible_listing_rows": int(eligible["cell_count"].sum()) if not eligible.empty else 0,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "README.md").write_text(
        _report_markdown(summary, top_premiums, top_discounts, area_spread),
        encoding="utf-8",
    )
    return summary


def _report_markdown(
    summary: dict[str, Any],
    top_premiums: pd.DataFrame,
    top_discounts: pd.DataFrame,
    area_spread: pd.DataFrame,
) -> str:
    lines = [
        "# H3 Micro-Area Report",
        "",
        f"Source: `{summary['source']}`",
        f"Rows with usable area, coordinates, and price signal: {summary['rows']:,}",
        f"H3 resolution: {summary['h3_base_resolution']} with min_count={summary['min_count']}",
        f"Eligible cells: {summary['eligible_cells']:,} / {summary['cells']:,}",
        "",
        "## Top Premium Cells",
        "",
        _markdown_table(
            top_premiums,
            [
                "area",
                "h3_res10",
                "cell_count",
                "cell_median_ppsqm",
                "area_median_ppsqm",
                "premium_vs_area_pct",
            ],
        ),
        "",
        "## Top Discount Cells",
        "",
        _markdown_table(
            top_discounts,
            [
                "area",
                "h3_res10",
                "cell_count",
                "cell_median_ppsqm",
                "area_median_ppsqm",
                "premium_vs_area_pct",
            ],
        ),
        "",
        "## Areas With Largest Micro-Area Spread",
        "",
        _markdown_table(
            area_spread.head(50),
            [
                "area",
                "cells",
                "listings",
                "p10_premium_pct",
                "p90_premium_pct",
                "spread_p90_p10_pct",
            ],
        ),
        "",
    ]
    return "\n".join(lines)


def _markdown_table(df: pd.DataFrame, columns: list[str]) -> str:
    if df.empty:
        return "_No rows._"

    df = df[columns].copy()
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for _, row in df.iterrows():
        values = []
        for column in columns:
            value = row[column]
            if isinstance(value, float):
                values.append(f"{value:.1f}" if not value.is_integer() else str(int(value)))
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)
