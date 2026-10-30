import numpy as np
import pandas as pd
import pytest

from estate_value_index.areas import (
    extract_area_name,
    normalize_area_for_model,
    transliterate_swedish,
)
from estate_value_index.ml.constants import MIN_VALID_PRICE
from estate_value_index.ml.preprocessing import (
    FeatureSpec,
    drop_outliers_quantile,
    filter_valid_listings,
    preprocess_area_field,
)


def make_sample_frame():
    return pd.DataFrame(
        [
            {
                "listing_id": "1",
                "listing_price": MIN_VALID_PRICE,
                "sold_price": MIN_VALID_PRICE + 50_000,
                "municipality": "Stockholm",
                "property_type": "Lägenhet",
                "living_area": 55.0,
                "rooms": 2,
                "monthly_fee": 2500,
                "days_on_market": 10,
                "construction_year": 1930,
                "area": "Lägenhet · Södermalm · Stockholm",
            },
            {
                "listing_id": "2",
                "listing_price": MIN_VALID_PRICE - 1,
                "sold_price": MIN_VALID_PRICE + 20_000,
                "area": "Lägenhet · Östermalm · Stockholm",
            },
            {
                "listing_id": "3",
                "listing_price": MIN_VALID_PRICE + 5,
                "sold_price": None,
                "area": "Villa · Vasastan · Stockholm",
            },
        ]
    )


def test_filter_valid_listings_drops_invalid_rows():
    frame = make_sample_frame()

    filtered = filter_valid_listings(frame)

    assert len(filtered) == 1
    assert filtered.iloc[0]["listing_id"] == "1"


class TestSwedishCharacterHandling:
    @pytest.mark.unit
    def test_transliterate_swedish_basic(self):
        assert transliterate_swedish("Södermalm") == "sodermalm"
        assert transliterate_swedish("Östermalm") == "ostermalm"
        assert transliterate_swedish("Vällingby") == "vallingby"

    @pytest.mark.unit
    def test_transliterate_swedish_mixed_case(self):
        assert transliterate_swedish("SöDERmalm") == "sodermalm"
        assert transliterate_swedish("ÖsterMalm") == "ostermalm"

    @pytest.mark.unit
    def test_transliterate_swedish_special_chars(self):
        assert transliterate_swedish("Söder-malm") == "soder_malm"
        assert transliterate_swedish("Östermalm & City") == "ostermalm_city"
        assert transliterate_swedish("Area/District") == "area_district"

    @pytest.mark.unit
    def test_transliterate_swedish_edge_cases(self):
        assert transliterate_swedish("") == ""
        assert transliterate_swedish("   ") == ""
        assert pd.isna(transliterate_swedish(None))
        assert pd.isna(transliterate_swedish(np.nan))

    @pytest.mark.unit
    def test_extract_area_name_basic(self):
        assert extract_area_name("Lägenhet · Södermalm · Stockholm") == "sodermalm"

    @pytest.mark.unit
    def test_extract_area_name_different_types(self):
        assert extract_area_name("Villa · Östermalm · Stockholm") == "ostermalm"
        assert extract_area_name("Radhus · Vasastan · Stockholm") == "vasastan"
        assert extract_area_name("Bostadsrätt · Gamla Stan · Stockholm") == "gamla_stan"

    @pytest.mark.unit
    def test_extract_area_name_malformed(self):
        # Single-token strings have no separator, so the whole string is slugified.
        assert extract_area_name("Just a simple area name") == "just_a_simple_area_name"
        # Multi-token strings extract the most-specific (last non-generic) token.
        # "Property" is non-generic but the last token wins for 2-part inputs.
        assert extract_area_name("Property · Area") == "area"

    @pytest.mark.unit
    def test_normalize_area_for_model_booli_shape(self):
        assert normalize_area_for_model("Lägenhet · Södermalm · Stockholm") == "sodermalm"
        assert normalize_area_for_model("Östermalm") == "ostermalm"

    @pytest.mark.unit
    def test_normalize_area_for_model_empty(self):
        assert normalize_area_for_model("") == "unknown"
        assert normalize_area_for_model(None) == "unknown"

    @pytest.mark.integration
    def test_preprocess_area_field(self):
        df = pd.DataFrame(
            {
                "area": [
                    "Lägenhet · Södermalm · Stockholm",
                    "Villa · Östermalm · Stockholm",
                    None,
                    "Simple area name",
                ],
                "price": [1000000, 2000000, 3000000, 4000000],
            }
        )

        result = preprocess_area_field(df)

        expected_areas = ["sodermalm", "ostermalm", None, "simple_area_name"]
        for i, expected in enumerate(expected_areas):
            if pd.isna(expected):
                assert pd.isna(result["area"].iloc[i])
            else:
                assert result["area"].iloc[i] == expected

        # Original frame is not mutated
        assert df["area"].iloc[0] == "Lägenhet · Södermalm · Stockholm"


class TestFilterValidListings:
    @pytest.mark.unit
    def test_filter_valid_listings_missing_columns(self):
        df = pd.DataFrame({"listing_price": [1000000]})  # missing sold_price

        with pytest.raises(KeyError, match="Missing required columns"):
            filter_valid_listings(df)

    @pytest.mark.unit
    def test_filter_valid_listings_custom_min_price(self):
        df = pd.DataFrame(
            {"listing_price": [500000, 2000000, 3000000], "sold_price": [550000, 2100000, 3100000]}
        )

        assert len(filter_valid_listings(df)) == 1
        assert len(filter_valid_listings(df, min_price=600000)) == 2

    @pytest.mark.unit
    def test_filter_valid_listings_na_handling(self):
        df = pd.DataFrame(
            {
                "listing_price": [1000000, np.nan, 2000000, 3000000],
                "sold_price": [1100000, 1200000, np.nan, 3100000],
            }
        )

        # Only the last row has both prices >= 3M
        assert len(filter_valid_listings(df)) == 1

    @pytest.mark.unit
    def test_filter_valid_listings_can_skip_listing_price_requirement(self):
        df = pd.DataFrame(
            {
                "listing_price": [np.nan, 2_000_000],
                "sold_price": [3_500_000, 3_600_000],
            }
        )

        assert len(filter_valid_listings(df)) == 0
        result = filter_valid_listings(df, require_listing_price=False)

        assert len(result) == 2
        assert "listing_price" in result.columns

    @pytest.mark.integration
    def test_filter_valid_listings_with_area_processing(self):
        df = pd.DataFrame(
            {
                "listing_price": [2000000, 3000000],
                "sold_price": [2100000, 3100000],
                "area": ["Lägenhet · Södermalm · Stockholm", "Villa · Östermalm · Stockholm"],
            }
        )

        result = filter_valid_listings(df)
        assert len(result) == 1
        assert result["area"].iloc[0] == "ostermalm"

    @pytest.mark.integration
    def test_filter_valid_listings_drop_na_features(self):
        df = pd.DataFrame(
            {
                "listing_price": [2000000, 3000000, 4000000],
                "sold_price": [2100000, 3100000, 4100000],
                "living_area": [65.0, np.nan, 85.0],
                "rooms": [2, 3, np.nan],
            }
        )

        assert len(filter_valid_listings(df, drop_na_features=False)) == 2
        assert len(filter_valid_listings(df, drop_na_features=True)) == 0


class TestOutlierRemoval:
    @pytest.mark.unit
    def test_drop_outliers_quantile_basic(self):
        df = pd.DataFrame(
            {"price": [1000000, 2000000, 3000000, 100000000], "area": [50, 65, 80, 85]}
        )

        # 10th-90th percentile across 4 values trims both extremes
        result = drop_outliers_quantile(df, columns=["price"], lower=0.1, upper=0.9)
        assert len(result) == 2
        assert result["price"].max() == 3000000

    @pytest.mark.unit
    def test_drop_outliers_quantile_invalid_bounds(self):
        df = pd.DataFrame({"price": [1, 2, 3, 4, 5]})

        with pytest.raises(ValueError, match="Quantile bounds must satisfy"):
            drop_outliers_quantile(df, lower=0.5, upper=0.3)
        with pytest.raises(ValueError, match="Quantile bounds must satisfy"):
            drop_outliers_quantile(df, lower=-0.1, upper=0.9)

    @pytest.mark.unit
    def test_drop_outliers_quantile_no_columns(self):
        df = pd.DataFrame({"text_col": ["a", "b", "c"], "other_col": [1, 2, 3]})

        result = drop_outliers_quantile(df, columns=[])
        assert len(result) == len(df)

    @pytest.mark.unit
    def test_drop_outliers_quantile_missing_columns(self):
        df = pd.DataFrame({"price": [1, 2, 3, 4, 5]})

        result = drop_outliers_quantile(df, columns=["price", "nonexistent"])
        assert len(result) <= len(df)

    @pytest.mark.unit
    def test_drop_outliers_quantile_na_values(self):
        df = pd.DataFrame(
            {"price": [1000000, 2000000, np.nan, 100000000, 3000000], "id": [1, 2, 3, 4, 5]}
        )

        result = drop_outliers_quantile(df, columns=["price"], lower=0.1, upper=0.9)

        assert result["price"].isna().sum() == 1
        assert result["price"].max() == 3000000

    @pytest.mark.integration
    def test_drop_outliers_quantile_realistic_data(self):
        normal_prices = np.random.normal(4000000, 1000000, 100)
        outlier_prices = [50000000, 100000000]
        all_prices = np.concatenate([normal_prices, outlier_prices])

        df = pd.DataFrame(
            {
                "sold_price": all_prices,
                "listing_price": all_prices * 0.95,
                "id": range(len(all_prices)),
            }
        )

        result = drop_outliers_quantile(df, columns=["sold_price", "listing_price"])

        assert len(result) < len(df)
        assert result["sold_price"].max() < 50000000
        assert result["listing_price"].max() < 50000000


class TestFeatureSpec:
    @pytest.mark.unit
    def test_feature_spec_immutable(self):
        spec = FeatureSpec(numeric=["price", "area"], categorical=["location"], target="sold_price")

        with pytest.raises(AttributeError):
            spec.numeric = ["different_price"]  # pyright: ignore[reportAttributeAccessIssue]  # asserts that FeatureSpec is frozen
        with pytest.raises(AttributeError):
            spec.target = "different_target"  # pyright: ignore[reportAttributeAccessIssue]  # asserts that FeatureSpec is frozen

    @pytest.mark.unit
    def test_feature_spec_equality(self):
        spec1 = FeatureSpec(
            numeric=["price", "area"], categorical=["location"], target="sold_price"
        )
        spec2 = FeatureSpec(
            numeric=["price", "area"], categorical=["location"], target="sold_price"
        )
        spec3 = FeatureSpec(numeric=["price"], categorical=["location"], target="sold_price")

        assert spec1 == spec2
        assert spec1 != spec3

    @pytest.mark.unit
    def test_feature_spec_str_representation(self):
        spec = FeatureSpec(numeric=["price", "area"], categorical=["location"], target="sold_price")

        str_repr = str(spec)
        assert "price" in str_repr
        assert "area" in str_repr
        assert "location" in str_repr
        assert "sold_price" in str_repr


class TestIntegrationPreprocessing:
    @pytest.mark.integration
    def test_full_preprocessing_pipeline(self):
        df = pd.DataFrame(
            {
                "listing_id": ["SWE-001", "SWE-002", "SWE-003", "SWE-004", "SWE-005"],
                "listing_price": [4000000, 500000, 6000000, 100000000, 3500000],
                "sold_price": [4200000, 520000, 6100000, 95000000, 3600000],
                "living_area": [65.0, 35.0, 85.0, 200.0, 55.0],
                "rooms": [2, 1, 3, 6, 2],
                "monthly_fee": [3200, 2000, 4500, 8000, 3000],
                "area": [
                    "Lägenhet · Södermalm · Stockholm",
                    "Lägenhet · Rinkeby · Stockholm",
                    "Lägenhet · Östermalm · Stockholm",
                    "Villa · Danderyd · Stockholm",
                    "Lägenhet · Vasastan · Stockholm",
                ],
                "property_type": "Lägenhet",
                "municipality": "Stockholm",
            }
        )

        filtered = filter_valid_listings(df)
        assert len(filtered) == 4
        assert filtered["area"].iloc[0] == "sodermalm"

        no_outliers = drop_outliers_quantile(
            filtered, columns=["listing_price", "sold_price"], lower=0.1, upper=0.9
        )
        assert len(no_outliers) < len(filtered)
