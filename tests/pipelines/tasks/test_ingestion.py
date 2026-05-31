"""Tests for Prefect ingestion tasks (BigQuery safety)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from estate_value_index.pipelines.tasks.ingestion import geocode_new_addresses_task


@pytest.mark.unit
def test_geocode_new_addresses_query_uses_bq_parameter_for_batch_size() -> None:
    """LIMIT uses @batch_size; value is bound via QueryJobConfig, not string interpolation."""
    captured: dict = {}

    def _query(query: str, job_config: object | None = None) -> MagicMock:
        captured["query"] = query
        captured["job_config"] = job_config
        out = MagicMock()
        out.to_dataframe.return_value = pd.DataFrame()
        return out

    mock_client = MagicMock()
    mock_client.query.side_effect = _query

    with patch(
        "estate_value_index.pipelines.tasks.ingestion.get_bq_client",
        return_value=mock_client,
    ):
        geocode_new_addresses_task.fn(project_id="estate-value-index", batch_size=4242)

    q = captured["query"]
    assert "@batch_size" in q
    assert "4242" not in q
    jc = captured["job_config"]
    assert jc is not None
    names = [p.name for p in jc.query_parameters]
    assert "batch_size" in names
