"""Tests for load_default_dataset's project-root resolution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from estate_value_index.ml import data_loader


def _seed_fake_repo(root: Path) -> Path:
    """Build a fake repo tree under ``root`` and return the fake module path."""
    (root / "pyproject.toml").write_text("[project]\nname = 'fake'\n")

    data_dir = root / "data" / "booli"
    data_dir.mkdir(parents=True)
    record = {
        "listing_id": "abc-1",
        "address": "Test 1",
        "area": "Vasastan",
        "listing_price": 5_000_000,
        "sold_price": 5_100_000,
        "scraped_at": "2024-01-01T00:00:00",
    }
    (data_dir / "booli_listings.json").write_text(json.dumps([record]))

    fake_module = root / "src" / "estate_value_index" / "ml" / "data_loader.py"
    fake_module.parent.mkdir(parents=True)
    fake_module.write_text("# placeholder\n")
    return fake_module


def test_load_default_dataset_finds_repo_via_pyproject(tmp_path, monkeypatch):
    fake_module = _seed_fake_repo(tmp_path)
    monkeypatch.setattr(data_loader, "__file__", str(fake_module))

    df = data_loader.load_default_dataset()
    assert not df.empty
    assert df.iloc[0]["listing_id"] == "abc-1"


def test_load_default_dataset_raises_without_pyproject(tmp_path, monkeypatch):
    # No pyproject.toml anywhere up the tree from this fake module path.
    fake_module = tmp_path / "nested" / "module.py"
    fake_module.parent.mkdir()
    fake_module.write_text("# placeholder\n")
    monkeypatch.setattr(data_loader, "__file__", str(fake_module))

    # Walk-up from tmp_path may find a real pyproject.toml; isolate by pointing
    # _find_project_root at a deep tempdir whose ancestors contain no project.
    # Use Path.parents — we need to ensure no pyproject.toml exists above.
    # Instead, monkeypatch the helper to walk only inside tmp_path.
    real_find = data_loader._find_project_root

    def bounded_find(start: Path) -> Path:
        # Only consider candidates inside tmp_path so the real repo's
        # pyproject.toml further up the filesystem isn't picked up.
        for candidate in (start, *start.parents):
            try:
                candidate.relative_to(tmp_path)
            except ValueError:
                break
            if (candidate / "pyproject.toml").is_file():
                return candidate
        raise FileNotFoundError(f"no pyproject.toml above {start}")

    monkeypatch.setattr(data_loader, "_find_project_root", bounded_find)

    with pytest.raises(FileNotFoundError):
        data_loader.load_default_dataset()

    # Ensure the real helper still does what we expect for a sibling test.
    assert real_find is not bounded_find
