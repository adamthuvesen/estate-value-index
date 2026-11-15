"""Detector tests for the module bans and the layer contract.

A ban or contract that stops working must fail here. Each test strips the owner
allowances (or plants a violation) and asserts that the detector still reports a
known real case.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
from importlinter import cli

REPO = Path(__file__).resolve().parents[1]
PYPROJECT = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
IMPORT_LINTER = PYPROJECT["tool"]["importlinter"]
CONTRACTS = {contract["name"]: contract for contract in IMPORT_LINTER["contracts"]}

FORBIDDEN = {
    name: contract for name, contract in CONTRACTS.items() if contract["type"] == "forbidden"
}
# A real import that goes against a reversed layer order.
KNOWN_LAYER_IMPORT = "estate_value_index.analytics.area_statistics"


def _ini_value(value: object) -> str:
    if isinstance(value, list):
        return "\n    " + "\n    ".join(str(item) for item in value)
    return str(value)


def _write_config(path: Path, contracts: list[dict[str, Any]]) -> None:
    lines = ["[importlinter]"]
    lines += [
        f"{key} = {_ini_value(value)}" for key, value in IMPORT_LINTER.items() if key != "contracts"
    ]
    for index, contract in enumerate(contracts):
        lines.append(f"[importlinter:contract:{index}]")
        lines += [f"{key} = {_ini_value(value)}" for key, value in contract.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture(scope="module")
def stripped_report(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Run import-linter with owner allowances removed and the layers reversed."""
    directory = tmp_path_factory.mktemp("import_linter")
    contracts = []
    for contract in CONTRACTS.values():
        contract = {key: value for key, value in contract.items() if key != "ignore_imports"}
        if contract["type"] == "layers":
            contract["layers"] = list(reversed(contract["layers"]))
        contracts.append(contract)
    config = directory / "importlinter.ini"
    _write_config(config, contracts)

    output = directory / "report.txt"
    with pytest.MonkeyPatch.context() as patch, output.open("w", encoding="utf-8") as sink:
        patch.setenv("COLUMNS", "300")
        patch.setattr(sys, "stdout", sink)
        status = cli.lint_imports(config_filename=str(config), cache_dir=str(directory / "cache"))
    assert status != 0, "stripped contracts must break"
    return output.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", FORBIDDEN)
def test_forbidden_contract_catches_each_real_owner_import(name: str, stripped_report: str) -> None:
    section = stripped_report.split(f"{name}\n{'-' * len(name)}")[1]
    owners = [entry.split(" -> ")[0] for entry in FORBIDDEN[name]["ignore_imports"]]
    assert owners
    for owner in owners:
        assert owner in section


def test_layers_contract_catches_a_known_real_import(stripped_report: str) -> None:
    assert "Layers" in CONTRACTS
    section = stripped_report.split("Layers\n------")[1]
    assert KNOWN_LAYER_IMPORT in section


def _ruff_codes(source: str, filename: str) -> str:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--stdin-filename",
            filename,
            "--select",
            "TID251",
            "-",
        ],
        input=source,
        capture_output=True,
        text=True,
        cwd=REPO,
        check=False,
    )
    return result.stdout


BANNED_CALLS = [
    "import urllib.request",
    "from urllib import request",
    "import http.client",
    "import os\nos.system('x')",
    "import os\nos.popen('x')",
    "import os\nos.execv('a', [])",
    "import os\nos.spawnv(0, 'a', [])",
    "import asyncio\nasyncio.create_subprocess_exec('a')",
    "import asyncio\nasyncio.subprocess.PIPE",
]


@pytest.mark.parametrize("source", BANNED_CALLS)
def test_ruff_ban_catches_planted_violation(source: str) -> None:
    assert "TID251" in _ruff_codes(source, "src/estate_value_index/planted.py")


def test_urllib_request_is_allowed_only_in_its_owner() -> None:
    owner = REPO / "src/estate_value_index/ingestion/booli/api.py"
    source = owner.read_text(encoding="utf-8")
    assert "import urllib.request" in source
    assert "TID251" not in _ruff_codes(source, str(owner.relative_to(REPO)))
    assert "TID251" in _ruff_codes(source, "src/estate_value_index/ingestion/other.py")
