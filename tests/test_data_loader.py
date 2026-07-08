"""Tests for data loading functionality."""

import json

import pandas as pd
import pytest

from src.estate_value_index.ml.data_loader import (
    _coerce_numeric,
    _coerce_records,
    _iter_json_objects,
    load_default_dataset,
    load_listings,
    load_raw_records,
)
from tests.conftest import assert_valid_dataframe


class TestJsonParsing:
    @pytest.mark.unit
    def test_iter_json_objects_single(self):
        json_text = '{"id": 1, "name": "test"}'
        objects = list(_iter_json_objects(json_text))

        assert len(objects) == 1
        assert objects[0] == {"id": 1, "name": "test"}

    @pytest.mark.unit
    def test_iter_json_objects_multiple(self):
        json_text = '{"id": 1}   {"id": 2}\n{"id": 3}'
        objects = list(_iter_json_objects(json_text))

        assert len(objects) == 3
        assert [obj["id"] for obj in objects] == [1, 2, 3]

    @pytest.mark.unit
    def test_iter_json_objects_empty(self):
        assert list(_iter_json_objects("")) == []

    @pytest.mark.unit
    def test_iter_json_objects_whitespace_only(self):
        assert list(_iter_json_objects("   \n  \t  ")) == []

    @pytest.mark.unit
    def test_coerce_records_list(self):
        assert _coerce_records([{"id": 1}, {"id": 2}]) == [{"id": 1}, {"id": 2}]

    @pytest.mark.unit
    def test_coerce_records_single_dict(self):
        assert _coerce_records({"id": 1, "name": "test"}) == [{"id": 1, "name": "test"}]

    @pytest.mark.unit
    def test_coerce_records_invalid_type(self):
        with pytest.raises(ValueError, match="Unsupported JSON payload type"):
            _coerce_records("invalid string")

    @pytest.mark.unit
    def test_coerce_records_list_with_non_dicts(self):
        data = [{"id": 1}, "invalid", {"id": 2}, 123]
        assert _coerce_records(data) == [{"id": 1}, {"id": 2}]


class TestRawRecordLoading:
    @pytest.mark.unit
    def test_load_raw_records_single_file(self, temp_data_dir):
        json_file = temp_data_dir / "test.json"
        data = [{"id": 1, "price": 1000000}, {"id": 2, "price": 2000000}]
        json_file.write_text(json.dumps(data))

        records = load_raw_records([json_file])
        assert len(records) == 2
        assert records[0]["id"] == 1
        assert records[1]["price"] == 2000000

    @pytest.mark.unit
    def test_load_raw_records_multiple_files(self, temp_data_dir):
        file1 = temp_data_dir / "file1.json"
        file2 = temp_data_dir / "file2.json"
        file1.write_text(json.dumps([{"id": 1}]))
        file2.write_text(json.dumps([{"id": 2}]))

        records = load_raw_records([file1, file2])
        assert len(records) == 2
        assert {r["id"] for r in records} == {1, 2}

    @pytest.mark.unit
    def test_load_raw_records_concatenated_json(self, temp_data_dir):
        json_file = temp_data_dir / "concat.json"
        json_file.write_text('{"id": 1} {"id": 2}')

        assert len(load_raw_records([json_file])) == 2

    @pytest.mark.unit
    def test_load_raw_records_empty_file(self, temp_data_dir):
        json_file = temp_data_dir / "empty.json"
        json_file.write_text("")

        assert load_raw_records([json_file]) == []


class TestNumericCoercion:
    @pytest.mark.unit
    def test_coerce_numeric_basic(self):
        df = pd.DataFrame(
            {
                "price": ["1000000", "2000000", "3000000"],
                "area": [50.5, 75.2, 90.0],
                "text": ["a", "b", "c"],
            }
        )

        _coerce_numeric(df, ["price", "area"])

        assert pd.api.types.is_numeric_dtype(df["price"])
        assert pd.api.types.is_numeric_dtype(df["area"])
        assert df["price"].iloc[0] == 1000000
        assert not pd.api.types.is_numeric_dtype(df["text"])

    @pytest.mark.unit
    def test_coerce_numeric_invalid_values(self):
        df = pd.DataFrame({"price": ["1000000", "invalid", "3000000"], "area": [50.5, None, 90.0]})

        _coerce_numeric(df, ["price", "area"])

        assert pd.api.types.is_numeric_dtype(df["price"])
        assert pd.api.types.is_numeric_dtype(df["area"])
        assert pd.isna(df["price"].iloc[1])
        assert pd.isna(df["area"].iloc[1])

    @pytest.mark.unit
    def test_coerce_numeric_missing_columns(self):
        df = pd.DataFrame({"existing": [1, 2, 3]})

        _coerce_numeric(df, ["existing", "missing"])

        assert pd.api.types.is_numeric_dtype(df["existing"])


class TestListingLoading:
    @pytest.mark.integration
    def test_load_listings_basic(self, temp_data_dir):
        data = [
            {
                "listing_id": "TEST-001",
                "listing_price": "4500000",
                "living_area": 65.5,
                "rooms": 2,
                "scraped_at": "2023-01-01T10:00:00Z",
            },
            {"listing_id": "TEST-002", "listing_price": "5200000", "living_area": 78.0, "rooms": 3},
        ]

        (temp_data_dir / "listings.json").write_text(json.dumps(data))

        df = load_listings(temp_data_dir)

        assert_valid_dataframe(df, min_rows=2)
        assert "listing_id" in df.columns
        assert "listing_price" in df.columns
        assert pd.api.types.is_numeric_dtype(df["listing_price"])
        assert df["listing_price"].iloc[0] == 4500000

    @pytest.mark.integration
    def test_load_listings_datetime_coercion(self, temp_data_dir):
        data = [
            {
                "listing_id": "TEST-001",
                "scraped_at": "2023-01-01T10:00:00Z",
                "sold_date": "2023-02-15",
            }
        ]

        (temp_data_dir / "listings.json").write_text(json.dumps(data))

        df = load_listings(temp_data_dir)

        assert pd.api.types.is_datetime64_any_dtype(df["scraped_at"])
        assert pd.api.types.is_datetime64_any_dtype(df["sold_date"])

    @pytest.mark.integration
    def test_load_listings_normalizes_coordinate_aliases(self, temp_data_dir):
        data = [
            {
                "listing_id": "TEST-001",
                "latitude": "59.315",
                "longitude": "18.070",
            }
        ]

        (temp_data_dir / "listings.json").write_text(json.dumps(data))

        df = load_listings(temp_data_dir)

        assert df["lat"].iloc[0] == pytest.approx(59.315)
        assert df["lon"].iloc[0] == pytest.approx(18.070)

    @pytest.mark.integration
    def test_load_listings_duplicate_handling(self, temp_data_dir):
        data = [
            {
                "listing_id": "DUPLICATE",
                "listing_price": 1000000,
                "scraped_at": "2023-01-01T10:00:00Z",
            },
            {
                "listing_id": "DUPLICATE",
                "listing_price": 1100000,
                "scraped_at": "2023-01-02T10:00:00Z",
            },
        ]

        (temp_data_dir / "listings.json").write_text(json.dumps(data))

        df = load_listings(temp_data_dir, drop_duplicate_listing_ids=True)

        assert len(df) == 1
        # Later scraped_at wins
        assert df["listing_price"].iloc[0] == 1100000

    @pytest.mark.integration
    def test_load_listings_no_duplicate_removal(self, temp_data_dir):
        data = [
            {"listing_id": "DUPLICATE", "listing_price": 1000000},
            {"listing_id": "DUPLICATE", "listing_price": 1100000},
        ]

        (temp_data_dir / "listings.json").write_text(json.dumps(data))

        df = load_listings(temp_data_dir, drop_duplicate_listing_ids=False)

        assert len(df) == 2

    @pytest.mark.integration
    def test_load_listings_multiple_files(self, temp_data_dir):
        (temp_data_dir / "file1.json").write_text(
            json.dumps([{"listing_id": "FILE1-001", "listing_price": 1000000}])
        )
        (temp_data_dir / "file2.json").write_text(
            json.dumps([{"listing_id": "FILE2-001", "listing_price": 2000000}])
        )

        df = load_listings(temp_data_dir)

        assert len(df) == 2
        assert set(df["listing_id"]) == {"FILE1-001", "FILE2-001"}

    @pytest.mark.integration
    def test_load_listings_custom_glob(self, temp_data_dir):
        (temp_data_dir / "data.json").write_text(json.dumps([{"id": 1}]))
        (temp_data_dir / "data.jsonl").write_text('{"id": 2}\n')
        (temp_data_dir / "data.txt").write_text(json.dumps([{"id": 3}]))

        df = load_listings(temp_data_dir, glob="*.jsonl")
        assert len(df) == 1
        assert df["id"].iloc[0] == 2

    @pytest.mark.integration
    def test_load_listings_subdirectories(self, temp_data_dir):
        subdir = temp_data_dir / "subdir"
        subdir.mkdir()
        (subdir / "data.json").write_text(json.dumps([{"id": 1}]))

        df = load_listings(temp_data_dir)
        assert len(df) == 1
        assert df["id"].iloc[0] == 1

    @pytest.mark.integration
    def test_load_listings_nonexistent_directory(self):
        with pytest.raises(FileNotFoundError):
            load_listings("/nonexistent/path")

    @pytest.mark.integration
    def test_load_listings_empty_directory(self, temp_data_dir):
        df = load_listings(temp_data_dir)
        assert len(df) == 0
        assert isinstance(df, pd.DataFrame)

    @pytest.mark.integration
    def test_load_listings_empty_files(self, temp_data_dir):
        (temp_data_dir / "empty.json").write_text("")

        df = load_listings(temp_data_dir)
        assert len(df) == 0


class TestDefaultDatasetLoading:
    @pytest.mark.unit
    def test_load_default_dataset_path_resolution(self):
        try:
            df = load_default_dataset()
            assert isinstance(df, pd.DataFrame)
        except FileNotFoundError:
            # No data directory in test env — expected
            pass

    @pytest.mark.unit
    def test_load_default_dataset_duplicate_parameter(self):
        try:
            df1 = load_default_dataset(drop_duplicate_listing_ids=True)
            df2 = load_default_dataset(drop_duplicate_listing_ids=False)
            assert isinstance(df1, pd.DataFrame)
            assert isinstance(df2, pd.DataFrame)
        except FileNotFoundError:
            pass


class TestErrorHandling:
    @pytest.mark.unit
    def test_malformed_json(self, temp_data_dir):
        bad_file = temp_data_dir / "malformed.json"
        bad_file.write_text('{"invalid": json content')

        with pytest.raises(json.JSONDecodeError):
            load_raw_records([bad_file])

    @pytest.mark.integration
    def test_mixed_valid_invalid_files(self, temp_data_dir):
        (temp_data_dir / "good.json").write_text(json.dumps([{"id": 1}]))
        (temp_data_dir / "bad.json").write_text('{"invalid": json')

        with pytest.raises(json.JSONDecodeError):
            load_listings(temp_data_dir)

    @pytest.mark.integration
    def test_permission_denied_handling(self, temp_data_dir):
        import os
        import stat

        if os.name != "posix":
            return

        protected_file = temp_data_dir / "protected.json"
        protected_file.write_text(json.dumps([{"id": 1}]))
        protected_file.chmod(stat.S_IWRITE)

        try:
            with pytest.raises(PermissionError):
                load_listings(temp_data_dir)
        finally:
            protected_file.chmod(stat.S_IREAD | stat.S_IWRITE)


class TestDataQuality:
    @pytest.mark.integration
    def test_realistic_swedish_property_data(self, temp_data_dir):
        realistic_data = [
            {
                "listing_id": "BOOLI-12345",
                "listing_price": "4500000",
                "sold_price": "4650000",
                "living_area": "65.5",
                "rooms": "2",
                "monthly_fee": "3200",
                "construction_year": "1958",
                "property_type": "Lägenhet",
                "municipality": "Stockholm",
                "area": "Södermalm",
                "scraped_at": "2023-12-01T10:30:00Z",
                "sold_date": "2023-12-15T00:00:00Z",
                "floor": "3",
            },
            {
                "listing_id": "BOOLI-67890",
                "listing_price": "6200000",
                "sold_price": None,  # Active listing
                "living_area": "78.0",
                "rooms": "3",
                "monthly_fee": "4100",
                "construction_year": "1975",
                "property_type": "Lägenhet",
                "municipality": "Stockholm",
                "area": "Östermalm",
                "scraped_at": "2023-12-01T15:45:00Z",
                "sold_date": None,
                "floor": "5",
            },
        ]

        (temp_data_dir / "realistic.json").write_text(json.dumps(realistic_data))

        df = load_listings(temp_data_dir)

        assert_valid_dataframe(df, min_rows=2)
        assert pd.api.types.is_numeric_dtype(df["listing_price"])
        assert pd.api.types.is_numeric_dtype(df["living_area"])
        assert pd.api.types.is_numeric_dtype(df["rooms"])
        assert pd.api.types.is_datetime64_any_dtype(df["scraped_at"])
        assert df["property_type"].iloc[0] == "Lägenhet"
        assert df["municipality"].iloc[0] == "Stockholm"
        assert df["listing_price"].min() > 1000000

    @pytest.mark.integration
    def test_data_consistency_after_loading(self, temp_data_dir):
        original_data = [
            {
                "listing_id": "CONSISTENCY-TEST",
                "listing_price": 4500000,
                "living_area": 65.5,
                "price_per_sqm": 4500000 / 65.5,
            }
        ]

        (temp_data_dir / "consistency.json").write_text(json.dumps(original_data))

        df = load_listings(temp_data_dir)

        expected_ratio = 4500000 / 65.5
        assert abs(df["price_per_sqm"].iloc[0] - expected_ratio) < 0.01
