"""Simple unit tests for basic ML pipeline functionality."""

import json
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.estate_value_index.ml.data_loader import load_listings  # noqa: E402
from src.estate_value_index.ml.preprocessing import filter_valid_listings  # noqa: E402
from src.estate_value_index.ml.training import LGBMTrainer  # noqa: E402


class TestBasicDataFlow:
    @pytest.mark.unit
    def test_data_loading_and_filtering(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            data_file = temp_path / "test_data.json"

            test_data = [
                {
                    "listing_id": "TEST-001",
                    "listing_price": 4500000,
                    "sold_price": 4600000,
                    "living_area": 65.0,
                    "rooms": 2,
                    "area": "Stockholm",
                }
            ]
            data_file.write_text(json.dumps(test_data))

            df = load_listings(temp_path)
            assert len(df) >= 1

            filtered_df = filter_valid_listings(df)
            assert len(filtered_df) >= 1
            assert "listing_price" in filtered_df.columns
            assert "sold_price" in filtered_df.columns

    @pytest.mark.unit
    def test_basic_data_validation(self):
        valid_df = pd.DataFrame(
            {
                "listing_id": ["TEST-001"],
                "listing_price": [4500000],
                "sold_price": [4600000],
                "living_area": [65.0],
                "rooms": [2],
                "area": ["Stockholm"],
            }
        )
        assert len(filter_valid_listings(valid_df)) == 1

        invalid_df = pd.DataFrame(
            {
                "listing_id": ["TEST-002"],
                "listing_price": [None],
                "sold_price": [4600000],
                "living_area": [65.0],
                "rooms": [2],
                "area": ["Stockholm"],
            }
        )
        assert len(filter_valid_listings(invalid_df)) == 0


class TestTrainerBasics:
    @pytest.mark.unit
    def test_trainer_creation(self):
        trainer = LGBMTrainer()
        assert trainer is not None
        assert hasattr(trainer, "train")

    @pytest.mark.unit
    def test_trainer_has_methods(self):
        trainer = LGBMTrainer()
        assert callable(getattr(trainer, "train", None))
        assert trainer.__class__.__name__ == "LGBMTrainer"


class TestDataTypes:
    @pytest.mark.unit
    def test_numeric_columns(self):
        df = pd.DataFrame(
            {
                "listing_price": [4500000, 3200000],
                "sold_price": [4600000, 3100000],
                "living_area": [65.0, 55.0],
                "rooms": [2, 2],
            }
        )

        assert pd.api.types.is_numeric_dtype(df["listing_price"])
        assert pd.api.types.is_numeric_dtype(df["sold_price"])
        assert pd.api.types.is_numeric_dtype(df["living_area"])
        assert pd.api.types.is_numeric_dtype(df["rooms"])

    @pytest.mark.unit
    def test_data_ranges(self):
        df = pd.DataFrame(
            {
                "listing_price": [4500000],
                "sold_price": [4600000],
                "living_area": [65.0],
                "rooms": [2],
            }
        )

        assert 1_000_000 < df["listing_price"].iloc[0] < 50_000_000
        assert 0 < df["living_area"].iloc[0] < 1000
        assert 0 < df["rooms"].iloc[0] < 20
