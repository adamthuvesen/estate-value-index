"""Contract: optional BigQuery where_clause is not wired from untrusted entrypoints."""

from __future__ import annotations

from pathlib import Path


def test_where_clause_keyword_only_used_in_data_loader() -> None:
    """Lock in that only data_loader defines/parses this optional parameter in Python."""
    repo = Path(__file__).resolve().parents[2]
    data_loader = repo / "src/estate_value_index/ml/data_loader.py"
    needle = "where_clause" + "="
    offenders: list[Path] = []
    for path in repo.rglob("*.py"):
        try:
            rel = path.relative_to(repo)
        except ValueError:
            continue
        if rel.parts and rel.parts[0] in (".venv", "node_modules", "web", "openspec"):
            continue
        if ".venv" in rel.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if needle not in text:
            continue
        if path.resolve() != data_loader.resolve():
            offenders.append(rel)
    assert offenders == [], f"Unexpected where_clause keyword usage in: {offenders}"
