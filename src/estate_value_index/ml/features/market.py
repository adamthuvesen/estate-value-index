from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

from estate_value_index.ml.features.context import FeatureEngineeringContext, _ensure_timestamp

"""Market-level economic features from local reference data."""


ECONOMY_DIR = Path(__file__).resolve().parents[4] / "data" / "reference" / "economy"

MARKET_FEATURE_DEFAULTS: dict[str, float] = {
    "market_interest_rate": 0.0,
    "market_interest_rate_change_3m": 0.0,
    "market_economic_tendency": 100.0,
    "market_consumer_confidence": 100.0,
    "market_construction_confidence": 100.0,
    "market_gdp_growth": 0.0,
    "market_ppsqm_index": 0.0,
    "market_ppsqm_index_change_3m": 0.0,
    "market_sales_volume": 0.0,
    "market_months_since_2020": 0.0,
    "market_data_age_months": 0.0,
}


def create_market_features(
    df: pd.DataFrame,
    context: FeatureEngineeringContext | None,
) -> pd.DataFrame:
    """Attach as-of macro and market index features.

    Historical training rows use their sold month as the valuation month. Live
    inference rows usually have no sold_date, so they fall back to scraped_at
    and then the model context reference date. External monthly sources are
    shifted to the previous month to avoid same-month lookahead.
    """
    as_of_date = _as_of_date(df, context)
    lookup_month = _month_start(as_of_date) - pd.DateOffset(months=1)

    market_table = _load_market_table()
    if market_table.empty:
        _fill_market_defaults(df)
        return df

    lookup = pd.DataFrame({"_orig_idx": df.index, "_lookup_month": lookup_month})
    lookup = lookup.sort_values("_lookup_month")
    joined = pd.merge_asof(
        lookup,
        market_table.sort_values("market_month"),
        left_on="_lookup_month",
        right_on="market_month",
        direction="backward",
    ).set_index("_orig_idx")

    feature_values = pd.DataFrame(index=df.index)
    for column, default in MARKET_FEATURE_DEFAULTS.items():
        if column == "market_months_since_2020":
            value = _months_since_2020(lookup_month)
            feature_values[column] = value.reindex(df.index).astype(float)
            continue
        if column == "market_data_age_months":
            feature_values[column] = _data_age_months(lookup_month, joined["market_month"]).reindex(
                df.index
            )
            feature_values[column] = feature_values[column].fillna(0.0).astype(float)
            continue

        if column in joined.columns:
            feature_values[column] = joined[column].reindex(df.index).astype(float).fillna(default)
        else:
            feature_values[column] = default

    return pd.concat([df, feature_values], axis=1)


def _as_of_date(
    df: pd.DataFrame,
    context: FeatureEngineeringContext | None,
) -> pd.Series:
    fallback = context.reference_date if context else pd.Timestamp.now()
    fallback = pd.Timestamp(fallback)

    dates = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")

    if "sold_date" in df.columns:
        sold_date = _ensure_timestamp(df["sold_date"], df.index, fallback)
        dates = dates.fillna(sold_date)
    if "scraped_at" in df.columns:
        scraped_at = _ensure_timestamp(df["scraped_at"], df.index, fallback)
        dates = dates.fillna(scraped_at)

    return dates.fillna(fallback)


def _month_start(values: pd.Series) -> pd.Series:
    return values.dt.to_period("M").dt.to_timestamp()


def _months_since_2020(months: pd.Series) -> pd.Series:
    return (months.dt.year - 2020) * 12 + (months.dt.month - 1)


def _data_age_months(lookup_month: pd.Series, data_month: pd.Series) -> pd.Series:
    age = (lookup_month.dt.year - data_month.dt.year) * 12 + (
        lookup_month.dt.month - data_month.dt.month
    )
    return age.clip(lower=0)


def _fill_market_defaults(df: pd.DataFrame) -> None:
    for column, default in MARKET_FEATURE_DEFAULTS.items():
        df[column] = default


@lru_cache(maxsize=1)
def _load_market_table() -> pd.DataFrame:
    frames = [
        _load_interest_rates(),
        _load_ki_indicators(),
        _load_gdp(),
        _load_sales_index(),
    ]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return pd.DataFrame()

    start = min(frame["market_month"].min() for frame in frames)
    end = max(frame["market_month"].max() for frame in frames)
    monthly = pd.DataFrame({"market_month": pd.date_range(start, end, freq="MS")})

    for frame in frames:
        monthly = monthly.merge(frame, on="market_month", how="left")

    monthly = monthly.sort_values("market_month")
    feature_columns = [column for column in MARKET_FEATURE_DEFAULTS if column in monthly.columns]
    monthly[feature_columns] = monthly[feature_columns].ffill()
    for column, default in MARKET_FEATURE_DEFAULTS.items():
        if column in {"market_months_since_2020", "market_data_age_months"}:
            continue
        if column not in monthly.columns:
            monthly[column] = default
        else:
            monthly[column] = monthly[column].fillna(default)

    return monthly


def _load_interest_rates() -> pd.DataFrame:
    path = ECONOMY_DIR / "swedish_interest_rates_monthly.csv"
    if not path.exists():
        return pd.DataFrame()

    rates = pd.read_csv(path)
    if rates.empty or "year_month" not in rates.columns:
        return pd.DataFrame()

    rates["market_month"] = pd.to_datetime(rates["year_month"], errors="coerce")
    rates["market_interest_rate"] = pd.to_numeric(rates["average_rate"], errors="coerce")
    rates = rates.sort_values("market_month")
    rates["market_interest_rate_change_3m"] = rates["market_interest_rate"] - rates[
        "market_interest_rate"
    ].shift(3)
    return rates[["market_month", "market_interest_rate", "market_interest_rate_change_3m"]].dropna(
        subset=["market_month"]
    )


def _load_ki_indicators() -> pd.DataFrame:
    path = ECONOMY_DIR / "swedish_ki_indicators_monthly.csv"
    if not path.exists():
        return pd.DataFrame()

    indicators = pd.read_csv(path)
    required = {"period", "indicator_name", "value"}
    if indicators.empty or not required.issubset(indicators.columns):
        return pd.DataFrame()

    indicators["market_month"] = pd.to_datetime(
        indicators["period"].astype(str).str.replace("M", "-", regex=False),
        errors="coerce",
    )
    indicators["value"] = pd.to_numeric(indicators["value"], errors="coerce")
    pivot = indicators.pivot_table(
        index="market_month",
        columns="indicator_name",
        values="value",
        aggfunc="last",
    ).reset_index()
    rename = {
        "Economic_Tendency_Indicator": "market_economic_tendency",
        "Consumer_Confidence": "market_consumer_confidence",
        "Construction_Confidence": "market_construction_confidence",
    }
    pivot = pivot.rename(columns=rename)
    keep = ["market_month", *rename.values()]
    return pivot[[column for column in keep if column in pivot.columns]].dropna(
        subset=["market_month"]
    )


def _load_gdp() -> pd.DataFrame:
    path = ECONOMY_DIR / "swedish_economic_indicators_quarterly.csv"
    if not path.exists():
        return pd.DataFrame()

    gdp = pd.read_csv(path)
    if gdp.empty or not {"period", "gdp_growth_percent"}.issubset(gdp.columns):
        return pd.DataFrame()

    gdp["market_month"] = pd.to_datetime(gdp["period"], errors="coerce")
    gdp["market_gdp_growth"] = pd.to_numeric(gdp["gdp_growth_percent"], errors="coerce")
    return gdp[["market_month", "market_gdp_growth"]].dropna(subset=["market_month"])


def _load_sales_index() -> pd.DataFrame:
    path = ECONOMY_DIR / "sales_data_48_months.csv"
    if not path.exists():
        return pd.DataFrame()

    sales = pd.read_csv(path)
    if sales.empty or not {"Månad", "kr/kvm", "antal försäljningar"}.issubset(sales.columns):
        return pd.DataFrame()

    sales["market_month"] = sales["Månad"].apply(_parse_swedish_month)
    sales["market_ppsqm_index"] = pd.to_numeric(sales["kr/kvm"], errors="coerce")
    sales["market_sales_volume"] = pd.to_numeric(sales["antal försäljningar"], errors="coerce")
    sales = sales.sort_values("market_month")
    sales["market_ppsqm_index_change_3m"] = (
        sales["market_ppsqm_index"] / sales["market_ppsqm_index"].shift(3) - 1.0
    )
    return sales[
        [
            "market_month",
            "market_ppsqm_index",
            "market_ppsqm_index_change_3m",
            "market_sales_volume",
        ]
    ].dropna(subset=["market_month"])


def _parse_swedish_month(value: object) -> pd.Timestamp | pd.NaT:
    if not isinstance(value, str):
        return pd.NaT

    month_names = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "maj": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "okt": 10,
        "nov": 11,
        "dec": 12,
    }
    parts = value.strip().lower().split()
    if len(parts) != 2:
        return pd.NaT

    month = month_names.get(parts[0])
    year_suffix = parts[1].replace("-", "")
    if month is None or not year_suffix.isdigit():
        return pd.NaT

    year = 2000 + int(year_suffix)
    return pd.Timestamp(year=year, month=month, day=1)
