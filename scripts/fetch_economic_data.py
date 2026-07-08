# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "requests",
#     "pandas",
# ]
# ///
"""Refresh Swedish economy reference data used by market ML features."""

from __future__ import annotations

import argparse
import html
import json
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd
import requests

DATA_DIR = Path(__file__).parent.parent / "data" / "reference" / "economy"

RIKSBANK_POLICY_RATE_URL = (
    "https://api.riksbank.se/swea/v1/Observations/SECBREPOEFF/{from_date}/{to_date}"
)
KI_INDICATORS_URL = "https://statistik.konj.se/PXWeb/api/v1/en/KonjBar/Indikatorer/Indikatorm.px"
SCB_GDP_URL = "https://api.scb.se/OV0104/v1/doris/en/ssd/NR/NR0103/NR0103B/NR0103ENS2010T10SKv"
MAKLARSTATISTIK_CENTRAL_STOCKHOLM_URL = (
    "https://www.maklarstatistik.se/omrade/riket/stockholms-lan/stockholm/centrala-stockholm/"
)

KI_INDICATORS = ["KIFI", "BTOT", "BBYG", "bhus", "bhusmakro", "bhusmikro"]
KI_INDICATOR_NAMES = {
    "KIFI": "Economic_Tendency_Indicator",
    "BTOT": "Business_Sector_Confidence",
    "BBYG": "Construction_Confidence",
    "bhus": "Consumer_Confidence",
    "bhusmakro": "Consumer_Macro_Index",
    "bhusmikro": "Consumer_Micro_Index",
}
KI_SORT_ORDER = {indicator: idx for idx, indicator in enumerate(KI_INDICATORS)}

SWEDISH_MONTHS = {
    1: "jan",
    2: "feb",
    3: "mar",
    4: "apr",
    5: "maj",
    6: "jun",
    7: "jul",
    8: "aug",
    9: "sep",
    10: "okt",
    11: "nov",
    12: "dec",
}
SWEDISH_MONTH_LOOKUP = {value: key for key, value in SWEDISH_MONTHS.items()}


class ChartCanvasParser(HTMLParser):
    """Pull chart metadata from Mäklarstatistik canvas tags."""

    def __init__(self) -> None:
        super().__init__()
        self.canvases: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "canvas":
            return

        values = dict(attrs)
        class_name = values.get("class") or ""
        if "chartjs" in class_name:
            self.canvases.append(values)


def fetch_riksbank_policy_rate(
    session: requests.Session, from_date: date, to_date: date
) -> list[dict]:
    url = RIKSBANK_POLICY_RATE_URL.format(
        from_date=from_date.isoformat(), to_date=to_date.isoformat()
    )
    response = session.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def process_riksbank_to_monthly(data: list[dict]) -> pd.DataFrame:
    if not data:
        return pd.DataFrame(columns=["year_month", "average_rate", "days_in_month"])

    rates = pd.DataFrame(data)
    rates["date"] = pd.to_datetime(rates["date"], errors="coerce")
    rates["value"] = pd.to_numeric(rates["value"], errors="coerce")
    rates = rates.dropna(subset=["date", "value"])
    if rates.empty:
        return pd.DataFrame(columns=["year_month", "average_rate", "days_in_month"])

    rates["year_month"] = rates["date"].dt.to_period("M").astype(str)
    return (
        rates.groupby("year_month")
        .agg(average_rate=("value", "mean"), days_in_month=("value", "count"))
        .reset_index()
    )


def fetch_ki_metadata(session: requests.Session) -> dict:
    response = session.get(KI_INDICATORS_URL, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_ki_indicators(session: requests.Session, periods: list[str]) -> pd.DataFrame:
    if not periods:
        return pd.DataFrame(columns=["period", "indicator_code", "indicator_name", "value"])

    query = {
        "query": [
            {"code": "Indikator", "selection": {"filter": "item", "values": KI_INDICATORS}},
            {"code": "Period", "selection": {"filter": "item", "values": periods}},
        ],
        "response": {"format": "json"},
    }
    response = session.post(KI_INDICATORS_URL, json=query, timeout=30)
    response.raise_for_status()

    rows = []
    for row in response.json()["data"]:
        indicator, period = row["key"]
        value = row["values"][0]
        rows.append(
            {
                "period": period,
                "indicator_code": indicator,
                "indicator_name": KI_INDICATOR_NAMES.get(indicator, indicator),
                "value": float(value) if value else None,
            }
        )

    result = pd.DataFrame(rows)
    return _sort_ki_indicators(result)


def fetch_scb_metadata(session: requests.Session) -> dict:
    response = session.get(SCB_GDP_URL, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_scb_gdp(session: requests.Session, quarters: list[str]) -> pd.DataFrame:
    if not quarters:
        return pd.DataFrame(columns=["period", "quarter", "gdp_growth_percent"])

    query = {
        "query": [
            {"code": "Anvandningstyp", "selection": {"filter": "item", "values": ["BNPM"]}},
            {"code": "ContentsCode", "selection": {"filter": "item", "values": ["NR0103CF"]}},
            {"code": "Tid", "selection": {"filter": "item", "values": quarters}},
        ],
        "response": {"format": "json"},
    }
    response = session.post(SCB_GDP_URL, json=query, timeout=30)
    response.raise_for_status()

    rows = []
    for row in response.json()["data"]:
        quarter = row["key"][1]
        rows.append(
            {
                "period": _quarter_to_month(quarter),
                "quarter": quarter,
                "gdp_growth_percent": float(row["values"][0]) if row["values"][0] else None,
            }
        )

    return pd.DataFrame(rows).sort_values("quarter", key=lambda col: col.map(_quarter_key))


def fetch_maklarstatistik_sales(session: requests.Session, url: str) -> tuple[pd.DataFrame, str]:
    response = session.get(url, timeout=30)
    response.raise_for_status()

    parser = ChartCanvasParser()
    parser.feed(response.text)

    ppsqm = _find_chart(parser.canvases, "br-48m-prisutveckling")
    volume = _find_chart(parser.canvases, "br-48m-antal-salda")
    ppsqm_labels, ppsqm_values = _chart_labels_and_values(ppsqm)
    volume_labels, volume_values = _chart_labels_and_values(volume)
    if ppsqm_labels != volume_labels:
        raise ValueError("Mäklarstatistik price and sales charts use different months")

    rows = []
    for label, ppsqm_value, volume_value in zip(
        ppsqm_labels, ppsqm_values, volume_values, strict=True
    ):
        rows.append(
            {
                "Månad": _normalize_swedish_month_label(label),
                "kr/kvm": round(float(ppsqm_value)),
                "antal försäljningar": round(float(volume_value)),
            }
        )

    area_name = _find_meta_content(response.text, "og:title") or url.rstrip("/").split("/")[-1]
    return pd.DataFrame(rows), area_name


def update_interest_rates(session: requests.Session, to_date: date, replace: bool) -> Path | None:
    path = DATA_DIR / "swedish_interest_rates_monthly.csv"
    existing = pd.read_csv(path)
    existing["year_month"] = existing["year_month"].astype(str)
    next_month = _month_after(existing["year_month"].max())
    fetch_end = _last_complete_month_end(to_date)

    print("\n1. Riksbanken policy rate")
    print(f"   Local latest: {existing['year_month'].max()}")
    if next_month > fetch_end:
        print("   No complete missing months.")
        return None

    monthly = process_riksbank_to_monthly(
        fetch_riksbank_policy_rate(session, next_month, fetch_end)
    )
    updated = _append_new_rows(existing, monthly, key="year_month")
    output = _write_reference_file(
        updated,
        "swedish_interest_rates_monthly.csv",
        replace=replace,
        changed=len(updated) > len(existing),
    )
    print(
        f"   Added {len(updated) - len(existing)} months; latest is {updated['year_month'].max()}."
    )
    return output


def update_ki_indicators(session: requests.Session, to_date: date, replace: bool) -> Path | None:
    path = DATA_DIR / "swedish_ki_indicators_monthly.csv"
    existing = pd.read_csv(path)
    existing_periods = set(existing["period"].astype(str))
    latest_local = max(existing_periods, key=_ki_period_key)
    max_complete_period = _date_to_ki_period(_last_complete_month_end(to_date))
    available = _metadata_values(fetch_ki_metadata(session), "Period")
    periods_to_fetch = [
        period
        for period in available
        if _ki_period_key(latest_local)
        < _ki_period_key(period)
        <= _ki_period_key(max_complete_period)
        and period not in existing_periods
    ]

    print("\n2. Konjunkturinstitutet indicators")
    print(f"   Local latest: {latest_local}")
    if not periods_to_fetch:
        print("   No missing released periods.")
        return None

    new_data = fetch_ki_indicators(session, periods_to_fetch)
    updated = pd.concat([existing, new_data], ignore_index=True)
    output = _write_reference_file(
        updated,
        "swedish_ki_indicators_monthly.csv",
        replace=replace,
        changed=True,
    )
    latest_updated = max(updated["period"].astype(str), key=_ki_period_key)
    print(f"   Added {len(new_data)} values across {len(periods_to_fetch)} periods.")
    print(f"   Latest is {latest_updated}.")
    return output


def update_gdp(session: requests.Session, replace: bool) -> Path | None:
    path = DATA_DIR / "swedish_economic_indicators_quarterly.csv"
    existing = pd.read_csv(path)
    existing_quarters = set(existing["quarter"].astype(str))
    latest_local = max(existing_quarters, key=_quarter_key)
    available = _metadata_values(fetch_scb_metadata(session), "Tid")
    quarters_to_fetch = [
        quarter
        for quarter in available
        if _quarter_key(quarter) > _quarter_key(latest_local) and quarter not in existing_quarters
    ]

    print("\n3. SCB GDP growth")
    print(f"   Local latest: {latest_local}")
    if not quarters_to_fetch:
        print("   No missing released quarters.")
        return None

    new_data = fetch_scb_gdp(session, quarters_to_fetch)
    updated = pd.concat([existing, new_data], ignore_index=True)
    output = _write_reference_file(
        updated,
        "swedish_economic_indicators_quarterly.csv",
        replace=replace,
        changed=True,
    )
    latest_updated = max(updated["quarter"].astype(str), key=_quarter_key)
    print(f"   Added {len(new_data)} quarters; latest is {latest_updated}.")
    return output


def update_sales_data(session: requests.Session, sales_url: str, replace: bool) -> Path | None:
    path = DATA_DIR / "sales_data_48_months.csv"
    existing = pd.read_csv(path)
    fetched, area_name = fetch_maklarstatistik_sales(session, sales_url)
    updated = _merge_sales_data(existing, fetched)
    changed = not updated.equals(existing)

    print("\n4. Mäklarstatistik monthly apartment sales")
    print(f"   Source: {area_name}")
    print(f"   Local latest: {existing['Månad'].iloc[-1]}")
    print(f"   Source latest: {fetched['Månad'].iloc[-1]}")
    if not changed:
        print("   No changes.")
        return None

    output = _write_reference_file(
        updated,
        "sales_data_48_months.csv",
        replace=replace,
        changed=True,
    )
    print(f"   Rows after merge: {len(updated)}.")
    return output


def _write_reference_file(
    data: pd.DataFrame, filename: str, *, replace: bool, changed: bool
) -> Path | None:
    if not changed:
        return None

    output = DATA_DIR / filename if replace else DATA_DIR / filename.replace(".csv", "_updated.csv")
    data.to_csv(output, index=False)
    print(f"   Wrote {output}")
    return output


def _append_new_rows(existing: pd.DataFrame, new_data: pd.DataFrame, key: str) -> pd.DataFrame:
    if new_data.empty:
        return existing

    new_rows = new_data[~new_data[key].astype(str).isin(set(existing[key].astype(str)))]
    if new_rows.empty:
        return existing

    updated = pd.concat([existing, new_rows], ignore_index=True)
    return updated.sort_values(key).reset_index(drop=True)


def _sort_ki_indicators(data: pd.DataFrame) -> pd.DataFrame:
    if data.empty:
        return data

    sorted_data = data.copy()
    sorted_data["_period_sort"] = sorted_data["period"].map(_ki_period_key)
    sorted_data["_indicator_sort"] = sorted_data["indicator_code"].map(KI_SORT_ORDER)
    return (
        sorted_data.sort_values(["_period_sort", "_indicator_sort"])
        .drop(columns=["_period_sort", "_indicator_sort"])
        .reset_index(drop=True)
    )


def _metadata_values(metadata: dict, code: str) -> list[str]:
    for variable in metadata["variables"]:
        if variable["code"] == code:
            return list(variable["values"])
    raise ValueError(f"Metadata variable not found: {code}")


def _find_chart(canvases: list[dict[str, str | None]], chart_name: str) -> dict[str, str | None]:
    for canvas in canvases:
        if canvas.get("data-chart") == chart_name:
            return canvas
    raise ValueError(f"Mäklarstatistik chart not found: {chart_name}")


def _chart_labels_and_values(canvas: dict[str, str | None]) -> tuple[list[str], list[str]]:
    labels = json.loads(html.unescape(canvas["data-labels"] or "[]"))
    series = json.loads(html.unescape(canvas["data-series"] or "[]"))
    if not series:
        raise ValueError(f"Chart has no series: {canvas.get('data-chart')}")
    return labels, series[0]


def _find_meta_content(page: str, property_name: str) -> str | None:
    marker = f'property="{property_name}"'
    index = page.find(marker)
    if index < 0:
        return None
    content_marker = 'content="'
    content_start = page.find(content_marker, index)
    if content_start < 0:
        return None
    content_start += len(content_marker)
    content_end = page.find('"', content_start)
    if content_end < 0:
        return None
    return html.unescape(page[content_start:content_end])


def _merge_sales_data(existing: pd.DataFrame, fetched: pd.DataFrame) -> pd.DataFrame:
    existing = existing.copy()
    fetched = fetched.copy()
    existing["_month"] = existing["Månad"].map(_parse_swedish_month)
    fetched["_month"] = fetched["Månad"].map(_parse_swedish_month)

    historical_only = existing[~existing["_month"].isin(set(fetched["_month"]))]
    updated = pd.concat([historical_only, fetched], ignore_index=True)
    updated = updated.dropna(subset=["_month"]).sort_values("_month")
    updated = updated[["Månad", "kr/kvm", "antal försäljningar"]].reset_index(drop=True)
    updated["kr/kvm"] = pd.to_numeric(updated["kr/kvm"], errors="raise").round().astype(int)
    updated["antal försäljningar"] = (
        pd.to_numeric(updated["antal försäljningar"], errors="raise").round().astype(int)
    )
    return updated


def _last_complete_month_end(value: date) -> date:
    return value.replace(day=1) - timedelta(days=1)


def _month_after(year_month: str) -> date:
    timestamp = pd.Period(year_month, freq="M").to_timestamp()
    return (timestamp + pd.DateOffset(months=1)).date()


def _date_to_ki_period(value: date) -> str:
    return f"{value.year}M{value.month:02d}"


def _ki_period_key(period: str) -> tuple[int, int]:
    year, month = period.split("M", maxsplit=1)
    return int(year), int(month)


def _quarter_to_month(quarter: str) -> str:
    year = quarter[:4]
    quarter_number = int(quarter[-1])
    month = (quarter_number - 1) * 3 + 1
    return f"{year}-{month:02d}"


def _quarter_key(quarter: str) -> tuple[int, int]:
    return int(quarter[:4]), int(quarter[-1])


def _parse_swedish_month(value: object) -> pd.Timestamp | pd.NaT:
    if not isinstance(value, str):
        return pd.NaT

    parts = value.strip().lower().split()
    if len(parts) != 2:
        return pd.NaT

    month = SWEDISH_MONTH_LOOKUP.get(parts[0])
    year_suffix = parts[1].replace("-", "")
    if month is None or not year_suffix.isdigit():
        return pd.NaT

    return pd.Timestamp(year=2000 + int(year_suffix), month=month, day=1)


def _normalize_swedish_month_label(value: str) -> str:
    timestamp = _parse_swedish_month(value)
    if pd.isna(timestamp):
        raise ValueError(f"Bad Swedish month label: {value}")
    return f"{SWEDISH_MONTHS[timestamp.month]} -{str(timestamp.year)[-2:]}"


def _parse_to_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Swedish economy data updates")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace the reference CSVs. Without this, write *_updated.csv files.",
    )
    parser.add_argument(
        "--to-date",
        type=_parse_to_date,
        default=date.today(),
        help="Refresh through this date. Monthly series use the previous complete month.",
    )
    parser.add_argument(
        "--skip-sales",
        action="store_true",
        help="Skip Mäklarstatistik monthly apartment sales.",
    )
    parser.add_argument(
        "--sales-url",
        default=MAKLARSTATISTIK_CENTRAL_STOCKHOLM_URL,
        help="Mäklarstatistik area page to use for sales_data_48_months.csv.",
    )
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()

    print("Refreshing Swedish economy reference data")
    print(f"Data directory: {DATA_DIR}")
    print(f"Complete monthly data through: {_last_complete_month_end(args.to_date)}")
    if not args.replace:
        print("Dry write mode: use --replace to update the source CSVs.")

    outputs = [
        update_interest_rates(session, args.to_date, args.replace),
        update_ki_indicators(session, args.to_date, args.replace),
        update_gdp(session, args.replace),
    ]
    if not args.skip_sales:
        outputs.append(update_sales_data(session, args.sales_url, args.replace))

    written = [output for output in outputs if output is not None]
    print("\nSummary")
    if written:
        for output in written:
            print(f"   Updated: {output}")
    else:
        print("   No reference files changed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
