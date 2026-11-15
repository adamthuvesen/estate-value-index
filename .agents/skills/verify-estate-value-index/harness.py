"""Isolation for the verify drives: a temp copy of the checkout, a temp HOME, and PATH tripwires."""

import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SECRET_NAME = re.compile("KEY|TOKEN|SECRET|PASSWORD")
# Commands a drive must never run. Each shim logs its call and exits 97.
TRIPWIRES = ("gcloud", "gsutil", "bq", "docker", "curl")
# An unroutable proxy makes an HTTP client fail fast instead of reaching the network.
DEAD_PROXY = "http://127.0.0.1:9"
# Tools the repo's own recipes need, found by name before PATH is narrowed.
RECIPE_TOOLS = ("uv", "just", "node", "npm")
COMMAND_TIMEOUT = 40


class DriveFailure(Exception):
    pass


def check(actual: object, expected: object, what: str) -> None:
    if actual != expected:
        raise DriveFailure(f"{what}: expected {expected!r}, got {actual!r}")


def _git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


def tool_dirs() -> list[str]:
    found = {shutil.which(tool) for tool in RECIPE_TOOLS}
    return sorted({str(Path(path).parent) for path in found if path})


class Run:
    """One drive's isolated world. `cmd` runs a child inside it and fails on a tripwire hit."""

    def __init__(self, evidence: Path, name: str) -> None:
        self.evidence = evidence
        self.name = name
        self.scratch = Path(tempfile.mkdtemp(prefix=f"verify-evi-{name}-")).resolve()
        self.home = self.scratch / "home"
        self.copy = self.scratch / "checkout"
        self.tripwire_bin = self.scratch / "tripwires"
        self.tripwire_log = self.scratch / "tripwire.log"
        self.step = 0
        self.home.mkdir()
        self._install_tripwires()
        self._copy_checkout()

    def _install_tripwires(self) -> None:
        self.tripwire_bin.mkdir()
        for name in TRIPWIRES:
            shim = self.tripwire_bin / name
            shim.write_text(f'#!/bin/sh\necho "{name} $*" >> "{self.tripwire_log}"\nexit 97\n')
            shim.chmod(0o755)

    def _copy_checkout(self) -> None:
        listed = _git("ls-files", "-z").split(b"\0") + _git(
            "ls-files", "-z", "--others", "--exclude-standard"
        ).split(b"\0")
        keep_web = {
            "web/package.json",
            "web/package-lock.json",
            "web/src/lib/generated/api-types.ts",
        }
        for raw in filter(None, listed):
            path = raw.decode()
            source = ROOT / path
            if (path.startswith("web/") and path not in keep_web) or not source.is_file():
                continue
            target = self.copy / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        node_modules = ROOT / "web" / "node_modules"
        if node_modules.is_dir():
            (self.copy / "web" / "node_modules").symlink_to(node_modules)

    def env(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        path = [str(self.tripwire_bin), str(Path(sys.executable).parent), *tool_dirs()]
        environment = {
            "PATH": ":".join([*path, "/usr/bin", "/bin"]),
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / "config"),
            "XDG_CACHE_HOME": str(self.home / "cache"),
            "XDG_DATA_HOME": str(self.home / "data"),
            "CLOUDSDK_CONFIG": str(self.home / "gcloud"),
            "UV_CACHE_DIR": str(self.home / "uv-cache"),
            "UV_PROJECT_ENVIRONMENT": sys.prefix,
            "PYTHONPATH": f"{self.copy / 'src'}:{self.copy}",
            "PYTHONDONTWRITEBYTECODE": "1",
            "NO_GCE_CHECK": "true",
            "HTTP_PROXY": DEAD_PROXY,
            "HTTPS_PROXY": DEAD_PROXY,
            "ALL_PROXY": DEAD_PROXY,
            "GCS_ENABLED": "false",
            "TZ": "UTC",
            "NO_COLOR": "1",
            "COLUMNS": "200",
        }
        return {**environment, **(extra or {})}

    def tripwire_hits(self) -> list[str]:
        return self.tripwire_log.read_text().splitlines() if self.tripwire_log.exists() else []

    def cmd(
        self,
        argv: Sequence[str],
        *,
        extra_env: dict[str, str] | None = None,
        expect_exit: int | None = 0,
        timeout: float = COMMAND_TIMEOUT,
    ) -> subprocess.CompletedProcess[str]:
        environment = self.env(extra_env)
        label = " ".join(Path(a).name if a.startswith("/") else a for a in argv)[:120]
        try:
            proc = subprocess.run(
                list(argv),
                cwd=self.copy,
                env=environment,
                capture_output=True,
                text=True,
                timeout=timeout,
                start_new_session=True,
            )
        except subprocess.TimeoutExpired as error:
            raise DriveFailure(f"`{label}` timed out after {timeout}s") from error
        self.step += 1
        record = {
            "argv": list(argv),
            "env": {
                k: "<redacted>" if SECRET_NAME.search(k) else v for k, v in environment.items()
            },
            "exit": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
        (self.evidence / f"{self.name}.{self.step}.json").write_text(json.dumps(record, indent=2))
        hits = self.tripwire_hits()
        if hits:
            raise DriveFailure(f"tripwire hit by `{label}`: {'; '.join(hits)[:200]}")
        if expect_exit is not None and proc.returncode != expect_exit:
            tail = (proc.stderr or proc.stdout).strip()[-300:]
            raise DriveFailure(
                f"`{label}` expected exit {expect_exit}, got {proc.returncode}: {tail}"
            )
        return proc

    def probe(
        self, script: str, *args: str, extra_env: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Run a probe script from the skill dir inside the copy; return its PROBE_RESULT payload."""
        probe_path = self.copy / ".agents/skills/verify-estate-value-index/probes" / script
        proc = self.cmd([sys.executable, str(probe_path), *args], extra_env=extra_env)
        for line in proc.stdout.splitlines():
            if line.startswith("PROBE_RESULT "):
                result = json.loads(line.removeprefix("PROBE_RESULT "))
                origin = Path(str(result["origin"])).resolve()
                if not origin.is_relative_to(self.copy):
                    raise DriveFailure(
                        f"{script} imported estate_value_index from {origin}, not the copy"
                    )
                return result
        raise DriveFailure(
            f"{script} exited {proc.returncode} without a PROBE_RESULT line (early exit)"
        )

    def cleanup(self) -> None:
        shutil.rmtree(self.scratch, ignore_errors=True)
