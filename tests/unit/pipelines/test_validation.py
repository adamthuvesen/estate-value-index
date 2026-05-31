"""Unit tests for pipelines/tasks/validation.py."""

from __future__ import annotations

import pandas as pd
import pytest

from estate_value_index.pipelines.tasks.validation import (
    check_duplicates,
    check_minimum_listing_count,
    check_required_fields,
    run_all_data_quality_checks,
    validate_price_ranges,
)


class TestCheckDuplicates:
    @pytest.mark.unit
    def test_no_duplicates_passes(self, sample_valid_df: pd.DataFrame) -> None:
        result = check_duplicates.fn(sample_valid_df)

        assert result["passed"] is True
        assert result["duplicates"] == 0
        assert result["total_rows"] == len(sample_valid_df)

    @pytest.mark.unit
    def test_duplicates_raises_value_error(self, sample_df_with_duplicates: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="duplicate listings found"):
            check_duplicates.fn(sample_df_with_duplicates)

    @pytest.mark.unit
    def test_missing_id_column_passes(self, sample_valid_df: pd.DataFrame) -> None:
        df_no_id = sample_valid_df.drop(columns=["listing_id"])
        result = check_duplicates.fn(df_no_id)

        assert result["passed"] is True
        assert result["duplicates"] == 0

    @pytest.mark.unit
    def test_custom_id_column(self, sample_valid_df: pd.DataFrame) -> None:
        df = sample_valid_df.rename(columns={"listing_id": "custom_id"})
        result = check_duplicates.fn(df, id_column="custom_id")

        assert result["passed"] is True
        assert result["duplicates"] == 0

    @pytest.mark.unit
    def test_returns_correct_type(self, sample_valid_df: pd.DataFrame) -> None:
        result = check_duplicates.fn(sample_valid_df)

        assert "total_rows" in result
        assert "duplicates" in result
        assert "passed" in result
        assert isinstance(result["total_rows"], int)
        assert isinstance(result["duplicates"], int)
        assert isinstance(result["passed"], bool)

    @pytest.mark.unit
    def test_empty_dataframe(self) -> None:
        result = check_duplicates.fn(pd.DataFrame({"listing_id": []}))

        assert result["passed"] is True
        assert result["total_rows"] == 0


class TestValidatePriceRanges:
    @pytest.mark.unit
    def test_all_prices_in_range(self, sample_valid_df: pd.DataFrame) -> None:
        result = validate_price_ranges.fn(sample_valid_df)

        assert result["passed"] is True
        assert result["outliers"] == 0
        assert result["outlier_pct"] == 0.0

    @pytest.mark.unit
    def test_outliers_below_threshold(self, sample_df_with_outliers: pd.DataFrame) -> None:
        # 2/5 = 40% outliers > 5% default threshold
        with pytest.raises(ValueError, match="exceeds threshold"):
            validate_price_ranges.fn(sample_df_with_outliers)

    @pytest.mark.unit
    def test_outliers_exceed_threshold_raises(self, sample_df_with_outliers: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="outliers"):
            validate_price_ranges.fn(sample_df_with_outliers, outlier_threshold_pct=5.0)

    @pytest.mark.unit
    def test_high_outlier_threshold_passes(self, sample_df_with_outliers: pd.DataFrame) -> None:
        result = validate_price_ranges.fn(sample_df_with_outliers, outlier_threshold_pct=50.0)

        assert result["passed"] is True
        assert result["outliers"] == 2  # 500K and 50M

    @pytest.mark.unit
    def test_missing_price_column(self, sample_valid_df: pd.DataFrame) -> None:
        df_no_price = sample_valid_df.drop(columns=["sold_price"])
        result = validate_price_ranges.fn(df_no_price)

        assert result["passed"] is True
        assert result["outliers"] == 0

    @pytest.mark.unit
    def test_custom_price_bounds(self, sample_valid_df: pd.DataFrame) -> None:
        # Sample prices 3M-5M; bounds 4M-6M flag 2 outliers (3M and 3.5M)
        result = validate_price_ranges.fn(
            sample_valid_df,
            min_price=4_000_000,
            max_price=6_000_000,
            outlier_threshold_pct=70.0,
        )

        assert result["passed"] is True
        assert result["outliers"] == 2

    @pytest.mark.unit
    def test_returns_statistics(self, sample_valid_df: pd.DataFrame) -> None:
        result = validate_price_ranges.fn(sample_valid_df)

        assert "min_price" in result
        assert "max_price" in result
        assert "median_price" in result
        assert result["min_price"] == 3_000_000
        assert result["max_price"] == 5_000_000

    @pytest.mark.unit
    def test_custom_price_column(self) -> None:
        df = pd.DataFrame(
            {
                "listing_id": ["1", "2"],
                "final_price": [3_000_000, 4_000_000],
            }
        )
        result = validate_price_ranges.fn(df, price_column="final_price")

        assert result["passed"] is True


class TestCheckMinimumListingCount:
    @pytest.mark.unit
    def test_sufficient_listings(self, sample_valid_df: pd.DataFrame) -> None:
        result = check_minimum_listing_count.fn(sample_valid_df, min_count=3)

        assert result["passed"] is True
        assert result["total_rows"] == 5
        assert result["min_required"] == 3

    @pytest.mark.unit
    def test_insufficient_listings_raises(self, sample_small_df: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="listings.*minimum"):
            check_minimum_listing_count.fn(sample_small_df, min_count=100)

    @pytest.mark.unit
    def test_exact_minimum(self, sample_valid_df: pd.DataFrame) -> None:
        result = check_minimum_listing_count.fn(sample_valid_df, min_count=5)

        assert result["passed"] is True
        assert result["total_rows"] == 5

    @pytest.mark.unit
    def test_default_minimum(self, sample_valid_df: pd.DataFrame) -> None:
        # 5 rows < default 100 minimum
        with pytest.raises(ValueError):
            check_minimum_listing_count.fn(sample_valid_df)

    @pytest.mark.unit
    def test_zero_minimum(self) -> None:
        result = check_minimum_listing_count.fn(pd.DataFrame({"listing_id": []}), min_count=0)

        assert result["passed"] is True


class TestCheckRequiredFields:
    @pytest.mark.unit
    def test_all_fields_present(self, sample_valid_df: pd.DataFrame) -> None:
        result = check_required_fields.fn(sample_valid_df)

        assert result["passed"] is True
        assert result["missing_fields"] == []

    @pytest.mark.unit
    def test_missing_field_raises(self, sample_df_missing_fields: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="Required fields missing"):
            check_required_fields.fn(sample_df_missing_fields)

    @pytest.mark.unit
    def test_null_field_warns(self, sample_df_null_fields: pd.DataFrame) -> None:
        # Entirely-null columns are recorded but don't fail
        result = check_required_fields.fn(sample_df_null_fields)

        assert result["passed"] is True
        assert "rooms" in result["null_fields"]

    @pytest.mark.unit
    def test_custom_required_fields(self, sample_valid_df: pd.DataFrame) -> None:
        result = check_required_fields.fn(
            sample_valid_df, required_fields=["listing_id", "sold_price"]
        )

        assert result["passed"] is True
        assert result["total_fields"] == 2

    @pytest.mark.unit
    def test_default_required_fields(self, sample_valid_df: pd.DataFrame) -> None:
        # Default: sold_price, living_area, rooms, area, sold_date
        result = check_required_fields.fn(sample_valid_df)
        assert result["total_fields"] == 5

    @pytest.mark.unit
    def test_empty_required_fields(self, sample_valid_df: pd.DataFrame) -> None:
        result = check_required_fields.fn(sample_valid_df, required_fields=[])

        assert result["passed"] is True
        assert result["total_fields"] == 0


class TestRunAllDataQualityChecks:
    @pytest.mark.unit
    def test_all_checks_pass(self) -> None:
        df = pd.DataFrame(
            {
                "listing_id": [str(i) for i in range(150)],
                "sold_price": [3_000_000 + i * 10_000 for i in range(150)],
                "living_area": [50 + (i % 50) for i in range(150)],
                "rooms": [(i % 4) + 1 for i in range(150)],
                "area": ["Södermalm"] * 150,
                "sold_date": ["2024-01-01"] * 150,
            }
        )

        result = run_all_data_quality_checks.fn(df)

        assert result["total_rows"] == 150
        assert result["total_columns"] == 6
        assert "duplicates" in result["checks"]
        assert "price_ranges" in result["checks"]
        assert "minimum_count" in result["checks"]
        assert "required_fields" in result["checks"]

    @pytest.mark.unit
    def test_skip_duplicates_check(self, sample_df_with_duplicates: pd.DataFrame) -> None:
        result = run_all_data_quality_checks.fn(
            sample_df_with_duplicates,
            skip_duplicates=True,
            skip_count_check=True,
        )

        assert "duplicates" not in result["checks"]

    @pytest.mark.unit
    def test_skip_price_validation(self, sample_df_with_outliers: pd.DataFrame) -> None:
        result = run_all_data_quality_checks.fn(
            sample_df_with_outliers,
            skip_price_validation=True,
            skip_count_check=True,
        )

        assert "price_ranges" not in result["checks"]

    @pytest.mark.unit
    def test_skip_count_check(self, sample_small_df: pd.DataFrame) -> None:
        result = run_all_data_quality_checks.fn(sample_small_df, skip_count_check=True)
        assert "minimum_count" not in result["checks"]

    @pytest.mark.unit
    def test_skip_field_check(self, sample_df_missing_fields: pd.DataFrame) -> None:
        result = run_all_data_quality_checks.fn(
            sample_df_missing_fields,
            skip_field_check=True,
            skip_count_check=True,
        )

        assert "required_fields" not in result["checks"]

    @pytest.mark.unit
    def test_returns_combined_results(self) -> None:
        df = pd.DataFrame(
            {
                "listing_id": [str(i) for i in range(150)],
                "sold_price": [3_000_000] * 150,
                "living_area": [50] * 150,
                "rooms": [2] * 150,
                "area": ["Södermalm"] * 150,
                "sold_date": ["2024-01-01"] * 150,
            }
        )

        result = run_all_data_quality_checks.fn(df)

        assert "total_rows" in result
        assert "total_columns" in result
        assert "checks" in result
        assert isinstance(result["checks"], dict)

    @pytest.mark.unit
    def test_duplicate_check_failure_raises(self, sample_df_with_duplicates: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            run_all_data_quality_checks.fn(sample_df_with_duplicates, skip_count_check=True)

    @pytest.mark.unit
    def test_price_check_failure_raises(self, sample_df_with_outliers: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="outliers"):
            run_all_data_quality_checks.fn(sample_df_with_outliers, skip_count_check=True)
