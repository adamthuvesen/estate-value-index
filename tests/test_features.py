"""Tests for feature engineering functionality."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from src.estate_value_index.ml.features import (
    CATEGORICAL_FEATURE_NAMES,
    NUMERIC_FEATURE_NAMES,
    FeatureEngineeringContext,
    SimplePredictionPipeline,
    _coerce_nullable_bool,
    _safe_divide,
    build_feature_context,
    create_optimized_features,
    get_feature_lists,
    handle_missing_values,
)
from src.estate_value_index.ml.features.heuristics import (
    _estimate_energy_efficiency,
    _estimate_energy_efficiency_series,
)
from src.estate_value_index.ml.training_workflow.data import load_feature_subset
from tests.conftest import assert_valid_dataframe


def test_unknown_feature_subset_fails() -> None:
    with pytest.raises(ValueError, match="Unknown feature set"):
        load_feature_subset("missing_feature_set")


def test_missing_feature_subset_config_fails(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(FileNotFoundError, match="Feature subset config not found"):
        load_feature_subset("no_list_price_v1")


def test_full_feature_set_is_explicit_and_config_free(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)

    assert load_feature_subset("full") == (None, None)


def test_all_registered_feature_sets_match_the_feature_registry() -> None:
    config = yaml.safe_load(Path("config/feature_subsets.yaml").read_text(encoding="utf-8"))

    for feature_set in config:
        if feature_set != "default":
            load_feature_subset(feature_set)


class TestFeatureEngineering:
    @pytest.mark.unit
    def test_create_optimized_features_basic(self, sample_swedish_properties):
        result = create_optimized_features(sample_swedish_properties)

        assert_valid_dataframe(result)
        assert len(result) == len(sample_swedish_properties)

        expected_features = [
            "price_per_sqm",
            "monthly_fee_per_sqm",
            "property_age",
            "living_area_squared",
            "age_bucket",
            "rooms_per_sqm",
            "area_age_interaction",
            "luxury_score",
            "h3_res10",
            "micro_area_ppsqm_median",
            "h3_neighbor_ppsqm",
            "same_size_ppsqm_median",
            "street_name",
            "street_area_ppsqm_median",
            "address_ppsqm_median",
            "market_interest_rate",
            "market_ppsqm_index",
            "micro_luxury_score",
            "luxury_location_tier",
            "distance_to_nearest_metro",
            "description_word_count",
            "condition_score",
        ]
        for feature in expected_features:
            assert feature in result.columns, f"Missing feature: {feature}"

    @pytest.mark.unit
    def test_create_optimized_features_with_context(
        self, sample_swedish_properties, mock_feature_context
    ):
        result = create_optimized_features(sample_swedish_properties, context=mock_feature_context)

        assert_valid_dataframe(result)
        assert "area_avg_price" in result.columns
        assert "area_target_encoded" in result.columns
        assert result["area_avg_price"].notna().any()

    @pytest.mark.unit
    def test_create_optimized_features_tolerates_reengineering_existing_features(
        self, sample_swedish_properties
    ):
        valid_data = sample_swedish_properties.dropna(subset=["sold_price"])
        engineered = create_optimized_features(valid_data)
        context = build_feature_context(engineered)

        result = create_optimized_features(engineered, context=context)

        assert "micro_luxury_score" in result.columns
        assert result["micro_luxury_score"].notna().all()

    @pytest.mark.unit
    def test_create_optimized_features_temporal(self, sample_swedish_properties):
        result = create_optimized_features(sample_swedish_properties)

        # Listing-based temporal features (sold_date features avoided to prevent leakage)
        temporal_features = [
            "days_since_scraped",
            "days_since_listed",
            "listed_month",
            "listed_quarter",
            "listed_weekday",
            "is_weekend_listing",
            "listed_month_sin",
            "listed_month_cos",
        ]
        for feature in temporal_features:
            assert feature in result.columns, f"Missing temporal feature: {feature}"

        assert result["listed_month"].min() >= 1
        assert result["listed_month"].max() <= 12
        assert result["listed_quarter"].min() >= 1
        assert result["listed_quarter"].max() <= 4

    @pytest.mark.unit
    def test_create_optimized_features_description_and_poi(self, sample_swedish_properties):
        df = sample_swedish_properties.head(2).copy()
        df["lat"] = [59.3326, 59.334]
        df["lon"] = [18.0649, 18.07]
        df["description"] = [
            "Nyrenoverad lagenhet med modernt kok, renoverat badrum, sjoutsikt och lugnt lage.",
            "Originalskick med renoveringsbehov.",
        ]

        result = create_optimized_features(df)

        assert result.loc[0, "is_renovated"] == 1
        assert result.loc[0, "has_modern_kitchen"] == 1
        assert result.loc[0, "has_modern_bathroom"] == 1
        assert result.loc[0, "has_view"] == 1
        assert result.loc[0, "is_quiet_location"] == 1
        assert result.loc[0, "condition_score"] > result.loc[1, "condition_score"]
        assert result.loc[1, "needs_renovation"] == 1
        assert result["distance_to_city_center"].notna().all()
        assert "transit_accessibility_score" in result.columns

    @pytest.mark.unit
    def test_create_optimized_features_edge_cases(self, edge_case_properties):
        result = create_optimized_features(edge_case_properties)

        assert_valid_dataframe(result)
        assert len(result) == len(edge_case_properties)
        assert "price_per_sqm" in result.columns
        assert "property_age" in result.columns

    @pytest.mark.unit
    def test_safe_divide_function(self):
        index = pd.RangeIndex(3)

        result = _safe_divide([10, 20, 30], [2, 4, 5], index)
        expected = pd.Series([5.0, 5.0, 6.0], index=index)
        pd.testing.assert_series_equal(result, expected)

        result = _safe_divide([10, 20], [0, 4], index[:2])
        assert np.isnan(result.iloc[0])
        assert result.iloc[1] == 5.0

        result = _safe_divide(None, [1, 2], index[:2])
        assert result.isna().all()

    @pytest.mark.unit
    def test_coerce_nullable_bool(self):
        test_series = pd.Series(["true", "false", "1", "0", "yes", "no", "invalid", None])
        result = _coerce_nullable_bool(test_series)

        expected = [True, False, True, False, True, False, pd.NA, pd.NA]
        for i, exp in enumerate(expected):
            if pd.isna(exp):
                assert pd.isna(result.iloc[i])
            else:
                assert result.iloc[i] == exp


class TestFeatureConfiguration:
    @pytest.mark.unit
    def test_get_feature_lists(self):
        numeric, categorical, all_features = get_feature_lists()

        assert isinstance(numeric, list)
        assert isinstance(categorical, list)
        assert isinstance(all_features, list)
        assert len(numeric) > 0
        assert len(categorical) > 0
        assert len(all_features) == len(numeric) + len(categorical)

        assert "listing_price" in numeric
        assert "living_area" in numeric
        assert "micro_area_ppsqm_median" in numeric
        assert "micro_area_ppsqm_p90" in numeric
        assert "h3_neighbor_ppsqm" in numeric
        assert "h3_neighbor_ppsqm_p90" in numeric
        assert "same_size_ppsqm_median" in numeric
        assert "same_size_ppsqm_p90" in numeric
        assert "street_area_ppsqm_median" in numeric
        assert "address_ppsqm_median" in numeric
        assert "market_interest_rate" in numeric
        assert "distance_to_nearest_metro" in numeric
        assert "condition_score" in numeric
        assert "area" in categorical
        assert "h3_res10" in categorical
        assert "same_size_scope_used" in categorical
        assert "street_name" in categorical
        # property_type is filtered out from current feature list
        assert "property_type" not in categorical

    @pytest.mark.unit
    def test_feature_constants(self):
        assert len(NUMERIC_FEATURE_NAMES) > 15
        assert len(CATEGORICAL_FEATURE_NAMES) > 0
        assert "price_per_sqm" in NUMERIC_FEATURE_NAMES
        assert "micro_area_ppsqm_premium_vs_area" in NUMERIC_FEATURE_NAMES
        assert "micro_area_upper_tail_ratio" in NUMERIC_FEATURE_NAMES
        assert "h3_neighbor_premium_vs_micro" in NUMERIC_FEATURE_NAMES
        assert "h3_neighbor_upper_tail_ratio" in NUMERIC_FEATURE_NAMES
        assert "same_size_premium_vs_area" in NUMERIC_FEATURE_NAMES
        assert "same_size_upper_tail_ratio" in NUMERIC_FEATURE_NAMES
        assert "street_area_premium_vs_micro" in NUMERIC_FEATURE_NAMES
        assert "street_size_premium_vs_street" in NUMERIC_FEATURE_NAMES
        assert "address_premium_vs_street" in NUMERIC_FEATURE_NAMES
        assert "market_ppsqm_index_change_3m" in NUMERIC_FEATURE_NAMES
        assert "micro_luxury_score" in NUMERIC_FEATURE_NAMES
        assert "h3_market_ppsqm_ratio" in NUMERIC_FEATURE_NAMES
        assert "transit_accessibility_score" in NUMERIC_FEATURE_NAMES
        assert "premium_score" in NUMERIC_FEATURE_NAMES
        assert "area" in CATEGORICAL_FEATURE_NAMES
        assert "micro_area_resolution_used" in CATEGORICAL_FEATURE_NAMES
        assert "same_size_scope_used" in CATEGORICAL_FEATURE_NAMES
        assert "street_name" in CATEGORICAL_FEATURE_NAMES
        assert "address_comp_scope_used" in CATEGORICAL_FEATURE_NAMES
        assert "luxury_location_tier" in CATEGORICAL_FEATURE_NAMES

    @pytest.mark.unit
    def test_production_variants_are_explicit_about_asking_price(self):
        no_list_numeric, no_list_categorical = load_feature_subset("no_list_price_v1")
        listing_numeric, listing_categorical = load_feature_subset("with_list_price_v1")

        blocked_no_list = {
            "listing_price",
            "relative_area_price",
            "price_per_sqm",
            "total_cost_per_sqm",
            "cost_benefit_ratio",
            "efficiency_premium",
        }

        assert blocked_no_list.isdisjoint(no_list_numeric)
        assert "listing_price" in listing_numeric
        assert "relative_area_price" in listing_numeric
        assert "total_cost_per_sqm" in listing_numeric
        assert no_list_categorical == listing_categorical

    @pytest.mark.unit
    def test_comparison_feature_subsets_isolate_h3(self):
        listing_numeric, listing_categorical = load_feature_subset("with_list_price_v1")
        comps_numeric, comps_categorical = load_feature_subset("no_list_price_h3_comps")
        street_numeric, street_categorical = load_feature_subset("no_list_price_h3_market_street")

        assert "listing_price" in listing_numeric
        assert "h3_neighbor_ppsqm" in listing_numeric
        assert "h3_res10" in listing_categorical

        assert "listing_price" not in comps_numeric
        assert "h3_neighbor_ppsqm" in comps_numeric
        assert "same_size_ppsqm_median" in comps_numeric
        assert "market_interest_rate" not in comps_numeric
        assert "same_size_scope_used" in comps_categorical

        market_numeric, market_categorical = load_feature_subset("no_list_price_h3_market")
        assert "listing_price" not in market_numeric
        assert "h3_neighbor_ppsqm" in market_numeric
        assert "same_size_ppsqm_median" in market_numeric
        assert "market_interest_rate" in market_numeric
        assert "same_size_scope_used" in market_categorical
        assert "listing_price" not in street_numeric
        assert "street_area_ppsqm_p90" in street_numeric
        assert "street_size_ppsqm_median" in street_numeric
        assert "address_ppsqm_median" in street_numeric
        assert "street_name" in street_categorical
        assert "address_comp_scope_used" in street_categorical
        assert "micro_area_ppsqm_p90" not in street_numeric

    @pytest.mark.unit
    def test_rfe_compact_feature_subsets_are_registered(self):
        no_list_numeric, no_list_categorical = load_feature_subset("no_list_price_v1")
        listing_numeric, listing_categorical = load_feature_subset(
            "listing_price_h3_market_street_rfe15"
        )

        no_list_blocked = {
            "listing_price",
            "price_per_sqm",
            "relative_area_price",
            "total_cost_per_sqm",
            "fee_price_interaction",
            "cost_benefit_ratio",
            "efficiency_premium",
        }

        assert len(no_list_numeric) + len(no_list_categorical) == 25
        assert no_list_blocked.isdisjoint(no_list_numeric)
        assert {"h3_res10", "h3_res9", "street_name", "area"}.issubset(no_list_categorical)
        assert "same_size_premium_vs_area" in no_list_numeric
        assert "street_size_upper_tail_ratio" in no_list_numeric
        assert set(no_list_numeric).issubset(NUMERIC_FEATURE_NAMES)
        assert set(no_list_categorical).issubset(CATEGORICAL_FEATURE_NAMES)

        assert len(listing_numeric) + len(listing_categorical) == 15
        assert "listing_price" in listing_numeric
        assert "relative_area_price" in listing_numeric
        assert "street_name" in listing_categorical
        assert set(listing_numeric).issubset(NUMERIC_FEATURE_NAMES)
        assert set(listing_categorical).issubset(CATEGORICAL_FEATURE_NAMES)

    @pytest.mark.unit
    def test_aligned_listing_feature_sets_extend_no_list_backbone(self):
        no_list_numeric, no_list_categorical = load_feature_subset("no_list_price_v1")
        aligned26_numeric, aligned26_categorical = load_feature_subset(
            "listing_price_h3_market_street_aligned26"
        )
        aligned30_numeric, aligned30_categorical = load_feature_subset("with_list_price_v1")

        assert set(no_list_numeric).issubset(aligned26_numeric)
        assert set(no_list_numeric).issubset(aligned30_numeric)
        assert aligned26_categorical == no_list_categorical
        assert aligned30_categorical == no_list_categorical

        assert set(aligned26_numeric) - set(no_list_numeric) == {"listing_price"}
        assert set(aligned30_numeric) - set(no_list_numeric) == {
            "listing_price",
            "relative_area_price",
            "total_cost_per_sqm",
            "monthly_fee_per_sqm",
            "efficiency_premium",
        }
        assert len(aligned26_numeric) + len(aligned26_categorical) == 26
        assert len(aligned30_numeric) + len(aligned30_categorical) == 30


class TestMissingValueHandling:
    @pytest.mark.unit
    def test_handle_missing_values_basic(self, sample_swedish_properties):
        df = sample_swedish_properties.copy()
        df.loc[0, "living_area"] = np.nan
        df.loc[1, "area"] = np.nan

        numeric_features = ["living_area", "rooms", "monthly_fee"]
        categorical_features = ["area", "property_type"]

        X_train = df[numeric_features + categorical_features]
        X_test = X_train.copy()

        X_train_filled, _, numeric_fill, categorical_fill = handle_missing_values(
            X_train, X_test, numeric_features, categorical_features
        )

        assert not X_train_filled[numeric_features].isna().any().any()
        assert not X_train_filled[categorical_features].isna().any().any()
        assert "living_area" in numeric_fill
        assert "area" in categorical_fill
        assert isinstance(numeric_fill["living_area"], float)
        assert isinstance(categorical_fill["area"], str)

    @pytest.mark.unit
    def test_handle_missing_values_all_missing(self):
        df = pd.DataFrame(
            {"numeric_col": [np.nan, np.nan, np.nan], "categorical_col": [None, None, None]}
        )

        X_train_filled, _, _, _ = handle_missing_values(
            df, df, ["numeric_col"], ["categorical_col"]
        )

        assert not X_train_filled["numeric_col"].isna().any()
        assert not X_train_filled["categorical_col"].isna().any()
        assert X_train_filled["numeric_col"].iloc[0] == 0
        assert X_train_filled["categorical_col"].iloc[0] == "unknown"

    @pytest.mark.unit
    def test_handle_missing_values_fills_categorical_dtype_with_new_unknown(self):
        X_train = pd.DataFrame(
            {
                "area": pd.Categorical(["Sodermalm", None], categories=["Sodermalm"]),
            }
        )
        X_test = pd.DataFrame(
            {
                "area": pd.Categorical([None, "Vasastan"], categories=["Vasastan"]),
            }
        )

        X_train_filled, X_test_filled, _, categorical_fill = handle_missing_values(
            X_train, X_test, [], ["area"]
        )

        assert categorical_fill["area"] == "Sodermalm"
        assert not X_train_filled["area"].isna().any()
        assert not X_test_filled["area"].isna().any()
        assert str(X_train_filled["area"].dtype) == "category"
        assert str(X_test_filled["area"].dtype) == "category"


class TestFeatureContext:
    @pytest.mark.unit
    def test_build_feature_context(self, sample_swedish_properties):
        df = create_optimized_features(sample_swedish_properties)
        context = build_feature_context(df)

        assert isinstance(context, FeatureEngineeringContext)
        assert isinstance(context.reference_date, pd.Timestamp)
        assert isinstance(context.area_avg_price, dict)
        assert isinstance(context.global_target_mean, float)
        assert "Södermalm" in context.area_avg_price
        assert context.area_avg_price["Södermalm"] > 0

    @pytest.mark.unit
    def test_build_feature_context_empty_data(self):
        df = pd.DataFrame(
            {"listing_price": [1000000], "sold_price": [1100000], "area": ["Stockholm"]}
        )
        context = build_feature_context(df)

        assert isinstance(context, FeatureEngineeringContext)
        assert context.global_target_mean > 0
        assert context.global_listing_price_mean > 0

    @pytest.mark.unit
    def test_build_feature_context_has_micro_area_stats(self, sample_swedish_properties):
        df = create_optimized_features(sample_swedish_properties)
        context = build_feature_context(df)

        assert isinstance(context.micro_area_stats_res10, dict)
        assert isinstance(context.micro_area_stats_res9, dict)
        assert isinstance(context.same_size_stats_h3_res9, dict)
        assert isinstance(context.same_size_stats_area, dict)
        assert isinstance(context.same_size_stats_global, dict)
        assert context.global_ppsqm_median is None or context.global_ppsqm_median >= 0

    @pytest.mark.unit
    def test_market_features_use_previous_month_reference_data(self):
        df = pd.DataFrame(
            {
                "listing_id": ["A"],
                "listing_price": [4_000_000],
                "sold_price": [4_200_000],
                "living_area": [50.0],
                "rooms": [2.0],
                "monthly_fee": [3000.0],
                "days_on_market": [10],
                "construction_year": [1970],
                "property_type": ["Lägenhet"],
                "municipality": ["Stockholm"],
                "area": ["Södermalm"],
                "scraped_at": ["2025-11-15"],
                "sold_date": ["2025-11-20"],
            }
        )

        result = create_optimized_features(df)

        assert result.loc[0, "market_interest_rate"] == pytest.approx(1.75)
        assert result.loc[0, "market_ppsqm_index"] == pytest.approx(112912)

    @pytest.mark.unit
    def test_energy_efficiency_vectorised_matches_scalar(self):
        # Permutation of every (year-bin, area-bin) bucket the function reasons about,
        # plus NaNs on each axis. The vectorised version must match the scalar
        # version row-by-row — this is the safety net for the `df.apply(axis=1)`
        # → `np.select` rewrite.
        years = [2020, 2005, 1995, 1985, 1975, 1960, np.nan, 2020]
        areas = [30.0, 50.0, 70.0, 90.0, 30.0, 70.0, 50.0, np.nan]
        s_year = pd.Series(years)
        s_area = pd.Series(areas)

        scalar = pd.Series(
            [_estimate_energy_efficiency(y, a) for y, a in zip(years, areas, strict=True)]
        )
        vector = _estimate_energy_efficiency_series(s_year, s_area)

        pd.testing.assert_series_equal(scalar, vector, check_names=False, check_dtype=False)

    @pytest.mark.unit
    def test_energy_efficiency_handles_nullable_extension_dtypes(self):
        # BigQuery's to_dataframe() returns integer columns as pandas nullable
        # Int64. Comparisons on nullable dtypes return a `boolean` extension
        # Series which numpy 2.x's np.select rejects with
        # "invalid entry 0 in condlist: should be boolean ndarray". Guard against
        # regressing back to a non-nullable assumption.
        s_year = pd.Series([2020, 2005, pd.NA, 1985, 1960], dtype="Int64")
        s_area = pd.Series([30.0, 50.0, 70.0, pd.NA, 90.0], dtype="Float64")

        result = _estimate_energy_efficiency_series(s_year, s_area)

        expected = pd.Series(
            [
                _estimate_energy_efficiency(2020, 30.0),
                _estimate_energy_efficiency(2005, 50.0),
                5.0,  # NaN year → default
                5.0,  # NaN area → default
                _estimate_energy_efficiency(1960, 90.0),
            ]
        )
        pd.testing.assert_series_equal(result, expected, check_names=False, check_dtype=False)


class TestPredictionPipelines:
    @pytest.mark.unit
    def test_simple_prediction_pipeline_init(self, mock_feature_context):
        mock_model = object()

        pipeline = SimplePredictionPipeline(
            model=mock_model,
            numeric_features=["living_area", "rooms"],
            categorical_features=["area"],
            context=mock_feature_context,
        )

        assert pipeline.model is mock_model
        assert pipeline.context is mock_feature_context
        assert "living_area" in pipeline.numeric_features


class TestFeatureValidation:
    @pytest.mark.unit
    def test_feature_engineering_preserves_index(self, sample_swedish_properties):
        original_ids = sample_swedish_properties["listing_id"].tolist()
        result = create_optimized_features(sample_swedish_properties)

        assert result["listing_id"].tolist() == original_ids

    @pytest.mark.unit
    def test_feature_engineering_numeric_dtypes(self, sample_swedish_properties):
        result = create_optimized_features(sample_swedish_properties)

        for col in ["price_per_sqm", "property_age", "living_area_squared"]:
            if col in result.columns:
                assert pd.api.types.is_numeric_dtype(result[col]), f"{col} should be numeric"

    @pytest.mark.unit
    @pytest.mark.parametrize("missing_col", ["listing_price", "living_area", "construction_year"])
    def test_feature_engineering_missing_key_columns(self, sample_swedish_properties, missing_col):
        df = sample_swedish_properties.copy()
        if missing_col in df.columns:
            df = df.drop(columns=[missing_col])

        with pytest.raises((TypeError, KeyError)):
            create_optimized_features(df)
