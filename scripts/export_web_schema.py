"""Print the JSON Schema of every type the web app reads from Python.

``just fix`` pipes it through json-schema-to-typescript into
``web/src/lib/generated/api-types.ts``; ``just check`` fails when that file is stale.

Usage: uv run python -m scripts.export_web_schema
"""

from __future__ import annotations

import json
import sys
from typing import Any

from pydantic.json_schema import models_json_schema

from api_server import PredictionRequest, PredictionResponse
from estate_value_index.analytics.web_json import (
    AreaStatisticsData,
    OverallStatisticsData,
    ValueAnalysisData,
)


def _drop_field_titles(node: Any) -> Any:
    # Pydantic titles every field; json-schema-to-typescript would emit one alias per title.
    if isinstance(node, dict):
        return {key: _drop_field_titles(value) for key, value in node.items() if key != "title"}
    if isinstance(node, list):
        return [_drop_field_titles(item) for item in node]
    return node


def web_schema() -> dict[str, Any]:
    _, schema = models_json_schema(
        [
            (PredictionRequest, "validation"),
            (PredictionResponse, "serialization"),
            (ValueAnalysisData, "serialization"),
            (AreaStatisticsData, "serialization"),
            (OverallStatisticsData, "serialization"),
        ],
        ref_template="#/$defs/{model}",
    )
    defs = {
        name: {**_drop_field_titles(definition), "title": name}
        for name, definition in schema["$defs"].items()
    }
    return {"title": "WebTypes", "type": "object", "additionalProperties": False, "$defs": defs}


if __name__ == "__main__":
    json.dump(web_schema(), sys.stdout, indent=2, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")
