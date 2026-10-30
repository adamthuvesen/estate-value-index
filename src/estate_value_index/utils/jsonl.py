"""Read listing files that are either one JSON array or JSON Lines."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def load_jsonl_file(file_path: Path) -> list[dict[str, Any]]:
    """Load listings from JSONL file (supports both line-delimited and array format)."""
    listings = []

    if not file_path.exists():
        return listings

    with Path(file_path).open(encoding="utf-8") as f:
        content = f.read().strip()

        # Try JSON array format first
        if content.startswith("["):
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    listings = [item for item in data if isinstance(item, dict)]
                    return listings
            except json.JSONDecodeError:
                pass

        # Fall back to line-delimited JSON
        for line_num, line in enumerate(content.split("\n"), 1):
            line = line.strip()
            if not line:
                continue
            try:
                listing = json.loads(line)
                if isinstance(listing, dict):
                    listings.append(listing)
            except json.JSONDecodeError as e:
                logger.warning("Invalid JSON on line %d: %s", line_num, e)

    return listings
