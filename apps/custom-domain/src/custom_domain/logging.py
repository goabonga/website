# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Logging configuration with dual output streams.

Configures logging to send INFO/DEBUG to stdout and WARNING/ERROR/CRITICAL to stderr.
This allows systemd to capture logs appropriately:
- StandardOutput -> output.log (info, debug)
- StandardError -> error.log (warning, error, critical)
"""

import contextvars
import logging
import sys

from custom_domain.config import settings


class StdoutFilter(logging.Filter):
    """Filter that only allows INFO and DEBUG level records."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= logging.INFO


class StderrFilter(logging.Filter):
    """Filter that only allows WARNING, ERROR and CRITICAL level records."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.WARNING


def setup_logging(level: str | None = None) -> None:
    """Configure logging with dual output streams.

    Args:
        level: Minimum logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
               Defaults to settings.log_level.
    """
    if level is None:
        level = settings.log_level

    log_level = getattr(logging, level.upper(), logging.INFO)

    # Create formatters
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Stdout handler for INFO and DEBUG
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.addFilter(StdoutFilter())
    stdout_handler.setFormatter(formatter)

    # Stderr handler for WARNING, ERROR, CRITICAL
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.addFilter(StderrFilter())
    stderr_handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()
    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(stderr_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("celery").setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


# Thread-local storage for request context
_request_context: contextvars.ContextVar[dict] = contextvars.ContextVar("request_context")


def set_request_context(**kwargs: str) -> None:
    """Set request-scoped context for structured logging.

    Args:
        **kwargs: Key-value pairs to add to the logging context.
    """
    try:
        ctx = _request_context.get().copy()
    except LookupError:
        ctx = {}
    ctx.update(kwargs)
    _request_context.set(ctx)


def clear_request_context() -> None:
    """Clear the request context."""
    _request_context.set({})
