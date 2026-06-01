"""Feature materialization must use staging-then-swap when ``truncate=True``.

The previous flow truncated the production table BEFORE inserting rows,
so any partial batch insert left the table empty/half-populated. The new
flow uploads to a uuid-suffixed staging table, raises on any batch error,
asserts row counts match, then `CREATE OR REPLACE`s production from
staging — and always drops staging in `finally`.
"""

from __future__ import annotations

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

    return env_config


def _patch_bq_client(monkeypatch, client: MagicMock):
    monkeypatch.setattr(feature_materialization, "get_bq_client", MagicMock(return_value=client))


class _FakeQueryResult:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


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

    # CREATE OR REPLACE was issued.
    queries = [call.args[0] for call in client.query.call_args_list]
    create_or_replace = [q for q in queries if "CREATE OR REPLACE TABLE" in q.upper()]
    assert create_or_replace, queries
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
    assert client.delete_table.called
