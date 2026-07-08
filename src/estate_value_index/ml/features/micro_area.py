from __future__ import annotations

import numpy as np
import pandas as pd

from estate_value_index.ml.features.context import FeatureEngineeringContext
from estate_value_index.ml.features.utils import _safe_divide

"""H3 micro-area price-per-sqm features."""

H3_BASE_RESOLUTION = 10
H3_FALLBACK_RESOLUTION = 9
MICRO_AREA_MIN_PRIOR_COUNT = 20
SAME_SIZE_MIN_PRIOR_COUNT = 5
MICRO_AREA_SOURCE_COLUMN = "_observed_price_per_sqm"
SIZE_BAND_COLUMN = "_micro_area_size_band"
STAT_COLUMNS = ("median", "p75", "p90", "count")

try:
    import h3
except ImportError:  # pragma: no cover - dependency is installed via the geo extra.
    h3 = None


def normalize_coordinate_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Expose canonical lat/lon columns from either raw naming convention."""
    if "lat" not in df.columns and "latitude" in df.columns:
        df["lat"] = df["latitude"]
    if "lon" not in df.columns and "longitude" in df.columns:
        df["lon"] = df["longitude"]

    for column in ("lat", "lon"):
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    return df


def create_h3_cell(lat: float, lon: float, resolution: int) -> str | None:
    if h3 is None or pd.isna(lat) or pd.isna(lon):
        return None
    return h3.latlng_to_cell(float(lat), float(lon), resolution)


def add_h3_cells(df: pd.DataFrame) -> pd.DataFrame:
    df = normalize_coordinate_columns(df)
    if "lat" not in df.columns or "lon" not in df.columns:
        df["h3_res10"] = None
        df["h3_res9"] = None
        return df

    df["h3_res10"] = [
        create_h3_cell(lat, lon, H3_BASE_RESOLUTION)
        for lat, lon in zip(df["lat"], df["lon"], strict=False)
    ]
    df["h3_res9"] = [
        h3.cell_to_parent(cell, H3_FALLBACK_RESOLUTION) if h3 is not None and cell else None
        for cell in df["h3_res10"]
    ]
    return df


def observed_price_per_sqm(df: pd.DataFrame) -> pd.Series:
    if MICRO_AREA_SOURCE_COLUMN in df.columns:
        source = pd.to_numeric(df[MICRO_AREA_SOURCE_COLUMN], errors="coerce")
    elif "price_per_sqm" in df.columns:
        source = pd.to_numeric(df["price_per_sqm"], errors="coerce")
    else:
        source = pd.Series(np.nan, index=df.index, dtype=float)

    if "sold_price" in df.columns and "living_area" in df.columns:
        sold_ppsqm = _safe_divide(df["sold_price"], df["living_area"], df.index)
        source = source.fillna(sold_ppsqm)

    source = source.where(source > 0)
    return source.astype(float)


def create_micro_area_features(
    df: pd.DataFrame,
    context: FeatureEngineeringContext | None,
) -> pd.DataFrame:
    df = add_h3_cells(df)
    if context is None:
        df = _add_training_micro_area_features(df)
    else:
        df = _add_context_micro_area_features(df, context)
    return _add_comp_features(df, context)


def _add_training_micro_area_features(df: pd.DataFrame) -> pd.DataFrame:
    df[MICRO_AREA_SOURCE_COLUMN] = observed_price_per_sqm(df)
    for column in (
        "micro_area_ppsqm_median",
        "micro_area_ppsqm_p75",
        "micro_area_ppsqm_p90",
        "micro_area_ppsqm_count",
        "micro_area_ppsqm_premium_vs_area",
    ):
        df[column] = np.nan
    df["micro_area_upper_tail_ratio"] = 1.0
    df["micro_area_resolution_used"] = "global"

    if "sold_date" not in df.columns:
        return _add_group_micro_area_features(df)

    df["sold_date"] = pd.to_datetime(df["sold_date"], errors="coerce")
    base = _prior_group_stats(df, "h3_res10")
    fallback = _prior_group_stats(df, "h3_res9")
    area = _prior_group_stats(df, "area")
    global_stats = _prior_global_stats(df)

    _choose_micro_area_stats(df, base, fallback, area, global_stats)
    return df


def _add_group_micro_area_features(df: pd.DataFrame) -> pd.DataFrame:
    base = _group_stats(df, "h3_res10")
    fallback = _group_stats(df, "h3_res9")
    area = _group_stats(df, "area")
    global_stats = pd.DataFrame(
        {
            "median": df[MICRO_AREA_SOURCE_COLUMN].median(skipna=True),
            "p75": df[MICRO_AREA_SOURCE_COLUMN].quantile(0.75),
            "p90": df[MICRO_AREA_SOURCE_COLUMN].quantile(0.90),
            "count": df[MICRO_AREA_SOURCE_COLUMN].count(),
        },
        index=df.index,
    )
    _choose_micro_area_stats(df, base, fallback, area, global_stats)
    return df


def _prior_group_stats(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    if group_col not in df.columns:
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


def _prior_global_stats(df: pd.DataFrame) -> pd.DataFrame:
    work = df[["sold_date", MICRO_AREA_SOURCE_COLUMN]].copy()
    work["_orig_idx"] = work.index
    work = work.dropna(subset=["sold_date", MICRO_AREA_SOURCE_COLUMN])
    if work.empty:
        return _empty_stats(df.index)

    work = work.sort_values("sold_date").set_index("sold_date")
    stats = pd.DataFrame(
        {
            "median": work[MICRO_AREA_SOURCE_COLUMN]
            .rolling("100000D", closed="left")
            .median()
            .values,
            "p75": work[MICRO_AREA_SOURCE_COLUMN]
            .rolling("100000D", closed="left")
            .quantile(0.75)
            .values,
            "p90": work[MICRO_AREA_SOURCE_COLUMN]
            .rolling("100000D", closed="left")
            .quantile(0.90)
            .values,
            "count": work[MICRO_AREA_SOURCE_COLUMN]
            .rolling("100000D", closed="left")
            .count()
            .values,
        },
        index=work["_orig_idx"].values,
    )
    return stats.reindex(df.index)


def _group_stats(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    if group_col not in df.columns:
        return _empty_stats(df.index)
    grouped = df.groupby(group_col, observed=True)[MICRO_AREA_SOURCE_COLUMN]
    stats = pd.DataFrame(
        {
            "median": grouped.median(),
            "p75": grouped.quantile(0.75),
            "p90": grouped.quantile(0.90),
            "count": grouped.count(),
        }
    )
    return _context_stats_frame(df[group_col], _stats_dict(stats))


def _empty_stats(index: pd.Index) -> pd.DataFrame:
    return pd.DataFrame(dict.fromkeys(STAT_COLUMNS, np.nan), index=index)


def _assign_micro_area_stats(
    df: pd.DataFrame,
    mask: pd.Series,
    stats: pd.DataFrame,
    resolution: str,
) -> None:
    df.loc[mask, "micro_area_ppsqm_median"] = stats.loc[mask, "median"]
    df.loc[mask, "micro_area_ppsqm_p75"] = stats.loc[mask, "p75"]
    df.loc[mask, "micro_area_ppsqm_p90"] = stats.loc[mask, "p90"]
    df.loc[mask, "micro_area_ppsqm_count"] = stats.loc[mask, "count"]
    df.loc[mask, "micro_area_resolution_used"] = resolution


def _finish_micro_area_stats(df: pd.DataFrame, area: pd.DataFrame) -> None:
    df["micro_area_ppsqm_p75"] = df["micro_area_ppsqm_p75"].fillna(df["micro_area_ppsqm_median"])
    df["micro_area_ppsqm_p90"] = (
        df["micro_area_ppsqm_p90"]
        .fillna(df["micro_area_ppsqm_p75"])
        .fillna(df["micro_area_ppsqm_median"])
    )
    upper_tail = _safe_divide(
        df["micro_area_ppsqm_p90"],
        df["micro_area_ppsqm_median"],
        df.index,
    )
    df["micro_area_upper_tail_ratio"] = upper_tail.fillna(1.0)


def _choose_micro_area_stats(
    df: pd.DataFrame,
    base: pd.DataFrame,
    fallback: pd.DataFrame,
    area: pd.DataFrame,
    global_stats: pd.DataFrame,
) -> None:
    base_ok = base["count"] >= MICRO_AREA_MIN_PRIOR_COUNT
    fallback_ok = fallback["count"] >= MICRO_AREA_MIN_PRIOR_COUNT
    area_ok = area["count"] > 0
    global_ok = global_stats["count"] > 0

    _assign_micro_area_stats(df, base_ok, base, "h3_res10")

    use_fallback = ~base_ok & fallback_ok
    _assign_micro_area_stats(df, use_fallback, fallback, "h3_res9")

    use_area = ~base_ok & ~fallback_ok & area_ok
    _assign_micro_area_stats(df, use_area, area, "area")

    use_global = ~base_ok & ~fallback_ok & ~area_ok & global_ok
    _assign_micro_area_stats(df, use_global, global_stats, "global")

    _finish_micro_area_stats(df, area)
    area_denominator = area["median"].fillna(df["micro_area_ppsqm_median"])
    premium = _safe_divide(df["micro_area_ppsqm_median"], area_denominator, df.index) - 1.0
    df["micro_area_ppsqm_premium_vs_area"] = premium.fillna(0.0)
    df["micro_area_ppsqm_count"] = df["micro_area_ppsqm_count"].fillna(0.0)


def _add_context_micro_area_features(
    df: pd.DataFrame,
    context: FeatureEngineeringContext,
) -> pd.DataFrame:
    res10 = _context_stats_frame(df["h3_res10"], getattr(context, "micro_area_stats_res10", None))
    res9 = _context_stats_frame(df["h3_res9"], getattr(context, "micro_area_stats_res9", None))
    area = _context_stats_frame(df["area"], getattr(context, "area_ppsqm_stats", None))

    base_ok = res10["count"] >= MICRO_AREA_MIN_PRIOR_COUNT
    fallback_ok = res9["count"] >= MICRO_AREA_MIN_PRIOR_COUNT
    area_ok = area["count"] > 0

    global_median = getattr(context, "global_ppsqm_median", None)
    if global_median is None or pd.isna(global_median):
        global_median = 0.0

    df["micro_area_ppsqm_median"] = global_median
    df["micro_area_ppsqm_p75"] = global_median
    df["micro_area_ppsqm_p90"] = global_median
    df["micro_area_ppsqm_count"] = 0.0
    df["micro_area_upper_tail_ratio"] = 1.0
    df["micro_area_resolution_used"] = "global"

    _assign_micro_area_stats(df, area_ok, area, "area")

    use_fallback = fallback_ok
    _assign_micro_area_stats(df, use_fallback, res9, "h3_res9")

    _assign_micro_area_stats(df, base_ok, res10, "h3_res10")

    _finish_micro_area_stats(df, area)
    area_denominator = area["median"].fillna(df["micro_area_ppsqm_median"])
    premium = _safe_divide(df["micro_area_ppsqm_median"], area_denominator, df.index) - 1.0
    df["micro_area_ppsqm_premium_vs_area"] = premium.fillna(0.0)
    return df


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


def _add_comp_features(
    df: pd.DataFrame,
    context: FeatureEngineeringContext | None,
) -> pd.DataFrame:
    df[SIZE_BAND_COLUMN] = _size_band(df)
    if context is None:
        df = _add_training_neighbor_features(df)
        return _add_training_same_size_features(df)

    df = _add_context_neighbor_features(df, context)
    return _add_context_same_size_features(df, context)


def _size_band(df: pd.DataFrame) -> pd.Series:
    if "living_area" in df.columns:
        living_area = pd.to_numeric(df["living_area"], errors="coerce")
    else:
        living_area = pd.Series(np.nan, index=df.index)
    return (
        pd.cut(
            living_area,
            bins=[0, 35, 50, 70, 90, 120, np.inf],
            labels=["<35", "35-50", "50-70", "70-90", "90-120", "120+"],
        )
        .astype("object")
        .fillna("unknown")
    )


def _add_training_neighbor_features(df: pd.DataFrame) -> pd.DataFrame:
    _init_neighbor_features(df)
    if "sold_date" not in df.columns:
        return _add_group_neighbor_features(df)

    work = df[["h3_res10", "sold_date", MICRO_AREA_SOURCE_COLUMN]].copy()
    work["_orig_idx"] = work.index
    work = work.dropna(subset=["h3_res10", "sold_date", MICRO_AREA_SOURCE_COLUMN])
    if work.empty:
        return df

    work["sold_date"] = pd.to_datetime(work["sold_date"], errors="coerce")
    work = work.dropna(subset=["sold_date"]).sort_values("sold_date")
    state: dict[str, list[float]] = {}

    for _, same_date in work.groupby("sold_date", sort=True):
        rows = same_date[["h3_res10", MICRO_AREA_SOURCE_COLUMN, "_orig_idx"]].itertuples(
            index=False, name=None
        )
        for cell, _, orig_idx in rows:
            median, p75, p90, count = _neighbor_stats_from_state(cell, state)
            df.loc[orig_idx, "h3_neighbor_ppsqm"] = median
            df.loc[orig_idx, "h3_neighbor_ppsqm_p75"] = p75
            df.loc[orig_idx, "h3_neighbor_ppsqm_p90"] = p90
            df.loc[orig_idx, "h3_neighbor_ppsqm_count"] = count

        rows = same_date[["h3_res10", MICRO_AREA_SOURCE_COLUMN]].itertuples(index=False, name=None)
        for cell, ppsqm in rows:
            state.setdefault(str(cell), []).append(float(ppsqm))

    _finish_neighbor_features(df)
    return df


def _add_group_neighbor_features(df: pd.DataFrame) -> pd.DataFrame:
    if "h3_res10" not in df.columns:
        return df

    cell_stats = build_micro_area_context_stats(df, "h3_res10")
    for idx, cell in df["h3_res10"].items():
        median, p75, p90, count = _neighbor_stats_from_context(cell, cell_stats)
        df.loc[idx, "h3_neighbor_ppsqm"] = median
        df.loc[idx, "h3_neighbor_ppsqm_p75"] = p75
        df.loc[idx, "h3_neighbor_ppsqm_p90"] = p90
        df.loc[idx, "h3_neighbor_ppsqm_count"] = count

    _finish_neighbor_features(df)
    return df


def _add_context_neighbor_features(
    df: pd.DataFrame,
    context: FeatureEngineeringContext,
) -> pd.DataFrame:
    _init_neighbor_features(df)
    cell_stats = getattr(context, "micro_area_stats_res10", None) or {}
    for idx, cell in df["h3_res10"].items():
        median, p75, p90, count = _neighbor_stats_from_context(cell, cell_stats)
        df.loc[idx, "h3_neighbor_ppsqm"] = median
        df.loc[idx, "h3_neighbor_ppsqm_p75"] = p75
        df.loc[idx, "h3_neighbor_ppsqm_p90"] = p90
        df.loc[idx, "h3_neighbor_ppsqm_count"] = count

    _finish_neighbor_features(df)
    return df


def _init_neighbor_features(df: pd.DataFrame) -> None:
    df["h3_neighbor_ppsqm"] = np.nan
    df["h3_neighbor_ppsqm_p75"] = np.nan
    df["h3_neighbor_ppsqm_p90"] = np.nan
    df["h3_neighbor_ppsqm_count"] = 0.0
    df["h3_neighbor_premium_vs_micro"] = 0.0
    df["h3_neighbor_upper_tail_ratio"] = 1.0


def _finish_neighbor_features(df: pd.DataFrame) -> None:
    df["h3_neighbor_ppsqm_count"] = df["h3_neighbor_ppsqm_count"].fillna(0.0)
    df["h3_neighbor_ppsqm"] = df["h3_neighbor_ppsqm"].fillna(df["micro_area_ppsqm_median"])
    df["h3_neighbor_ppsqm_p75"] = df["h3_neighbor_ppsqm_p75"].fillna(df["h3_neighbor_ppsqm"])
    df["h3_neighbor_ppsqm_p90"] = (
        df["h3_neighbor_ppsqm_p90"]
        .fillna(df["h3_neighbor_ppsqm_p75"])
        .fillna(df["h3_neighbor_ppsqm"])
    )
    premium = _safe_divide(df["h3_neighbor_ppsqm"], df["micro_area_ppsqm_median"], df.index) - 1.0
    df["h3_neighbor_premium_vs_micro"] = premium.fillna(0.0)
    upper_tail = _safe_divide(
        df["h3_neighbor_ppsqm_p90"],
        df["h3_neighbor_ppsqm"],
        df.index,
    )
    df["h3_neighbor_upper_tail_ratio"] = upper_tail.fillna(1.0)


def _neighbor_stats_from_state(
    cell: object,
    state: dict[str, list[float]],
) -> tuple[float, float, float, float]:
    weighted_sum = 0.0
    p75_weighted_sum = 0.0
    p90_weighted_sum = 0.0
    count = 0.0
    for neighbor in _neighbor_cells(cell):
        values = state.get(neighbor)
        if not values:
            continue
        cell_values = np.asarray(values, dtype=float)
        n = float(len(values))
        weighted_sum += float(np.median(cell_values)) * n
        p75_weighted_sum += float(np.quantile(cell_values, 0.75)) * n
        p90_weighted_sum += float(np.quantile(cell_values, 0.90)) * n
        count += n

    if count == 0:
        return np.nan, np.nan, np.nan, 0.0
    return weighted_sum / count, p75_weighted_sum / count, p90_weighted_sum / count, count


def _neighbor_stats_from_context(
    cell: object,
    stats: dict[str, dict[str, float]],
) -> tuple[float, float, float, float]:
    weighted_sum = 0.0
    p75_weighted_sum = 0.0
    p90_weighted_sum = 0.0
    count = 0.0
    for neighbor in _neighbor_cells(cell):
        row = stats.get(neighbor)
        if not row:
            continue
        n = float(row.get("count", 0.0) or 0.0)
        median = row.get("median")
        if n <= 0 or median is None or pd.isna(median):
            continue
        p75 = row.get("p75", median)
        p90 = row.get("p90", p75)
        weighted_sum += float(median) * n
        p75_weighted_sum += float(p75) * n
        p90_weighted_sum += float(p90) * n
        count += n

    if count == 0:
        return np.nan, np.nan, np.nan, 0.0
    return weighted_sum / count, p75_weighted_sum / count, p90_weighted_sum / count, count


def _neighbor_cells(cell: object) -> set[str]:
    if h3 is None or not isinstance(cell, str) or not cell:
        return set()

    try:
        cells = set(h3.grid_disk(cell, 1))
    except (ValueError, TypeError):
        return set()
    cells.discard(cell)
    return {str(value) for value in cells}


def _add_training_same_size_features(df: pd.DataFrame) -> pd.DataFrame:
    _init_same_size_features(df)
    if "sold_date" not in df.columns:
        return _add_group_same_size_features(df)

    h3_size = _prior_multi_group_stats(df, ["h3_res9", SIZE_BAND_COLUMN])
    area_size = _prior_multi_group_stats(df, ["area", SIZE_BAND_COLUMN])
    global_size = _prior_multi_group_stats(df, [SIZE_BAND_COLUMN])
    _choose_same_size_stats(df, h3_size, area_size, global_size)
    return df


def _add_group_same_size_features(df: pd.DataFrame) -> pd.DataFrame:
    h3_size = _multi_group_stats(df, ["h3_res9", SIZE_BAND_COLUMN])
    area_size = _multi_group_stats(df, ["area", SIZE_BAND_COLUMN])
    global_size = _multi_group_stats(df, [SIZE_BAND_COLUMN])
    _choose_same_size_stats(df, h3_size, area_size, global_size)
    return df


def _add_context_same_size_features(
    df: pd.DataFrame,
    context: FeatureEngineeringContext,
) -> pd.DataFrame:
    _init_same_size_features(df)
    h3_size = _context_multi_stats_frame(
        _stats_keys(df, ["h3_res9", SIZE_BAND_COLUMN]),
        getattr(context, "same_size_stats_h3_res9", None),
    )
    area_size = _context_multi_stats_frame(
        _stats_keys(df, ["area", SIZE_BAND_COLUMN]),
        getattr(context, "same_size_stats_area", None),
    )
    global_size = _context_multi_stats_frame(
        _stats_keys(df, [SIZE_BAND_COLUMN]),
        getattr(context, "same_size_stats_global", None),
    )
    _choose_same_size_stats(df, h3_size, area_size, global_size)
    return df


def _init_same_size_features(df: pd.DataFrame) -> None:
    df["same_size_ppsqm_median"] = np.nan
    df["same_size_ppsqm_p75"] = np.nan
    df["same_size_ppsqm_p90"] = np.nan
    df["same_size_ppsqm_count"] = 0.0
    df["same_size_premium_vs_area"] = 0.0
    df["same_size_upper_tail_ratio"] = 1.0
    df["same_size_scope_used"] = "global"


def _prior_multi_group_stats(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    missing = [column for column in group_cols if column not in df.columns]
    if missing or "sold_date" not in df.columns:
        return _empty_stats(df.index)

    work = df[[*group_cols, "sold_date", MICRO_AREA_SOURCE_COLUMN]].copy()
    work["_orig_idx"] = work.index
    work["_stats_key"] = _stats_keys(work, group_cols)
    work = work.dropna(subset=["_stats_key", "sold_date", MICRO_AREA_SOURCE_COLUMN])
    if work.empty:
        return _empty_stats(df.index)

    work["sold_date"] = pd.to_datetime(work["sold_date"], errors="coerce")
    work = work.dropna(subset=["sold_date"]).sort_values("sold_date").set_index("sold_date")
    grouped = work.groupby("_stats_key", observed=True)
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


def _multi_group_stats(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    missing = [column for column in group_cols if column not in df.columns]
    if missing:
        return _empty_stats(df.index)

    work = pd.DataFrame(
        {
            "_stats_key": _stats_keys(df, group_cols),
            "ppsqm": df[MICRO_AREA_SOURCE_COLUMN],
        },
        index=df.index,
    ).dropna(subset=["_stats_key", "ppsqm"])
    if work.empty:
        return _empty_stats(df.index)

    grouped = work.groupby("_stats_key", observed=True)["ppsqm"]
    stats = pd.DataFrame(
        {
            "median": grouped.median(),
            "p75": grouped.quantile(0.75),
            "p90": grouped.quantile(0.90),
            "count": grouped.count(),
        }
    )
    keys = _stats_keys(df, group_cols)
    return _context_multi_stats_frame(keys, _stats_dict(stats))


def _choose_same_size_stats(
    df: pd.DataFrame,
    h3_size: pd.DataFrame,
    area_size: pd.DataFrame,
    global_size: pd.DataFrame,
) -> None:
    h3_ok = h3_size["count"] >= SAME_SIZE_MIN_PRIOR_COUNT
    area_ok = area_size["count"] >= SAME_SIZE_MIN_PRIOR_COUNT
    global_ok = global_size["count"] > 0

    df.loc[global_ok, "same_size_ppsqm_median"] = global_size.loc[global_ok, "median"]
    df.loc[global_ok, "same_size_ppsqm_p75"] = global_size.loc[global_ok, "p75"]
    df.loc[global_ok, "same_size_ppsqm_p90"] = global_size.loc[global_ok, "p90"]
    df.loc[global_ok, "same_size_ppsqm_count"] = global_size.loc[global_ok, "count"]
    df.loc[global_ok, "same_size_scope_used"] = "global_size"

    use_area = area_ok
    df.loc[use_area, "same_size_ppsqm_median"] = area_size.loc[use_area, "median"]
    df.loc[use_area, "same_size_ppsqm_p75"] = area_size.loc[use_area, "p75"]
    df.loc[use_area, "same_size_ppsqm_p90"] = area_size.loc[use_area, "p90"]
    df.loc[use_area, "same_size_ppsqm_count"] = area_size.loc[use_area, "count"]
    df.loc[use_area, "same_size_scope_used"] = "area_size"

    use_h3 = h3_ok
    df.loc[use_h3, "same_size_ppsqm_median"] = h3_size.loc[use_h3, "median"]
    df.loc[use_h3, "same_size_ppsqm_p75"] = h3_size.loc[use_h3, "p75"]
    df.loc[use_h3, "same_size_ppsqm_p90"] = h3_size.loc[use_h3, "p90"]
    df.loc[use_h3, "same_size_ppsqm_count"] = h3_size.loc[use_h3, "count"]
    df.loc[use_h3, "same_size_scope_used"] = "h3_res9_size"

    df["same_size_ppsqm_median"] = df["same_size_ppsqm_median"].fillna(
        df["micro_area_ppsqm_median"]
    )
    df["same_size_ppsqm_count"] = df["same_size_ppsqm_count"].fillna(0.0)
    df["same_size_ppsqm_p75"] = df["same_size_ppsqm_p75"].fillna(df["same_size_ppsqm_median"])
    df["same_size_ppsqm_p90"] = (
        df["same_size_ppsqm_p90"]
        .fillna(df["same_size_ppsqm_p75"])
        .fillna(df["same_size_ppsqm_median"])
    )
    premium = _safe_divide(df["same_size_ppsqm_median"], df["micro_area_ppsqm_median"], df.index)
    df["same_size_premium_vs_area"] = (premium - 1.0).fillna(0.0)
    upper_tail = _safe_divide(
        df["same_size_ppsqm_p90"],
        df["same_size_ppsqm_median"],
        df.index,
    )
    df["same_size_upper_tail_ratio"] = upper_tail.fillna(1.0)


def _context_multi_stats_frame(
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


def _stats_keys(df: pd.DataFrame, columns: list[str]) -> pd.Series:
    values = []
    for column in columns:
        values.append(df[column].astype("object").where(df[column].notna(), "unknown").astype(str))
    key = values[0]
    for value in values[1:]:
        key = key + "|" + value
    return key


def build_micro_area_context_stats(
    training_frame: pd.DataFrame,
    group_col: str,
) -> dict[str, dict[str, float]]:
    if group_col not in training_frame.columns:
        return {}

    source = observed_price_per_sqm(training_frame)
    work = pd.DataFrame({group_col: training_frame[group_col], "ppsqm": source})
    work = work.dropna(subset=[group_col, "ppsqm"])
    if work.empty:
        return {}

    grouped = work.groupby(group_col, observed=True)["ppsqm"]
    stats = pd.DataFrame(
        {
            "median": grouped.median(),
            "p75": grouped.quantile(0.75),
            "p90": grouped.quantile(0.90),
            "count": grouped.count(),
        }
    )
    return _stats_dict(stats)


def build_same_size_context_stats(
    training_frame: pd.DataFrame,
    group_cols: list[str],
) -> dict[str, dict[str, float]]:
    frame = training_frame.copy()
    if SIZE_BAND_COLUMN not in frame.columns:
        frame[SIZE_BAND_COLUMN] = _size_band(frame)

    missing = [column for column in group_cols if column not in frame.columns]
    if missing:
        return {}

    source = observed_price_per_sqm(frame)
    work = pd.DataFrame({"_stats_key": _stats_keys(frame, group_cols), "ppsqm": source})
    work = work.dropna(subset=["_stats_key", "ppsqm"])
    if work.empty:
        return {}

    grouped = work.groupby("_stats_key", observed=True)["ppsqm"]
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


def global_observed_ppsqm_median(training_frame: pd.DataFrame) -> float | None:
    values = observed_price_per_sqm(training_frame).dropna()
    if values.empty:
        return None
    median = values.median(skipna=True)
    return float(median) if pd.notna(median) else None
