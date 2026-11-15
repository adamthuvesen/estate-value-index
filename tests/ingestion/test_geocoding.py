from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest

from estate_value_index.ingestion import geocoding


def test_geocode_query_binds_batch_size_as_a_parameter(mocker: Any) -> None:
    client = MagicMock()
    client.query.return_value.to_dataframe.return_value = pd.DataFrame()
    mocker.patch.object(geocoding, "get_bq_client", return_value=client)

    geocoding.geocode_new_addresses(project_id="estate-value-index", batch_size=4242, approved=True)

    query = client.query.call_args.args[0]
    job_config = client.query.call_args.kwargs["job_config"]
    assert "@batch_size" in query
    assert "4242" not in query
    assert [param.name for param in job_config.query_parameters] == ["batch_size"]


def test_geocode_insert_errors_raise(mocker: Any) -> None:
    client = MagicMock()
    client.query.return_value.to_dataframe.return_value = pd.DataFrame(
        [{"address": "Street 1", "area": "Solna", "geocode_key": "Street 1, solna"}]
    )
    client.insert_rows_json.return_value = [{"index": 0, "errors": ["bad row"]}]
    mocker.patch.object(geocoding, "get_bq_client", return_value=client)
    mocker.patch.object(geocoding, "geocode_address", return_value=(59.3, 18.0))

    with pytest.raises(RuntimeError, match="geocode insert errors"):
        geocoding.geocode_new_addresses(
            project_id="test-project", rate_limit_delay=0, approved=True
        )
