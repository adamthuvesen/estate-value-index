"""Logging utilities for pipeline tasks."""

import logging
from logging import Logger

from prefect import get_run_logger
from prefect.exceptions import MissingContextError


def get_task_logger(name: str) -> Logger:
    """Get Prefect logger or fallback to standard logging.

    Args:
        name: Logger name (typically __name__ of calling module)

    Returns:
        Prefect run logger if in Prefect context, else standard logger
    """
    try:
        return get_run_logger()
    except MissingContextError:
        return logging.getLogger(name)
