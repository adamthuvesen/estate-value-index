# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "requests",
#     "pandas",
# ]
# ///
"""
Fetch and update Swedish economic data from official sources.

Sources:
- Riksbanken: Policy rate (styrränta)
- Konjunkturinstitutet: Economic Tendency Survey indicators
- SCB: GDP growth data
"""

from pathlib import Path

import pandas as pd
import requests

DATA_DIR = Path(__file__).parent.parent / "data" / "reference" / "economy"

# Indicators we track from KI
KI_INDICATORS = ["KIFI", "BTOT", "BBYG", "bhus", "bhusmakro", "bhusmikro"]
KI_INDICATOR_NAMES = {
    "KIFI": "Economic_Tendency_Indicator",
    "BTOT": "Business_Sector_Confidence",
    "BBYG": "Construction_Confidence",
    "bhus": "Consumer_Confidence",
    "bhusmakro": "Consumer_Macro_Index",
    "bhusmikro": "Consumer_Micro_Index",
}


def fetch_riksbank_policy_rate(from_date: str, to_date: str) -> list[dict]:
    """Fetch policy rate from Riksbanken API."""
    url = f"https://api.riksbank.se/swea/v1/Observations/SECBREPOEFF/{from_date}/{to_date}"
    print(f"Fetching Riksbanken: {url}")
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def process_riksbank_to_monthly(data: list[dict]) -> pd.DataFrame:
    """Convert daily policy rate to monthly average."""
    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"])
    df["year_month"] = df["date"].dt.to_period("M").astype(str)

    monthly = (
        df.groupby("year_month")
        .agg(average_rate=("value", "mean"), days_in_month=("value", "count"))
        .reset_index()
    )
    return monthly


def fetch_ki_indicators(periods: list[str]) -> pd.DataFrame:
    """
    Fetch KI Economic Tendency Survey indicators.

    PXWeb API: https://statistik.konj.se/PXWeb/api/v1/en/KonjBar
    """
    url = "https://statistik.konj.se/PXWeb/api/v1/en/KonjBar/Indikatorer/Indikatorm.px"

    query = {
        "query": [
            {"code": "Indikator", "selection": {"filter": "item", "values": KI_INDICATORS}},
            {"code": "Period", "selection": {"filter": "item", "values": periods}},
        ],
        "response": {"format": "json"},
    }

    print(f"Fetching KI indicators for periods: {periods}")
    resp = requests.post(url, json=query, timeout=30)
    resp.raise_for_status()

    data = resp.json()

    # Parse the PXWeb JSON-stat format
    rows = []
    for row in data["data"]:
        key = row["key"]
        value = row["values"][0]
        indicator = key[0]
        period = key[1]
        rows.append(
            {
                "period": period,
                "indicator_code": indicator,
                "indicator_name": KI_INDICATOR_NAMES.get(indicator, indicator),
                "value": float(value) if value else None,
            }
        )

    return pd.DataFrame(rows)


def fetch_scb_gdp(quarters: list[str]) -> pd.DataFrame:
    """
    Fetch GDP growth data from SCB.

    API: https://api.scb.se/OV0104/v1/doris/en/ssd/NR/NR0103
    Table: NR0103ENS2010T10SKv - GDP expenditure approach, seasonally adjusted
    """
    url = "https://api.scb.se/OV0104/v1/doris/en/ssd/NR/NR0103/NR0103B/NR0103ENS2010T10SKv"

    query = {
        "query": [
            # BNPM = GDP at market prices
            {"code": "Anvandningstyp", "selection": {"filter": "item", "values": ["BNPM"]}},
            # NR0103CF = Change in volume, percent (quarter-over-quarter)
            {"code": "ContentsCode", "selection": {"filter": "item", "values": ["NR0103CF"]}},
            {"code": "Tid", "selection": {"filter": "item", "values": quarters}},
        ],
        "response": {"format": "json"},
    }

    print(f"Fetching SCB GDP for quarters: {quarters}")
    resp = requests.post(url, json=query, timeout=30)
    resp.raise_for_status()

    data = resp.json()

    rows = []
    for row in data["data"]:
        quarter = row["key"][1]  # Tid is the 2nd key (0: Anvandningstyp, 1: Tid)
        value = row["values"][0]
        # Convert quarter format: 2025K1 -> 2025-01 (first month of quarter)
        year = quarter[:4]
        q = int(quarter[-1])
        month = str((q - 1) * 3 + 1).zfill(2)
        period = f"{year}-{month}"

        rows.append(
            {
                "period": period,
                "quarter": quarter,
                "gdp_growth_percent": float(value) if value else None,
            }
        )

    return pd.DataFrame(rows)


def update_interest_rates():
    """Fetch and merge new interest rate data."""
    print("\n" + "=" * 60)
    print("1. RIKSBANKEN - Policy Rate")
    print("=" * 60)

    # Fetch Oct 2025 - Dec 2025
    data = fetch_riksbank_policy_rate("2025-10-01", "2025-12-31")
    monthly = process_riksbank_to_monthly(data)
    print(f"\nFetched monthly rates:\n{monthly.to_string(index=False)}")

    # Load existing and merge
    existing = pd.read_csv(DATA_DIR / "swedish_interest_rates_monthly.csv")
    existing_months = set(existing["year_month"])

    new_data = monthly[~monthly["year_month"].isin(existing_months)]
    if len(new_data) > 0:
        print(f"\nNew months: {new_data['year_month'].tolist()}")
        updated = pd.concat([existing, new_data], ignore_index=True)
        output = DATA_DIR / "swedish_interest_rates_monthly_updated.csv"
        updated.to_csv(output, index=False)
        print(f"Saved to: {output}")
        return output
    else:
        print("No new data to add")
        return None


def update_ki_indicators():
    """Fetch and merge new KI indicator data."""
    print("\n" + "=" * 60)
    print("2. KONJUNKTURINSTITUTET - Economic Tendency Survey")
    print("=" * 60)

    # Load existing to find what's missing
    existing = pd.read_csv(DATA_DIR / "swedish_ki_indicators_monthly.csv")
    existing_periods = set(existing["period"].unique())
    print(f"Existing data ends at: {sorted(existing_periods)[-1]}")

    # Fetch Oct-Dec 2025
    new_periods = ["2025M10", "2025M11", "2025M12"]
    periods_to_fetch = [p for p in new_periods if p not in existing_periods]

    if not periods_to_fetch:
        print("No new periods to fetch")
        return None

    new_data = fetch_ki_indicators(periods_to_fetch)
    print(f"\nFetched {len(new_data)} indicator values")
    print(new_data.head(12).to_string(index=False))

    # Merge
    updated = pd.concat([existing, new_data], ignore_index=True)
    output = DATA_DIR / "swedish_ki_indicators_monthly_updated.csv"
    updated.to_csv(output, index=False)
    print(f"\nSaved to: {output}")
    return output


def update_gdp():
    """Fetch and merge new GDP data."""
    print("\n" + "=" * 60)
    print("3. SCB - GDP Growth (Quarterly)")
    print("=" * 60)

    existing = pd.read_csv(DATA_DIR / "swedish_economic_indicators_quarterly.csv")
    existing_quarters = set(existing["quarter"].unique())
    print(f"Existing data ends at: {sorted(existing_quarters)[-1]}")

    # Fetch 2025 quarters
    new_quarters = ["2025K1", "2025K2", "2025K3"]
    quarters_to_fetch = [q for q in new_quarters if q not in existing_quarters]

    if not quarters_to_fetch:
        print("No new quarters to fetch")
        return None

    new_data = fetch_scb_gdp(quarters_to_fetch)
    print(f"\nFetched GDP data:\n{new_data.to_string(index=False)}")

    # Merge
    updated = pd.concat([existing, new_data], ignore_index=True)
    output = DATA_DIR / "swedish_economic_indicators_quarterly_updated.csv"
    updated.to_csv(output, index=False)
    print(f"\nSaved to: {output}")
    return output


def print_sales_data_instructions():
    """Print instructions for updating sales data (requires API key)."""
    print("\n" + "=" * 60)
    print("4. SALES DATA - Manual Update Required")
    print("=" * 60)
    print("""
The sales_data files require an API key from Svensk Mäklarstatistik.

To get updated data:
1. Contact info@maklarstatistik.se for API access
2. Or manually download from https://www.maklarstatistik.se

Alternative sources:
- Valueguard HOX Index: https://valueguard.se (subscription)
- SBAB Booli HPI: https://www.sbab.se (monthly reports)
- SCB Fastighetsprisindex: https://www.scb.se (quarterly, free)

Current data ends at: aug -25
Missing months: sep-25, okt-25, nov-25, dec-25
""")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch Swedish economic data updates")
    parser.add_argument(
        "--replace", action="store_true", help="Replace original files with updated ones"
    )
    args = parser.parse_args()

    update_interest_rates()
    update_ki_indicators()
    update_gdp()
    print_sales_data_instructions()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("Updated files created in data/reference/economy/:")
    print("  - swedish_interest_rates_monthly_updated.csv")
    print("  - swedish_ki_indicators_monthly_updated.csv")
    print("  - swedish_economic_indicators_quarterly_updated.csv")

    if args.replace:
        import shutil

        for name in [
            "swedish_interest_rates_monthly",
            "swedish_ki_indicators_monthly",
            "swedish_economic_indicators_quarterly",
        ]:
            src = DATA_DIR / f"{name}_updated.csv"
            dst = DATA_DIR / f"{name}.csv"
            if src.exists():
                shutil.copy(src, dst)
                src.unlink()
                print(f"  Replaced: {dst.name}")
        print("\nOriginal files have been updated.")
    else:
        print("\nRun with --replace to update original files.")
