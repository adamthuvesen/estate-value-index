"""Framework-agnostic analytics generation library.

Holds the area-statistics and value-analysis computation logic shared by the
CLI entrypoints (`estate_value_index.cli`) and the Prefect tasks
(`estate_value_index.pipelines.tasks.analytics`). No argparse or Prefect here.
"""

from estate_value_index.analytics.area_statistics import generate_area_statistics
from estate_value_index.analytics.value_analysis import run_analysis

__all__ = ["generate_area_statistics", "run_analysis"]
