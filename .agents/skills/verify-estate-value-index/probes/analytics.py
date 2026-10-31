"""Validate the three derived JSON files against the Pydantic models the web app reads.

Runs inside the temp copy. Arguments: the value_analysis, area_statistics, and
overall_statistics file paths.
"""

import json
import sys
from pathlib import Path

import estate_value_index
from estate_value_index.analytics.web_json import (
    AreaStatisticsData,
    OverallStatisticsData,
    ValueAnalysisData,
)

if __name__ == "__main__":
    value, areas, overall = (json.loads(Path(arg).read_text()) for arg in sys.argv[1:4])
    value_model = ValueAnalysisData.model_validate(value)
    area_model = AreaStatisticsData.model_validate(areas)
    overall_model = OverallStatisticsData.model_validate(overall)
    result = {
        "origin": estate_value_index.__file__,
        "value_properties": len(value_model.properties),
        "areas": len(area_model.areas),
        "overall_properties": overall_model.metadata.total_properties,
    }
    print("PROBE_RESULT " + json.dumps(result))
