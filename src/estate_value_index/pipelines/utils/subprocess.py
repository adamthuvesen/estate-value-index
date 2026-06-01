"""Subprocess execution utilities for pipeline tasks."""

import json
import subprocess
from pathlib import Path
from typing import Any

from .logging import get_task_logger


def run_command(
    cmd: list[str],
    description: str,
    timeout: int = 300,
    cwd: Path | None = None,
    parse_json: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess | dict[str, Any]:
    """Run a command with standard error handling and logging.

    Args:
        cmd: Command and arguments to execute
        description: Human-readable description for logging
        timeout: Timeout in seconds (default 300)
        cwd: Working directory (default: current directory)
        parse_json: If True, parse stdout as JSON and return dict
        check: If True, raise on non-zero exit code

    Returns:
        CompletedProcess if parse_json=False, else parsed JSON dict

    Raises:
        RuntimeError: If command fails and check=True
        json.JSONDecodeError: If parse_json=True and output is not valid JSON
    """
    logger = get_task_logger(__name__)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=cwd or Path.cwd(),
    )

    if check and result.returncode != 0:
        logger.error(f"{description} failed: {result.stderr}")
        raise RuntimeError(f"{description} failed with code {result.returncode}")

    if parse_json:
        return json.loads(result.stdout)

    return result
