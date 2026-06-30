"""Regression guard against unsafe dynamic SQL.

This test statically scans ``src/`` for f-strings that look like SQL and contain
at least one interpolation. Such an f-string is considered **safe** only when
every interpolation is a direct call to a vetted helper
(:func:`safe_table_ref` / :func:`quote_identifier` in
``estate_value_index.utils.bigquery_safety``), which validates and quotes the
identifier before it reaches the query.

Any other dynamic SQL (interpolating a bare variable, attribute, or expression)
must be listed in ``REVIEWED_DYNAMIC_SQL`` with a human-readable reason. That
makes every hand-built SQL string in the codebase a single, auditable list:
adding a new one fails CI until the author either routes it through the helpers
or consciously registers it (forcing review).

Limitation (documented on purpose): detection keys off *uppercase* SQL keywords,
matching the codebase convention. A query written with lowercase keywords would
evade the scan — but our SQL is uppercase, and the helpers are the path of least
resistance anyway.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

# qualname -> reason. Each entry is dynamic SQL that interpolates something other
# than a safe_table_ref()/quote_identifier() call, and has been reviewed.
REVIEWED_DYNAMIC_SQL: dict[str, str] = {
    "estate_value_index.pipelines.tasks.sync:sync_bigquery_to_local_task": (
        "`table_ref` is BigQueryConfig.full_table_id, which is validated via "
        "safe_table_ref() in the property."
    ),
    "estate_value_index.pipelines.tasks.sync:verify_sync_task": (
        "`table_ref` is the validated BigQueryConfig.full_table_id."
    ),
    "estate_value_index.pipelines.tasks.ingestion:upload_to_bigquery_task": (
        "TRUNCATE interpolates the validated BigQueryConfig.full_table_id."
    ),
    "estate_value_index.pipelines.tasks.ingestion:_merge_query": (
        "MERGE interpolates the validated full_table_id + a safe_table_ref() "
        "temp ref; column lists go through quote_identifier()."
    ),
    "estate_value_index.ingestion.bigquery_upload:_merge_temp_table": (
        "`full_table_id`/`temp_table_id` are validated by bq_table()/safe_table_ref() "
        "at their construction sites; column list is a static literal."
    ),
    "estate_value_index.ingestion.bigquery_upload:_verify_row_count": (
        "`full_table_id` is the validated bq_table() result."
    ),
    "estate_value_index.ops.cost_monitoring:monitor_bigquery_costs": (
        "`project_id` is validated via _validate_bq_project_id() above; the region "
        "+ INFORMATION_SCHEMA.JOBS path components are static literals; `days` is a "
        "ScalarQueryParameter."
    ),
}

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
_PKG_ROOT = _SRC_ROOT / "estate_value_index"

# Vetted helpers: an interpolation that is a direct call to one of these is safe.
_SAFE_CALLS = {"safe_table_ref", "quote_identifier"}

# An f-string is treated as SQL only when its literal parts show SQL *structure*
# (not a lone keyword), so prose like "Continuing with MERGE for N rows" is not
# flagged. Case-sensitive uppercase, matching the codebase's SQL convention.
# The trailing ``^\s*WHERE`` arm catches a raw predicate fragment appended to a
# query — the pattern the retired ``where_clause`` hatch used; structured filters
# go through build_filter_clause() instead and never produce one here.
_SQL_STATEMENT = re.compile(
    r"""(?xms)
      \bSELECT\b .*? \bFROM\b        # SELECT ... FROM
    | \bMERGE\b \s+ [`{]             # MERGE `tbl` / MERGE {ref}
    | \bINSERT \s+ INTO\b
    | \bCREATE\b .*? \bTABLE\b
    | \bTRUNCATE \s+ TABLE\b
    | \bDELETE \s+ FROM\b
    | \bUPDATE\b .*? \bSET\b
    | ^ \s* WHERE\b                  # appended predicate fragment
    """
)


def _module_name(path: Path) -> str:
    """Dotted module path for a file under ``src/`` (e.g. ``a.b.c``)."""
    rel = path.relative_to(_SRC_ROOT).with_suffix("")
    return ".".join(rel.parts)


def _is_safe_call(node: ast.expr) -> bool:
    """True if ``node`` is a direct call to a vetted identifier helper."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
    return name in _SAFE_CALLS


def _joinedstr_text(node: ast.JoinedStr) -> str:
    """Concatenate the literal (non-interpolated) parts of an f-string."""
    return "".join(part.value for part in node.values if isinstance(part, ast.Constant))


def _find_unsafe_sql(tree: ast.AST, module: str) -> list[tuple[str, int]]:
    """Return ``(qualname, lineno)`` for each needs-review SQL f-string in a module."""
    findings: list[tuple[str, int]] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self._stack: list[str] = []

        def _visit_scope(self, node: ast.AST) -> None:
            self._stack.append(node.name)  # type: ignore[attr-defined]
            self.generic_visit(node)
            self._stack.pop()

        visit_FunctionDef = _visit_scope  # type: ignore[assignment]
        visit_AsyncFunctionDef = _visit_scope  # type: ignore[assignment]
        visit_ClassDef = _visit_scope  # type: ignore[assignment]

        def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
            interpolations = [v for v in node.values if isinstance(v, ast.FormattedValue)]
            if interpolations and _SQL_STATEMENT.search(_joinedstr_text(node)):
                if not all(_is_safe_call(fv.value) for fv in interpolations):
                    qualname = f"{module}:{'.'.join(self._stack) or '<module>'}"
                    findings.append((qualname, node.lineno))
            self.generic_visit(node)

    Visitor().visit(tree)
    return findings


def _scan() -> dict[str, list[int]]:
    """Map qualname -> line numbers of needs-review SQL f-strings across the package."""
    result: dict[str, list[int]] = {}
    for path in sorted(_PKG_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for qualname, lineno in _find_unsafe_sql(tree, _module_name(path)):
            result.setdefault(qualname, []).append(lineno)
    return result


def test_no_unreviewed_dynamic_sql() -> None:
    """Every hand-built SQL f-string must use the helpers or be in the registry."""
    found = _scan()
    found_keys = set(found)
    registered = set(REVIEWED_DYNAMIC_SQL)

    unexpected = {k: found[k] for k in found_keys - registered}
    assert not unexpected, (
        "Unreviewed dynamic SQL found. Route the interpolation through "
        "safe_table_ref()/quote_identifier(), or add an entry to "
        "REVIEWED_DYNAMIC_SQL with a justification:\n"
        + "\n".join(f"  - {k} (line(s): {v})" for k, v in sorted(unexpected.items()))
    )

    stale = registered - found_keys
    assert not stale, (
        "REVIEWED_DYNAMIC_SQL has stale entries (the code no longer builds SQL "
        "this way — remove them):\n" + "\n".join(f"  - {k}" for k in sorted(stale))
    )


def test_safe_helpers_are_importable() -> None:
    """Guard against the helper names drifting out from under this test."""
    from estate_value_index.utils.bigquery_safety import (  # noqa: F401
        quote_identifier,
        safe_table_ref,
    )
