"""Analytics generation: the derived web JSON files and their contract (``web_json``).

The ``evi`` CLI entrypoints (``estate_value_index.cli.generate_*``) are thin shells
over these functions. No argparse here.
"""

from estate_value_index.analytics.area_statistics import generate_area_statistics
from estate_value_index.analytics.value_analysis import generate_value_analysis

__all__ = ["generate_area_statistics", "generate_value_analysis"]
