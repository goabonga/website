# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Logging configuration with dual-stream output and request context."""

import logging
import sys
from contextvars import ContextVar
from typing import Any

# Context variables for request-scoped logging
request_context: ContextVar[dict[str, Any] | None] = ContextVar("request_context", default=None)


class ContextFilter(logging.Filter):
    """Add request context to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = request_context.get() or {}
        record.user_id = ctx.get("user_id", "-")  # type: ignore[attr-defined]
        record.client_id = ctx.get("client_id", "-")  # type: ignore[attr-defined]
        return True


class StdoutFilter(logging.Filter):
    """Allow DEBUG/INFO only."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= logging.INFO


class StderrFilter(logging.Filter):
    """Allow WARNING+ only."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.WARNING


def setup_logging(level: str = "INFO") -> None:
    """Configure dual-stream logging (stdout for info, stderr for errors)."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | user=%(user_id)s | client=%(client_id)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.addFilter(StdoutFilter())
    stdout_handler.addFilter(ContextFilter())
    stdout_handler.setFormatter(formatter)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.addFilter(StderrFilter())
    stderr_handler.addFilter(ContextFilter())
    stderr_handler.setFormatter(formatter)

    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(stderr_handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get named logger."""
    return logging.getLogger(name)


def set_request_context(
    user_id: str | None = None,
    client_id: str | None = None,
    **extra: Any,
) -> None:
    """Set request context for structured logs."""
    ctx = {"user_id": user_id or "-", "client_id": client_id or "-", **extra}
    request_context.set(ctx)


def clear_request_context() -> None:
    """Clear request context."""
    request_context.set({})
