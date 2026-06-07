#!/usr/bin/env python3
"""CLI for geocoding new addresses to BigQuery.

Usage:
    uv run python -m estate_value_index.cli.geocode_addresses --batch-size 100
    uv run python -m estate_value_index.cli.geocode_addresses --all  # Geocode all missing (slow!)
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import Namespace


def geocode_new_addresses(
    project_id: str | None = None,
    batch_size: int = 100,
    rate_limit_delay: float = 1.1,
    dry_run: bool = False,
) -> dict:
    """Geocode addresses not yet in the geocode cache. Returns run statistics."""
    from google.cloud import bigquery

    from estate_value_index.ml.geocoding import geocode_address
    from estate_value_index.utils.bigquery_safety import _validate_bq_project_id, safe_table_ref
    from estate_value_index.utils.clients import get_bq_client
    from estate_value_index.utils.settings import load_env_config

    env_config = load_env_config()
    project_id = _validate_bq_project_id(project_id or env_config.bigquery_project_id)

    client = get_bq_client(project_id)

    query = f"""
    WITH listing_addresses AS (
        SELECT DISTINCT
            address,
            area,
            CONCAT(address, ', ', LOWER(REPLACE(REPLACE(REPLACE(REPLACE(area, 'ö', 'o'), 'ä', 'a'), 'å', 'a'), ' ', '_'))) as geocode_key
        FROM {safe_table_ref(project_id, "booli_raw", "listings", quote=True)}
        WHERE address IS NOT NULL AND area IS NOT NULL
    ),
    existing_geocodes AS (
        SELECT address as geocode_key
        FROM {safe_table_ref(project_id, "booli_raw", "geocodes", quote=True)}
    )
    SELECT la.address, la.area, la.geocode_key
    FROM listing_addresses la
    LEFT JOIN existing_geocodes eg ON la.geocode_key = eg.geocode_key
    WHERE eg.geocode_key IS NULL
    LIMIT @batch_size
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("batch_size", "INT64", batch_size),
        ]
    )

    print("Querying for addresses not yet geocoded...")
    missing_df = client.query(query, job_config=job_config).to_dataframe()

    new_addresses = len(missing_df)
    print(f"Found {new_addresses} addresses to geocode")

    if new_addresses == 0:
        print("All addresses already geocoded!")
        return {"new_addresses": 0, "geocoded": 0, "failed": 0}

    if dry_run:
        print("\nDRY RUN - would geocode:")
        for _i, row in missing_df.head(10).iterrows():
            print(f"   {row['address']}, {row['area']}")
        if new_addresses > 10:
            print(f"   ... and {new_addresses - 10} more")
        return {"new_addresses": new_addresses, "geocoded": 0, "failed": 0, "dry_run": True}

    try:
        from geopy.geocoders import Nominatim
    except ImportError:
        print("geopy not installed - run: pip install geopy")
        return {
            "new_addresses": new_addresses,
            "geocoded": 0,
            "failed": 0,
            "error": "geopy not installed",
        }

    geolocator = Nominatim(user_agent="estate-value-index-cli")

    new_geocodes: list[dict] = []
    geocoded = 0
    failed = 0

    eta_min = new_addresses * rate_limit_delay / 60
    print(f"\nGeocoding {new_addresses} addresses (this will take ~{eta_min:.1f} minutes)...")

    for i, row in missing_df.iterrows():
        address = row["address"]
        area = row["area"]
        geocode_key = row["geocode_key"]
        print(f"  [{i + 1}/{new_addresses}] {address}, {area}", end=" ")

        try:
            coords = geocode_address(address, area, geolocator)
            if coords:
                lat, lon = coords
                new_geocodes.append(
                    {
                        "address": geocode_key,
                        "lat": lat,
                        "lon": lon,
                        "geocoded_at": datetime.now(UTC).isoformat(),
                        "source": "nominatim",
                    }
                )
                geocoded += 1
                print(f"({lat:.4f}, {lon:.4f})")
            else:
                # Persist a NULL-coord row so we don't retry the same miss.
                new_geocodes.append(
                    {
                        "address": geocode_key,
                        "lat": None,
                        "lon": None,
                        "geocoded_at": datetime.now(UTC).isoformat(),
                        "source": "nominatim_failed",
                    }
                )
                failed += 1
                print("(not found)")
        except Exception as e:
            print(f"(error: {e})")
            failed += 1

        time.sleep(rate_limit_delay)

    if new_geocodes:
        print(f"\nUploading {len(new_geocodes)} geocodes to BigQuery...")
        geocodes_table = safe_table_ref(project_id, "booli_raw", "geocodes")
        errors = client.insert_rows_json(geocodes_table, new_geocodes)
        if errors:
            print(f"BigQuery insert errors: {errors[:3]}")
        else:
            print(f"Uploaded {len(new_geocodes)} geocodes")

    print(f"\nSummary: {geocoded} geocoded, {failed} failed out of {new_addresses} total")

    return {
        "new_addresses": new_addresses,
        "geocoded": geocoded,
        "failed": failed,
    }


def main(argv: list[str] | None = None, *, args: Namespace | None = None) -> int:
    """Run the geocoder. ``args`` takes precedence over ``argv`` when given."""
    if args is None:
        parser = argparse.ArgumentParser(description="Geocode new addresses to BigQuery")
        parser.add_argument(
            "--project-id",
            type=str,
            default=None,
            help="GCP project ID (default: from environment config)",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Maximum addresses to geocode per run (default: 100)",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            dest="geocode_all",
            help="Geocode ALL missing addresses (can be very slow!)",
        )
        parser.add_argument(
            "--rate-limit",
            type=float,
            default=1.1,
            help="Delay between requests in seconds (default: 1.1)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be geocoded without actually doing it",
        )
        args = parser.parse_args(argv)

    batch_size = 10000 if args.geocode_all else args.batch_size

    try:
        result = geocode_new_addresses(
            project_id=args.project_id,
            batch_size=batch_size,
            rate_limit_delay=args.rate_limit,
            dry_run=args.dry_run,
        )
        return 0 if result.get("geocoded", 0) >= 0 else 1
    except Exception as e:
        print(f"Geocoding failed: {e}")
        if not isinstance(e, ValueError):
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
