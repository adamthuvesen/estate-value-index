"""Feature materialization must use staging-then-publish when ``truncate=True``.

The previous flow truncated the production table BEFORE inserting rows,
so any partial batch insert left the table empty/half-populated. The new
flow uploads to a uuid-suffixed staging table, raises on any batch error, asserts
row counts match, then replaces rows in the existing production table without
changing table metadata, and always drops staging in `finally`.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pandas as pd
import pytest

from estate_value_index.ml import feature_materialization


@pytest.fixture
def fake_env(monkeypatch):
    """Stub out every external dependency of `materialize_features`."""

    env_config = MagicMock()
    env_config.bigquery_project_id = "estate-value-index"
    env_config.bq_dataset_features = "booli_features"
    env_config.bq_table_features = "engineered_features"
    monkeypatch.setattr(feature_materialization, "load_env_config", lambda: env_config)
    monkeypatch.setattr(feature_materialization, "get_batch_size", lambda: 2)
    monkeypatch.setattr(
        feature_materialization,
        "bq_table",
        lambda p, d, t: f"{p}.{d}.{t}",
    )

    raw_df = pd.DataFrame(
        {
            "listing_id": ["1", "2", "3"],
            "listing_price": [3_900_000, 4_900_000, 5_900_000],
            "price_per_sqm": [78_000, 81_000, 84_000],
            "sold_price": [4_000_000, 5_000_000, 6_000_000],
            "sold_date": ["2024-01-01", "2024-02-01", "2024-03-01"],
            "address": ["A", "B", "C"],
            "area": ["X", "Y", "Z"],
        }
    )
    monkeypatch.setattr(
        feature_materialization, "load_from_bigquery", lambda project_id=None: raw_df
    )
    monkeypatch.setattr(
        feature_materialization,
        "join_geocodes",
        lambda df, project_id, **kw: df.assign(lat=59.3, lon=18.0),
    )
    monkeypatch.setattr(feature_materialization, "filter_valid_listings", lambda df, **kw: df)
    monkeypatch.setattr(feature_materialization, "create_optimized_features", lambda df: df)

    monkeypatch.setattr(feature_materialization, "NUMERIC_FEATURE_NAMES", [])
    monkeypatch.setattr(feature_materialization, "CATEGORICAL_FEATURE_NAMES", [])
    monkeypatch.setattr(feature_materialization, "_sync_feature_table_schema", lambda *a, **k: [])

    return env_config


def _patch_bq_client(monkeypatch, client: MagicMock):
    monkeypatch.setattr(feature_materialization, "get_bq_client", MagicMock(return_value=client))


def test_prepare_feature_rows_keeps_new_transit_and_text_features():
    df = pd.DataFrame(
        {
            "listing_id": ["1"],
            "sold_price": [4_000_000],
            "sold_date": ["2024-01-01"],
            "distance_to_nearest_metro": [120.5],
            "transit_accessibility_score": [0.82],
            "micro_area_ppsqm_p90": [115000.0],
            "micro_area_upper_tail_ratio": [1.18],
            "h3_neighbor_ppsqm": [101000.0],
            "h3_neighbor_ppsqm_p90": [118000.0],
            "h3_neighbor_upper_tail_ratio": [1.17],
            "same_size_ppsqm_median": [98000.0],
            "same_size_ppsqm_p90": [121000.0],
            "same_size_upper_tail_ratio": [1.23],
            "street_name": ["grev magnigatan"],
            "street_area_ppsqm_median": [150000.0],
            "street_area_ppsqm_p90": [190000.0],
            "street_area_upper_tail_ratio": [1.27],
            "street_size_ppsqm_median": [160000.0],
            "address_ppsqm_median": [170000.0],
            "address_comp_scope_used": ["address"],
            "market_interest_rate": [1.75],
            "h3_market_ppsqm_ratio": [1.12],
            "micro_luxury_score": [0.72],
            "luxury_location_tier": ["premium"],
            "description_word_count": [18],
            "condition_score": [3.5],
            "premium_score": [2.0],
        }
    )

    rows = feature_materialization.prepare_feature_rows(df, date(2024, 2, 1))

    assert rows[0]["distance_to_nearest_metro"] == 120.5
    assert rows[0]["transit_accessibility_score"] == 0.82
    assert rows[0]["micro_area_ppsqm_p90"] == 115000.0
    assert rows[0]["micro_area_upper_tail_ratio"] == 1.18
    assert rows[0]["h3_neighbor_ppsqm"] == 101000.0
    assert rows[0]["h3_neighbor_ppsqm_p90"] == 118000.0
    assert rows[0]["h3_neighbor_upper_tail_ratio"] == 1.17
    assert rows[0]["same_size_ppsqm_median"] == 98000.0
    assert rows[0]["same_size_ppsqm_p90"] == 121000.0
    assert rows[0]["same_size_upper_tail_ratio"] == 1.23
    assert rows[0]["street_name"] == "grev magnigatan"
    assert rows[0]["street_area_ppsqm_median"] == 150000.0
    assert rows[0]["street_area_ppsqm_p90"] == 190000.0
    assert rows[0]["street_area_upper_tail_ratio"] == 1.27
    assert rows[0]["street_size_ppsqm_median"] == 160000.0
    assert rows[0]["address_ppsqm_median"] == 170000.0
    assert rows[0]["address_comp_scope_used"] == "address"
    assert rows[0]["market_interest_rate"] == 1.75
    assert rows[0]["h3_market_ppsqm_ratio"] == 1.12
    assert rows[0]["micro_luxury_score"] == 0.72
    assert rows[0]["luxury_location_tier"] == "premium"
    assert rows[0]["description_word_count"] == 18
    assert rows[0]["condition_score"] == 3.5
    assert rows[0]["premium_score"] == 2.0


class _FakeQueryResult:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


def test_join_geocodes_uses_regular_bigquery_download(monkeypatch):
    client = MagicMock()
    query_job = MagicMock()
    query_job.to_dataframe.return_value = pd.DataFrame(
        {"address": ["A, x"], "lat": [59.3], "lon": [18.0]}
    )
    client.query.return_value = query_job
    _patch_bq_client(monkeypatch, client)

    feature_materialization.join_geocodes(
        pd.DataFrame({"address": ["A"], "area": ["X"]}),
        "estate-value-index",
    )

    query_job.to_dataframe.assert_called_once_with(create_bqstorage_client=False)


def test_sync_feature_table_schema_adds_missing_nullable_fields(tmp_path):
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(
        """
        [
          {"name": "listing_id", "type": "STRING", "mode": "REQUIRED"},
          {"name": "sold_price", "type": "FLOAT64", "mode": "NULLABLE"},
          {"name": "new_feature", "type": "FLOAT64", "mode": "NULLABLE"}
        ]
        """,
        encoding="utf-8",
    )
    existing = feature_materialization._load_feature_schema_fields(schema_path)[:2]
    table = MagicMock()
    table.schema = existing
    client = MagicMock()
    client.get_table.return_value = table

    target = feature_materialization.FeatureUploadTarget(
        dataset_id="booli_features",
        table_id="engineered_features",
        full_table_id="estate-value-index.booli_features.engineered_features",
        staging_table_id=None,
        staging_id=None,
        upload_target="estate-value-index.booli_features.engineered_features",
    )

    added = feature_materialization._sync_feature_table_schema(
        client,
        "estate-value-index",
        target,
        schema_path=schema_path,
    )

    assert added == ["new_feature"]
    assert [field.name for field in table.schema] == [
        "listing_id",
        "sold_price",
        "new_feature",
    ]
    client.update_table.assert_called_once_with(table, ["schema"])


def test_sync_feature_table_schema_rejects_missing_required_fields(tmp_path):
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(
        """
        [
          {"name": "listing_id", "type": "STRING", "mode": "REQUIRED"}
        ]
        """,
        encoding="utf-8",
    )
    table = MagicMock()
    table.schema = []
    client = MagicMock()
    client.get_table.return_value = table
    target = feature_materialization.FeatureUploadTarget(
        dataset_id="booli_features",
        table_id="engineered_features",
        full_table_id="estate-value-index.booli_features.engineered_features",
        staging_table_id=None,
        staging_id=None,
        upload_target="estate-value-index.booli_features.engineered_features",
    )

    with pytest.raises(RuntimeError, match="missing required schema fields"):
        feature_materialization._sync_feature_table_schema(
            client,
            "estate-value-index",
            target,
            schema_path=schema_path,
        )

    client.update_table.assert_not_called()


def test_truncate_path_swaps_staging_to_production_on_success(monkeypatch, fake_env):
    client = MagicMock()
    # All inserts return [] (no errors)
    client.insert_rows_json.return_value = []

    query_job = MagicMock()
    query_job.result.return_value = _FakeQueryResult([{"count": 3}])
    client.query.return_value = query_job

    _patch_bq_client(monkeypatch, client)

    result = feature_materialization.materialize_features(truncate=True, batch_size=2)
    assert result["row_count"] == 3

    # All inserts target staging, never the production table directly.
    insert_targets = {call.args[0] for call in client.insert_rows_json.call_args_list}
    assert all("_staging_" in target for target in insert_targets), insert_targets
    assert all(
        target.startswith("estate-value-index.booli_features.engineered_features_staging_")
        for target in insert_targets
    ), insert_targets

    # Staging table was created before inserts, then production rows were replaced.
    queries = [call.args[0] for call in client.query.call_args_list]
    create_staging = [q for q in queries if "CREATE TABLE" in q.upper() and "WHERE FALSE" in q]
    assert create_staging, queries
    assert client.query.call_args_list[0].args[0] == create_staging[0]
    assert client.query.call_args_list[0].args[0].find("_staging_") > -1
    publish_queries = [q for q in queries if "BEGIN TRANSACTION" in q.upper()]
    assert publish_queries, queries
    publish_query = publish_queries[0].upper()
    assert "DELETE FROM" in publish_query
    assert "INSERT INTO" in publish_query
    assert "COMMIT TRANSACTION" in publish_query
    assert "CREATE OR REPLACE TABLE" not in publish_query
    # No raw TRUNCATE TABLE issued against production.
    assert not any("TRUNCATE TABLE" in q.upper() for q in queries)

    # Staging deleted at the end.
    assert client.delete_table.called
    assert client.delete_table.call_args.kwargs.get("not_found_ok") is True


def test_truncate_path_raises_on_batch_error_and_skips_swap(monkeypatch, fake_env):
    client = MagicMock()
    # First batch ok, second batch errors.
    client.insert_rows_json.side_effect = [[], [{"index": 0, "errors": ["bad row"]}]]

    query_job = MagicMock()
    query_job.result.return_value = _FakeQueryResult([{"count": 0}])
    client.query.return_value = query_job

    _patch_bq_client(monkeypatch, client)

    with pytest.raises(RuntimeError, match="insert failed"):
        feature_materialization.materialize_features(truncate=True, batch_size=2)

    queries = [call.args[0] for call in client.query.call_args_list]
    assert not any("CREATE OR REPLACE TABLE" in q.upper() for q in queries)
    assert not any("DELETE FROM" in q.upper() for q in queries)
    # Staging still cleaned up.
    assert client.delete_table.called


def test_truncate_path_raises_on_row_count_mismatch(monkeypatch, fake_env):
    client = MagicMock()
    client.insert_rows_json.return_value = []

    # Staging count comes back wrong (e.g. 2 instead of 3).
    query_job = MagicMock()
    query_job.result.return_value = _FakeQueryResult([{"count": 2}])
    client.query.return_value = query_job

    _patch_bq_client(monkeypatch, client)

    with pytest.raises(RuntimeError, match="row count mismatch"):
        feature_materialization.materialize_features(truncate=True, batch_size=2)

    queries = [call.args[0] for call in client.query.call_args_list]
    assert not any("CREATE OR REPLACE TABLE" in q.upper() for q in queries)
    assert not any("DELETE FROM" in q.upper() for q in queries)
    assert client.delete_table.called


def test_materialization_masks_ask_price_signals_before_engineering(monkeypatch, fake_env):
    captured = {}

    def capture_engineering_input(df: pd.DataFrame) -> pd.DataFrame:
        captured["listing_price"] = df["listing_price"].copy()
        captured["price_per_sqm"] = df["price_per_sqm"].copy()
        return df

    monkeypatch.setattr(
        feature_materialization, "create_optimized_features", capture_engineering_input
    )

    feature_materialization.materialize_features(dry_run=True)

    assert captured["listing_price"].isna().all()
    assert captured["price_per_sqm"].isna().all()
