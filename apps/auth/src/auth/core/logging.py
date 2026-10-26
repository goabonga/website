# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Structured logging configuration with dual output streams.

Configures logging to send INFO/DEBUG to stdout and WARNING/ERROR/CRITICAL to stderr.
This allows systemd to capture logs appropriately:
- StandardOutput -> output.log (info, debug)
- StandardError -> error.log (warning, error, critical)

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
        record.user_id = ctx.get("user_id", "-")
        record.client_id = ctx.get("client_id", "-")
        return True


class StdoutFilter(logging.Filter):
    """Filter that only allows INFO and DEBUG level records."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= logging.INFO


class StderrFilter(logging.Filter):
    """Filter that only allows WARNING, ERROR and CRITICAL level records."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.WARNING


def setup_logging(level: str = "INFO") -> None:
    """Configure logging with dual output streams and request context.

    Args:
        level: Minimum logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Format with user context
    formatter = logging.Formatter(
        fmt=(
            "%(asctime)s | %(levelname)-8s | "
            "user=%(user_id)s | client=%(client_id)s | "
            "%(name)s | %(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Stdout handler for INFO and DEBUG
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.addFilter(StdoutFilter())
    stdout_handler.addFilter(ContextFilter())
    stdout_handler.setFormatter(formatter)

    # Stderr handler for WARNING, ERROR, CRITICAL
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.addFilter(StderrFilter())
    stderr_handler.addFilter(ContextFilter())
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


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
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


def log_action(
    logger: logging.Logger,
    action: str,
    user_id: str | None = None,
    client_id: str | None = None,
    **details: Any,
) -> None:
    """Log an action with user context.

    Args:
        logger: Logger instance
        action: Action being performed
        user_id: User ID (uses context if not provided)
        client_id: Client ID (uses context if not provided)
        **details: Additional details to log
    """
    ctx = request_context.get() or {}
    uid = user_id or ctx.get("user_id", "-")
    cid = client_id or ctx.get("client_id", "-")

    detail_str = " | ".join(f"{k}={v}" for k, v in details.items()) if details else ""
    message = f"ACTION: {action}"
    if detail_str:
        message = f"{message} | {detail_str}"

    # Temporarily set context if provided
    if user_id or client_id:
        set_request_context(user_id=uid, client_id=cid)

    logger.info(message)
