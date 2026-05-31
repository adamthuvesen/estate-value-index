from __future__ import annotations

import pandas as pd

from estate_value_index.ml.constants import TARGET_ENCODING_SMOOTHING
from estate_value_index.ml.features.context import FeatureEngineeringContext

"""Target encoding using only prior sales (temporal awareness)."""


def _create_target_encoding(
    df: pd.DataFrame, context: FeatureEngineeringContext | None
) -> pd.DataFrame:
    """Create target-encoded features using only sales strictly before each row's date."""
    if context is None:
        # Training mode: pre-aggregate same-day same-area rows so two listings
        # with identical (area, sold_date) do not contribute each other's
        # sold_price to the encoding. For each row at date D in area A, the
        # encoding is the mean of all sold_price values in A whose sold_date < D.
        if "sold_price" in df.columns and "sold_date" in df.columns:
            global_mean = float(df["sold_price"].mean())
            smoothing = TARGET_ENCODING_SMOOTHING

            df["sold_date"] = pd.to_datetime(df["sold_date"], errors="coerce")

            # Per-(area, sold_date) aggregates collapse same-day same-area ties.
            daily = (
                df.dropna(subset=["sold_price", "sold_date", "area"])
                .groupby(["area", "sold_date"], observed=True)["sold_price"]
                .agg(day_sum="sum", day_count="size")
                .reset_index()
                .sort_values(["area", "sold_date"])
            )
            grouped_daily = daily.groupby("area", observed=True)
            daily["prior_sum"] = grouped_daily["day_sum"].cumsum().shift(1)
            daily["prior_count"] = grouped_daily["day_count"].cumsum().shift(1)
            # Within an area, the first day's prior_* are NaN (no history).
            first_day_mask = grouped_daily.cumcount() == 0
            daily.loc[first_day_mask, ["prior_sum", "prior_count"]] = (0.0, 0.0)

            denom = daily["prior_count"] + smoothing
            daily["encoded"] = (daily["prior_sum"] + smoothing * global_mean) / denom
            daily.loc[denom == 0, "encoded"] = global_mean

            df = df.merge(
                daily[["area", "sold_date", "encoded"]],
                on=["area", "sold_date"],
                how="left",
            )
            df["area_target_encoded"] = df["encoded"].fillna(global_mean)
            df = df.drop(columns=["encoded"])
        else:
            df["area_target_encoded"] = 0.0
    else:
        # Inference mode: Use cached values
        encoded = df["area"].map(context.area_target_mean)
        df["area_target_encoded"] = encoded.fillna(context.global_target_mean)

    if context and context.area_avg_price:
        df["area_avg_price"] = df["area"].map(context.area_avg_price)
        df["area_listing_count"] = df["area"].map(context.area_listing_count).fillna(0)
    else:
        area_stats = (
            df.groupby("area", dropna=False, observed=True)["listing_price"]
            .agg(["mean", "count"])
            .reset_index()
        )
        area_stats.columns = ["area", "area_avg_price", "area_listing_count"]
        df = df.merge(area_stats, on="area", how="left")

    fallback_avg_price = None
    if context and context.global_listing_price_mean is not None:
        fallback_avg_price = context.global_listing_price_mean
    elif "listing_price" in df:
        fallback_avg_price = df["listing_price"].median(skipna=True)
    df["area_avg_price"] = df["area_avg_price"].fillna(fallback_avg_price)
    df["area_listing_count"] = df["area_listing_count"].fillna(0)

    return df
