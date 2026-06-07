"""Contract: the raw where_clause SQL hatch is retired in favour of structured filters."""

from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_DATA_LOADER = _REPO / "src/estate_value_index/ml/data_loader.py"

# Matches `where_clause` used as a parameter / keyword arg / assignment (i.e.
# actual code), not prose mentions of the retired hatch in docstrings.
_WHERE_CLAUSE_PARAM = re.compile(r"where_clause\s*[:=]")


def test_raw_where_clause_hatch_is_gone() -> None:
    """No source module should expose or pass a raw `where_clause` SQL string."""
    offenders = [
        path.relative_to(_REPO)
        for path in (_REPO / "src").rglob("*.py")
        if _WHERE_CLAUSE_PARAM.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], (
        f"raw where_clause hatch reintroduced in: {offenders}; "
        "use Filter + build_filter_clause instead"
    )


def test_bigquery_loaders_use_structured_filters() -> None:
    """The BigQuery loaders must build predicates via build_filter_clause."""
    text = _DATA_LOADER.read_text(encoding="utf-8")
    assert "build_filter_clause" in text
    assert "filters: Sequence[Filter] | None" in text
