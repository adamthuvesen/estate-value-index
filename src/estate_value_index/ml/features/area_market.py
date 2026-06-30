from __future__ import annotations

import numpy as np
import pandas as pd

from estate_value_index.ml.constants import (
    DEFAULT_AREA_INVENTORY,
    DEFAULT_DAYS_ON_MARKET,
    DEFAULT_MEDIAN_PRICE,
    DEFAULT_PRICE_CHANGE,
    DEFAULT_PRICE_VOLATILITY,
    TEMPORAL_WINDOWS,
)
from estate_value_index.ml.features.classifiers import _classify_area_price_momentum
from estate_value_index.ml.features.context import FeatureEngineeringContext
from estate_value_index.ml.features.utils import _safe_divide

"""Area-level market and temporal aggregate features."""


_AREA_MARKET_DEFAULTS = {
    "area_inventory": DEFAULT_AREA_INVENTORY,
    "area_price_volatility": DEFAULT_PRICE_VOLATILITY,
    "area_price_median": DEFAULT_MEDIAN_PRICE,
    "area_days_on_market_median": DEFAULT_DAYS_ON_MARKET,
    "area_price_change_mean": DEFAULT_PRICE_CHANGE,
    "area_price_change_count": 10.0,
}


def _create_area_market_features(
    df: pd.DataFrame, context: FeatureEngineeringContext | None
) -> pd.DataFrame:
    """Create area-level market microstructure features.

    During training, each row's area statistics are computed from other
    listings only (leave-one-out), using a time-based expanding window.
    """
    _ensure_days_on_market(df)
    if context is None:
        _add_training_area_market_features(df)
    else:
        df = _add_context_area_market_features(df, context)

    _fill_area_market_defaults(df)
    _add_area_market_indicators(df)
    return df


def _ensure_days_on_market(df: pd.DataFrame) -> None:
    if "days_on_market" not in df.columns:
        df["days_on_market"] = 0
    else:
        df["days_on_market"] = pd.to_numeric(df["days_on_market"], errors="coerce")


def _add_training_area_market_features(df: pd.DataFrame) -> None:
    if "sold_date" in df.columns:
        _add_prior_area_market_features(df)
    else:
        _add_group_area_market_features(df)


def _add_prior_area_market_features(df: pd.DataFrame) -> None:
    # Time-based rolling with closed='left' ensures same-day rows in the same
    # area see identical prior history and cannot leak into each other.
    df["sold_date"] = pd.to_datetime(df["sold_date"], errors="coerce")
    work_columns = ["area", "sold_date", "listing_price", "days_on_market"]
    if "price_change" in df.columns:
        work_columns.append("price_change")

    work = df[work_columns].copy()
    work["_orig_idx"] = work.index
    work_indexed = work.dropna(subset=["sold_date"]).sort_values("sold_date").set_index("sold_date")
    grouped = work_indexed.groupby("area", observed=True)
    unbounded = "100000D"

    stats = pd.DataFrame(
        {
            "area_inventory": _prior_rolling(grouped, "listing_price", unbounded, "count").values,
            "area_price_median": _prior_rolling(
                grouped, "listing_price", unbounded, "median"
            ).values,
            "area_price_volatility": _prior_rolling(
                grouped, "listing_price", unbounded, "std"
            ).values,
            "area_days_on_market_median": _prior_rolling(
                grouped, "days_on_market", unbounded, "median"
            ).values,
            "area_price_change_mean": _price_change_rolling(
                work_indexed, grouped, unbounded, "mean"
            ).values,
            "area_price_change_count": _price_change_rolling(
                work_indexed, grouped, unbounded, "count"
            ).values,
        },
        index=work_indexed["_orig_idx"].values,
    )
    for column in stats.columns:
        df[column] = stats[column].reindex(df.index)


def _prior_rolling(grouped, column: str, window: str, method: str) -> pd.Series:
    return grouped[column].transform(
        lambda values: getattr(values.rolling(window=window, closed="left"), method)()
    )


def _price_change_rolling(
    work_indexed: pd.DataFrame, grouped, window: str, method: str
) -> pd.Series:
    if "price_change" not in work_indexed.columns:
        return pd.Series(np.nan, index=work_indexed.index)
    return _prior_rolling(grouped, "price_change", window, method)


def _add_group_area_market_features(df: pd.DataFrame) -> None:
    grouped = df.groupby("area", observed=True)
    df["area_inventory"] = grouped["listing_price"].transform("count") - 1
    df["area_price_median"] = grouped["listing_price"].transform("median")
    df["area_price_volatility"] = grouped["listing_price"].transform("std")
    df["area_days_on_market_median"] = grouped["days_on_market"].transform("median")
    if "price_change" in df.columns:
        df["area_price_change_mean"] = grouped["price_change"].transform("mean")
        df["area_price_change_count"] = grouped["price_change"].transform("count")
    else:
        df["area_price_change_mean"] = np.nan
        df["area_price_change_count"] = np.nan


def _add_context_area_market_features(
    df: pd.DataFrame, context: FeatureEngineeringContext
) -> pd.DataFrame:
    if hasattr(context, "area_market_stats") and context.area_market_stats:
        area_stats_df = pd.DataFrame.from_dict(
            context.area_market_stats, orient="index"
        ).reset_index()
        area_stats_df.rename(columns={"index": "area"}, inplace=True)
        df = df.merge(area_stats_df, on="area", how="left")

    for column, default in _AREA_MARKET_DEFAULTS.items():
        if column not in df.columns:
            df[column] = default
    return df


def _fill_area_market_defaults(df: pd.DataFrame) -> None:
    df["area_inventory"] = df["area_inventory"].fillna(df["area_inventory"].median() or 50.0)
    df["area_price_volatility"] = df["area_price_volatility"].fillna(
        df["area_price_volatility"].median() or 500000.0
    )
    df["area_price_median"] = df["area_price_median"].fillna(
        df["area_price_median"].median() or 5000000.0
    )
    df["area_days_on_market_median"] = df["area_days_on_market_median"].fillna(
        df["area_days_on_market_median"].median() or 20.0
    )
    df["area_price_change_mean"] = df["area_price_change_mean"].fillna(
        df["area_price_change_mean"].median() or 350000.0
    )
    df["area_price_change_count"] = df["area_price_change_count"].fillna(10.0)


def _add_area_market_indicators(df: pd.DataFrame) -> None:
    df["area_liquidity"] = _safe_divide(
        df["area_inventory"], df["area_days_on_market_median"], df.index
    )
    df["relative_area_price"] = _safe_divide(df["listing_price"], df["area_price_median"], df.index)
    df["area_volatility_score"] = _safe_divide(
        df["area_price_volatility"], df["area_price_median"], df.index
    )

    # Area price momentum (categorical, based on area stats)
    df["area_price_momentum"] = df["area_price_change_mean"].apply(_classify_area_price_momentum)


def _create_area_temporal_metrics(
    df: pd.DataFrame, context: FeatureEngineeringContext | None
) -> pd.DataFrame:
    """Create rolling temporal metrics for areas (1m, 3m, 6m, 12m windows).

    Uses vectorized time-based rolling windows with closed='left' to exclude
    current observation (temporal safety: only uses data from before sold_date).
    """
    window_definitions = TEMPORAL_WINDOWS

    if context is None:
        for _, suffix in window_definitions:
            df[f"area_sold_price_median_{suffix}"] = np.nan
            df[f"area_sales_volume_{suffix}"] = np.nan

        if "sold_price" in df.columns and "sold_date" in df.columns:
            work = df[["area", "sold_date", "sold_price"]].copy()
            work["sold_date"] = pd.to_datetime(work["sold_date"], errors="coerce")
            valid_mask = (
                work["sold_date"].notna() & work["sold_price"].notna() & work["area"].notna()
            )

            if valid_mask.any():
                work_valid = work[valid_mask].copy()
                work_valid["_orig_idx"] = work_valid.index
                work_valid = work_valid.sort_values("sold_date").set_index("sold_date")

                for window_days, suffix in window_definitions:
                    window_str = f"{window_days}D"

                    # closed='left' excludes current observation (right boundary)
                    work_valid[f"median_{suffix}"] = work_valid.groupby("area", observed=True)[
                        "sold_price"
                    ].transform(
                        lambda x, window=window_str: x.rolling(
                            window=window, closed="left"
                        ).median()
                    )
                    work_valid[f"count_{suffix}"] = work_valid.groupby("area", observed=True)[
                        "sold_price"
                    ].transform(
                        lambda x, window=window_str: x.rolling(window=window, closed="left").count()
                    )

                work_valid = work_valid.reset_index().set_index("_orig_idx")

                for _, suffix in window_definitions:
                    df.loc[work_valid.index, f"area_sold_price_median_{suffix}"] = work_valid[
                        f"median_{suffix}"
                    ]
                    df.loc[work_valid.index, f"area_sales_volume_{suffix}"] = work_valid[
                        f"count_{suffix}"
                    ]
    else:
        # Inference mode: Use cached values
        df["area_sold_price_median_1m"] = df["area"].map(context.area_median_price_1m)
        df["area_sold_price_median_3m"] = df["area"].map(context.area_median_price_3m)
        df["area_sold_price_median_6m"] = df["area"].map(context.area_median_price_6m)
        df["area_sold_price_median_12m"] = df["area"].map(context.area_median_price_12m)

        df["area_sold_price_median_1m"] = df["area_sold_price_median_1m"].fillna(
            context.global_area_median_price_1m
        )
        df["area_sold_price_median_3m"] = df["area_sold_price_median_3m"].fillna(
            context.global_area_median_price_3m
        )
        df["area_sold_price_median_6m"] = df["area_sold_price_median_6m"].fillna(
            context.global_area_median_price_6m
        )
        df["area_sold_price_median_12m"] = df["area_sold_price_median_12m"].fillna(
            context.global_area_median_price_12m
        )

        df["area_sales_volume_1m"] = df["area"].map(context.area_sales_volume_1m).fillna(0.0)
        df["area_sales_volume_3m"] = df["area"].map(context.area_sales_volume_3m).fillna(0.0)
        df["area_sales_volume_6m"] = df["area"].map(context.area_sales_volume_6m).fillna(0.0)
        df["area_sales_volume_12m"] = df["area"].map(context.area_sales_volume_12m).fillna(0.0)

    # Fill missing values with fallbacks (same order as original)
    df["area_sold_price_median_6m"] = df["area_sold_price_median_6m"].fillna(
        df["area_sold_price_median_12m"]
    )
    df["area_sold_price_median_3m"] = df["area_sold_price_median_3m"].fillna(
        df["area_sold_price_median_6m"]
    )
    df["area_sold_price_median_1m"] = df["area_sold_price_median_1m"].fillna(
        df["area_sold_price_median_3m"]
    )

    global_listing_median = df["listing_price"].median(skipna=True)
    df["area_sold_price_median_12m"] = df["area_sold_price_median_12m"].fillna(
        global_listing_median
    )
    df["area_sold_price_median_6m"] = df["area_sold_price_median_6m"].fillna(global_listing_median)
    df["area_sold_price_median_3m"] = df["area_sold_price_median_3m"].fillna(global_listing_median)
    df["area_sold_price_median_1m"] = df["area_sold_price_median_1m"].fillna(global_listing_median)

    df["area_sales_volume_6m"] = df["area_sales_volume_6m"].fillna(df["area_sales_volume_12m"])
    df["area_sales_volume_3m"] = df["area_sales_volume_3m"].fillna(df["area_sales_volume_6m"])
    df["area_sales_volume_1m"] = df["area_sales_volume_1m"].fillna(df["area_sales_volume_3m"])
    df["area_sales_volume_12m"] = df["area_sales_volume_12m"].fillna(0.0)
    df["area_sales_volume_6m"] = df["area_sales_volume_6m"].fillna(0.0)
    df["area_sales_volume_3m"] = df["area_sales_volume_3m"].fillna(0.0)
    df["area_sales_volume_1m"] = df["area_sales_volume_1m"].fillna(0.0)

    return df
