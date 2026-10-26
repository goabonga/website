# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Logging configuration for Mailler API.

Provides dual-stream logging for proper systemd journal integration:
- INFO/DEBUG messages go to stdout
- WARNING/ERROR/CRITICAL messages go to stderr

Includes request context support for user and client tracking.
"""

import logging
import sys
from contextvars import ContextVar
from typing import Any

# Context variables for request-scoped logging
request_context: ContextVar[dict[str, Any] | None] = ContextVar("request_context", default=None)


class ContextFilter(logging.Filter):
    """Add request context to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Add context variables to log record."""
        ctx = request_context.get() or {}
        record.user_id = ctx.get("user_id", "-")  # type: ignore[attr-defined]
        record.client_id = ctx.get("client_id", "-")  # type: ignore[attr-defined]
        return True


class StdoutFilter(logging.Filter):
    """Filter to only allow INFO and DEBUG level messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Only allow INFO and DEBUG."""
        return record.levelno <= logging.INFO


class StderrFilter(logging.Filter):
    """Filter to only allow WARNING, ERROR, and CRITICAL level messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Only allow WARNING and above."""
        return record.levelno >= logging.WARNING


def setup_logging(level: str = "INFO") -> None:
    """Configure dual-stream logging with request context for systemd compatibility.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Format with user context
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | user=%(user_id)s | client=%(client_id)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Clear existing handlers
    root_logger.handlers.clear()

    # Stdout handler (INFO and below)
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.addFilter(StdoutFilter())
    stdout_handler.addFilter(ContextFilter())
    stdout_handler.setFormatter(formatter)

    # Stderr handler (WARNING and above)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.addFilter(StderrFilter())
    stderr_handler.addFilter(ContextFilter())
    stderr_handler.setFormatter(formatter)

    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(stderr_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)


def set_request_context(
    user_id: str | None = None,
    client_id: str | None = None,
    **extra: Any,
) -> None:
    """Set the current request context for logging.

    Args:
        user_id: Authenticated user ID
        client_id: OAuth2 client ID
        **extra: Additional context values
    """
    ctx = {
        "user_id": user_id or "-",
        "client_id": client_id or "-",
        **extra,
    }
    request_context.set(ctx)


def clear_request_context() -> None:
    """Clear the current request context."""
    request_context.set({})
