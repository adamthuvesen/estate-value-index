"""Tasks for data quality validation."""

from typing import TypedDict

import pandas as pd
from prefect import task

from estate_value_index.pipelines.utils import get_task_logger


class DuplicateCheckResult(TypedDict):
    total_rows: int
    duplicates: int
    passed: bool


class PriceValidationResult(TypedDict):
    total_rows: int
    outliers: int
    outlier_pct: float
    min_price: float
    max_price: float
    median_price: float
    passed: bool


class CountCheckResult(TypedDict):
    total_rows: int
    min_required: int
    passed: bool


class FieldCheckResult(TypedDict):
    total_fields: int
    missing_fields: list[str]
    null_fields: list[str]
    passed: bool


class DataQualityResult(TypedDict):
    total_rows: int
    total_columns: int
    checks: dict


@task(name="check-duplicates", retries=0)
def check_duplicates(df: pd.DataFrame, id_column: str = "listing_id") -> DuplicateCheckResult:
    """Check for duplicate listings by ID.

    Args:
        df: DataFrame to check
        id_column: Column name for unique ID

    Returns:
        Duplicate check results

    Raises:
        ValueError: If duplicates found
    """
    logger = get_task_logger(__name__)

    if id_column not in df.columns:
        logger.warning(f"ID column '{id_column}' not found in DataFrame")
        return DuplicateCheckResult(total_rows=len(df), duplicates=0, passed=True)

    duplicates = df[df.duplicated(subset=[id_column], keep=False)]
    duplicate_count = len(duplicates)

    if duplicate_count > 0:
        duplicate_ids = duplicates[id_column].unique()[:5]
        logger.warning(f"Found {duplicate_count} duplicate listings: {list(duplicate_ids)}")
        raise ValueError(f"Data quality check failed: {duplicate_count} duplicate listings found")

    logger.info(f"No duplicates found ({len(df):,} unique listings)")
    return DuplicateCheckResult(total_rows=len(df), duplicates=0, passed=True)


@task(name="validate-price-ranges", retries=0)
def validate_price_ranges(
    df: pd.DataFrame,
    price_column: str = "sold_price",
    min_price: float = 1_000_000,
    max_price: float = 10_000_000,
    outlier_threshold_pct: float = 5.0,
) -> PriceValidationResult:
    """Validate that prices are within expected ranges.

    Args:
        df: DataFrame to check
        price_column: Column name for price
        min_price: Minimum expected price (SEK)
        max_price: Maximum expected price (SEK)
        outlier_threshold_pct: Max percentage of outliers allowed

    Returns:
        Price validation results

    Raises:
        ValueError: If too many outliers
    """
    logger = get_task_logger(__name__)

    if price_column not in df.columns:
        logger.warning(f"Price column '{price_column}' not found")
        return PriceValidationResult(
            total_rows=len(df),
            outliers=0,
            outlier_pct=0.0,
            min_price=0.0,
            max_price=0.0,
            median_price=0.0,
            passed=True,
        )

    if df.empty:
        raise ValueError("Data quality check failed: no rows available for price validation")

    outliers = df[(df[price_column] < min_price) | (df[price_column] > max_price)]
    outlier_count = len(outliers)
    outlier_pct = (outlier_count / len(df)) * 100

    logger.info(
        f"Price validation: {outlier_count:,} outliers ({outlier_pct:.1f}%) "
        f"outside {min_price:,.0f}-{max_price:,.0f} SEK"
    )

    if outlier_pct > outlier_threshold_pct:
        raise ValueError(
            f"Data quality check failed: {outlier_pct:.1f}% outliers "
            f"exceeds threshold {outlier_threshold_pct:.1f}%"
        )

    return PriceValidationResult(
        total_rows=len(df),
        outliers=outlier_count,
        outlier_pct=outlier_pct,
        min_price=float(df[price_column].min()),
        max_price=float(df[price_column].max()),
        median_price=float(df[price_column].median()),
        passed=True,
    )


@task(name="check-minimum-listing-count", retries=0)
def check_minimum_listing_count(df: pd.DataFrame, min_count: int = 100) -> CountCheckResult:
    """Check that dataset has minimum number of listings.

    Args:
        df: DataFrame to check
        min_count: Minimum required listings

    Returns:
        Count check results

    Raises:
        ValueError: If insufficient listings
    """
    logger = get_task_logger(__name__)

    if len(df) < min_count:
        raise ValueError(f"Data quality check failed: {len(df):,} listings < {min_count:,} minimum")

    logger.info(f"Sufficient listings: {len(df):,} >= {min_count:,}")
    return CountCheckResult(total_rows=len(df), min_required=min_count, passed=True)


@task(name="check-required-fields", retries=0)
def check_required_fields(
    df: pd.DataFrame,
    required_fields: list[str] | None = None,
) -> FieldCheckResult:
    """Check that required fields are present and not entirely null.

    Args:
        df: DataFrame to check
        required_fields: List of required field names

    Returns:
        Field check results

    Raises:
        ValueError: If required fields missing
    """
    logger = get_task_logger(__name__)

    if required_fields is None:
        required_fields = ["sold_price", "living_area", "rooms", "area", "sold_date"]

    missing_fields = []
    null_fields = []

    for field in required_fields:
        if field not in df.columns:
            missing_fields.append(field)
        elif df[field].isna().all():
            null_fields.append(field)

    if missing_fields:
        raise ValueError(f"Required fields missing: {missing_fields}")

    if null_fields:
        raise ValueError(f"Required fields entirely null: {null_fields}")

    logger.info(f"All {len(required_fields)} required fields present")

    return FieldCheckResult(
        total_fields=len(required_fields),
        missing_fields=missing_fields,
        null_fields=null_fields,
        passed=True,
    )


@task(name="run-all-data-quality-checks", retries=0)
def run_all_data_quality_checks(
    df: pd.DataFrame,
    skip_duplicates: bool = False,
    skip_price_validation: bool = False,
    skip_count_check: bool = False,
    skip_field_check: bool = False,
) -> DataQualityResult:
    """Run all data quality checks on a DataFrame.

    Args:
        df: DataFrame to validate
        skip_duplicates: Skip duplicate check
        skip_price_validation: Skip price range validation
        skip_count_check: Skip minimum count check
        skip_field_check: Skip required fields check

    Returns:
        Combined results from all checks

    Raises:
        ValueError: If any check fails
    """
    logger = get_task_logger(__name__)
    logger.info(f"Running data quality checks on {len(df):,} rows")

    results: DataQualityResult = {
        "total_rows": len(df),
        "total_columns": len(df.columns),
        "checks": {},
    }

    if not skip_duplicates:
        results["checks"]["duplicates"] = check_duplicates.fn(df)

    if not skip_price_validation:
        results["checks"]["price_ranges"] = validate_price_ranges.fn(df)

    if not skip_count_check:
        results["checks"]["minimum_count"] = check_minimum_listing_count.fn(df)

    if not skip_field_check:
        results["checks"]["required_fields"] = check_required_fields.fn(df)

    logger.info("All data quality checks passed")
    return results
