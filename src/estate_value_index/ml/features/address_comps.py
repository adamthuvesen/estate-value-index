"""Street and address prior comp features."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from estate_value_index.ml.features.context import FeatureEngineeringContext
from estate_value_index.ml.features.micro_area import (
    MICRO_AREA_SOURCE_COLUMN,
    SIZE_BAND_COLUMN,
    _size_band,
    observed_price_per_sqm,
)
from estate_value_index.ml.features.utils import _safe_divide

STREET_AREA_MIN_PRIOR_COUNT = 5
STREET_SIZE_MIN_PRIOR_COUNT = 3
ADDRESS_MIN_PRIOR_COUNT = 3
ADDRESS_STAT_COLUMNS = ("median", "p75", "p90", "count")


def normalize_street_name(address: object) -> str:
    """Extract a stable street-level key from a Booli address string."""
    if not isinstance(address, str):
        return "unknown"

    value = " ".join(address.lower().strip().split())
    if not value:
        return "unknown"

    value = re.sub(r"\s+\d+\w?(?:[-/]\d+\w?)?.*$", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or "unknown"


def normalize_address_key(address: object) -> str:
    if not isinstance(address, str):
        return "unknown"
    value = " ".join(address.lower().strip().split())
    return value or "unknown"


def create_address_comp_features(
    df: pd.DataFrame,
    context: FeatureEngineeringContext | None,
) -> pd.DataFrame:
    """Add strict-prior street and exact-address comp features."""
    df = _ensure_address_keys(df)
    if context is None:
        return _add_training_address_comp_features(df)
    return _add_context_address_comp_features(df, context)


def _ensure_address_keys(df: pd.DataFrame) -> pd.DataFrame:
    address = df.get("address", pd.Series("unknown", index=df.index))
    area = df.get("area", pd.Series("unknown", index=df.index)).astype("object")
    area_key = area.where(area.notna(), "unknown").astype(str).str.lower()

    df["street_name"] = address.apply(normalize_street_name)
    address_key = address.apply(normalize_address_key)

    street_valid = df["street_name"].ne("unknown") & area_key.ne("unknown")
    address_valid = address_key.ne("unknown") & area_key.ne("unknown")

    df["_street_area_key"] = np.where(street_valid, area_key + "|" + df["street_name"], None)
    df["_address_comp_key"] = np.where(address_valid, area_key + "|" + address_key, None)
    if SIZE_BAND_COLUMN not in df.columns:
        df[SIZE_BAND_COLUMN] = _size_band(df)
    size_band = (
        df[SIZE_BAND_COLUMN]
        .astype("object")
        .where(
            df[SIZE_BAND_COLUMN].notna(),
            "unknown",
        )
    )
    df["_street_size_key"] = np.where(
        street_valid,
        pd.Series(df["_street_area_key"], index=df.index).astype(str) + "|" + size_band.astype(str),
        None,
    )
    return df


def _add_training_address_comp_features(df: pd.DataFrame) -> pd.DataFrame:
    df[MICRO_AREA_SOURCE_COLUMN] = observed_price_per_sqm(df)
    _init_address_comp_features(df)

    if "sold_date" in df.columns:
        df["sold_date"] = pd.to_datetime(df["sold_date"], errors="coerce")
        street_area = _prior_group_stats(df, "_street_area_key")
        street_size = _prior_group_stats(df, "_street_size_key")
        address = _prior_group_stats(df, "_address_comp_key")
    else:
        street_area = _group_stats(df, "_street_area_key")
        street_size = _group_stats(df, "_street_size_key")
        address = _group_stats(df, "_address_comp_key")

    _choose_address_comp_stats(df, street_area, street_size, address)
    return df


def _add_context_address_comp_features(
    df: pd.DataFrame,
    context: FeatureEngineeringContext,
) -> pd.DataFrame:
    _init_address_comp_features(df)
    street_area = _context_stats_frame(
        df["_street_area_key"],
        getattr(context, "street_area_ppsqm_stats", None),
    )
    street_size = _context_stats_frame(
        df["_street_size_key"],
        getattr(context, "street_size_ppsqm_stats", None),
    )
    address = _context_stats_frame(
        df["_address_comp_key"],
        getattr(context, "address_ppsqm_stats", None),
    )
    _choose_address_comp_stats(df, street_area, street_size, address)
    return df


def _init_address_comp_features(df: pd.DataFrame) -> None:
    for prefix in ("street_area", "street_size", "address"):
        df[f"{prefix}_ppsqm_median"] = np.nan
        df[f"{prefix}_ppsqm_p75"] = np.nan
        df[f"{prefix}_ppsqm_p90"] = np.nan
        df[f"{prefix}_ppsqm_count"] = 0.0
        df[f"{prefix}_upper_tail_ratio"] = 1.0

    df["street_area_premium_vs_micro"] = 0.0
    df["street_size_premium_vs_street"] = 0.0
    df["address_premium_vs_street"] = 0.0
    df["street_area_scope_used"] = "micro_area"
    df["street_size_scope_used"] = "street_area"
    df["address_comp_scope_used"] = "street_area"


def _choose_address_comp_stats(
    df: pd.DataFrame,
    street_area: pd.DataFrame,
    street_size: pd.DataFrame,
    address: pd.DataFrame,
) -> None:
    _fill_from_micro_area(df, "street_area")
    street_ok = street_area["count"] >= STREET_AREA_MIN_PRIOR_COUNT
    _assign_stats(
        df, "street_area", street_ok, street_area, "street_area_scope_used", "street_area"
    )
    _finish_stats(df, "street_area")

    _copy_prefix(df, source="street_area", target="street_size")
    df["street_size_scope_used"] = "street_area"
    size_ok = street_size["count"] >= STREET_SIZE_MIN_PRIOR_COUNT
    _assign_stats(df, "street_size", size_ok, street_size, "street_size_scope_used", "street_size")
    _finish_stats(df, "street_size")

    _copy_prefix(df, source="street_area", target="address")
    df["address_comp_scope_used"] = "street_area"
    address_ok = address["count"] >= ADDRESS_MIN_PRIOR_COUNT
    _assign_stats(df, "address", address_ok, address, "address_comp_scope_used", "address")
    _finish_stats(df, "address")

    street_premium = _safe_divide(
        df["street_area_ppsqm_median"],
        _numeric_column(df, "micro_area_ppsqm_median"),
        df.index,
    )
    df["street_area_premium_vs_micro"] = (street_premium - 1.0).fillna(0.0)

    size_premium = _safe_divide(
        df["street_size_ppsqm_median"],
        df["street_area_ppsqm_median"],
        df.index,
    )
    df["street_size_premium_vs_street"] = (size_premium - 1.0).fillna(0.0)

    address_premium = _safe_divide(
        df["address_ppsqm_median"],
        df["street_area_ppsqm_median"],
        df.index,
    )
    df["address_premium_vs_street"] = (address_premium - 1.0).fillna(0.0)


def _fill_from_micro_area(df: pd.DataFrame, prefix: str) -> None:
    df[f"{prefix}_ppsqm_median"] = _numeric_column(df, "micro_area_ppsqm_median")
    df[f"{prefix}_ppsqm_p75"] = _numeric_column(
        df,
        "micro_area_ppsqm_p75",
        fallback_column="micro_area_ppsqm_median",
    )
    df[f"{prefix}_ppsqm_p90"] = _numeric_column(
        df,
        "micro_area_ppsqm_p90",
        fallback_column="micro_area_ppsqm_p75",
    )
    df[f"{prefix}_ppsqm_count"] = 0.0


def _copy_prefix(df: pd.DataFrame, *, source: str, target: str) -> None:
    for suffix in ("median", "p75", "p90", "count"):
        df[f"{target}_ppsqm_{suffix}"] = df[f"{source}_ppsqm_{suffix}"]
    df[f"{target}_upper_tail_ratio"] = df[f"{source}_upper_tail_ratio"]


def _assign_stats(
    df: pd.DataFrame,
    prefix: str,
    mask: pd.Series,
    stats: pd.DataFrame,
    scope_column: str,
    scope_value: str,
) -> None:
    df.loc[mask, f"{prefix}_ppsqm_median"] = stats.loc[mask, "median"]
    df.loc[mask, f"{prefix}_ppsqm_p75"] = stats.loc[mask, "p75"]
    df.loc[mask, f"{prefix}_ppsqm_p90"] = stats.loc[mask, "p90"]
    df.loc[mask, f"{prefix}_ppsqm_count"] = stats.loc[mask, "count"]
    df.loc[mask, scope_column] = scope_value


def _finish_stats(df: pd.DataFrame, prefix: str) -> None:
    df[f"{prefix}_ppsqm_p75"] = df[f"{prefix}_ppsqm_p75"].fillna(df[f"{prefix}_ppsqm_median"])
    df[f"{prefix}_ppsqm_p90"] = (
        df[f"{prefix}_ppsqm_p90"]
        .fillna(df[f"{prefix}_ppsqm_p75"])
        .fillna(df[f"{prefix}_ppsqm_median"])
    )
    df[f"{prefix}_ppsqm_count"] = df[f"{prefix}_ppsqm_count"].fillna(0.0)
    upper_tail = _safe_divide(
        df[f"{prefix}_ppsqm_p90"],
        df[f"{prefix}_ppsqm_median"],
        df.index,
    )
    df[f"{prefix}_upper_tail_ratio"] = upper_tail.fillna(1.0)


def _prior_group_stats(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    if group_col not in df.columns or "sold_date" not in df.columns:
        return _empty_stats(df.index)

    work = df[[group_col, "sold_date", MICRO_AREA_SOURCE_COLUMN]].copy()
    work["_orig_idx"] = work.index
    work = work.dropna(subset=[group_col, "sold_date", MICRO_AREA_SOURCE_COLUMN])
    if work.empty:
        return _empty_stats(df.index)

    work = work.sort_values("sold_date").set_index("sold_date")
    grouped = work.groupby(group_col, observed=True)
    stats = pd.DataFrame(
        {
            "median": grouped[MICRO_AREA_SOURCE_COLUMN]
            .transform(lambda values: values.rolling("100000D", closed="left").median())
            .values,
            "p75": grouped[MICRO_AREA_SOURCE_COLUMN]
            .transform(lambda values: values.rolling("100000D", closed="left").quantile(0.75))
            .values,
            "p90": grouped[MICRO_AREA_SOURCE_COLUMN]
            .transform(lambda values: values.rolling("100000D", closed="left").quantile(0.90))
            .values,
            "count": grouped[MICRO_AREA_SOURCE_COLUMN]
            .transform(lambda values: values.rolling("100000D", closed="left").count())
            .values,
        },
        index=work["_orig_idx"].values,
    )
    return stats.reindex(df.index)


def _group_stats(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    if group_col not in df.columns:
        return _empty_stats(df.index)

    work = df[[group_col, MICRO_AREA_SOURCE_COLUMN]].dropna(
        subset=[group_col, MICRO_AREA_SOURCE_COLUMN]
    )
    if work.empty:
        return _empty_stats(df.index)

    grouped = work.groupby(group_col, observed=True)[MICRO_AREA_SOURCE_COLUMN]
    stats = pd.DataFrame(
        {
            "median": grouped.median(),
            "p75": grouped.quantile(0.75),
            "p90": grouped.quantile(0.90),
            "count": grouped.count(),
        }
    )
    return _context_stats_frame(df[group_col], _stats_dict(stats))


def _context_stats_frame(
    keys: pd.Series,
    stats: dict[str, dict[str, float]] | None,
) -> pd.DataFrame:
    if not stats:
        return _empty_stats(keys.index)

    stats_df = pd.DataFrame.from_dict(stats, orient="index")
    return pd.DataFrame(
        {
            "median": _map_stat(keys, stats_df, "median"),
            "p75": _map_stat(keys, stats_df, "p75", fallback_column="median"),
            "p90": _map_stat(keys, stats_df, "p90", fallback_column="p75"),
            "count": _map_stat(keys, stats_df, "count"),
        },
        index=keys.index,
    )


def _map_stat(
    keys: pd.Series,
    stats_df: pd.DataFrame,
    column: str,
    *,
    fallback_column: str | None = None,
) -> pd.Series:
    if column in stats_df:
        return keys.map(stats_df[column])
    if fallback_column is not None and fallback_column in stats_df:
        return keys.map(stats_df[fallback_column])
    return pd.Series(np.nan, index=keys.index, dtype=float)


def _empty_stats(index: pd.Index) -> pd.DataFrame:
    return pd.DataFrame(dict.fromkeys(ADDRESS_STAT_COLUMNS, np.nan), index=index)


def build_address_context_stats(
    training_frame: pd.DataFrame,
    key_column: str,
) -> dict[str, dict[str, float]]:
    frame = _ensure_address_keys(training_frame.copy())
    if key_column not in frame.columns:
        return {}

    source = observed_price_per_sqm(frame)
    work = pd.DataFrame({key_column: frame[key_column], "ppsqm": source})
    work = work.dropna(subset=[key_column, "ppsqm"])
    if work.empty:
        return {}

    grouped = work.groupby(key_column, observed=True)["ppsqm"]
    stats = pd.DataFrame(
        {
            "median": grouped.median(),
            "p75": grouped.quantile(0.75),
            "p90": grouped.quantile(0.90),
            "count": grouped.count(),
        }
    )
    return _stats_dict(stats)


def _stats_dict(stats: pd.DataFrame) -> dict[str, dict[str, float]]:
    values = {}
    for key, row in stats.iterrows():
        median = _float_stat(row, "median")
        p75 = _float_stat(row, "p75", fallback=median)
        p90 = _float_stat(row, "p90", fallback=p75)
        values[str(key)] = {
            "median": median,
            "p75": p75,
            "p90": p90,
            "count": _float_stat(row, "count", fallback=0.0),
        }
    return values


def _float_stat(row: pd.Series, column: str, *, fallback: float = np.nan) -> float:
    value = row[column] if column in row else fallback
    if pd.isna(value):
        return float(fallback)
    return float(value)


def _numeric_column(
    df: pd.DataFrame,
    column: str,
    *,
    fallback_column: str | None = None,
) -> pd.Series:
    if column in df.columns:
        values = pd.to_numeric(df[column], errors="coerce")
    else:
        values = pd.Series(np.nan, index=df.index, dtype=float)
    if fallback_column is not None and fallback_column in df.columns:
        values = values.fillna(pd.to_numeric(df[fallback_column], errors="coerce"))
    return values
