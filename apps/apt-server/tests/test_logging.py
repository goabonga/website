# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Dual-stream logging with request context."""

import logging

import pytest
from apt_server.logging import (
    ContextFilter,
    StderrFilter,
    StdoutFilter,
    clear_request_context,
    get_logger,
    set_request_context,
    setup_logging,
)


def record(level: int) -> logging.LogRecord:
    return logging.LogRecord("test", level, __file__, 1, "message", None, None)


@pytest.fixture(autouse=True)
def restore_root_logger():
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)
    clear_request_context()


def test_stdout_filter_keeps_info_and_below() -> None:
    assert StdoutFilter().filter(record(logging.DEBUG))
    assert StdoutFilter().filter(record(logging.INFO))
    assert not StdoutFilter().filter(record(logging.WARNING))


def test_stderr_filter_keeps_warning_and_above() -> None:
    assert not StderrFilter().filter(record(logging.INFO))
    assert StderrFilter().filter(record(logging.WARNING))
    assert StderrFilter().filter(record(logging.ERROR))


def test_context_filter_defaults_to_dash() -> None:
    rec = record(logging.INFO)

    ContextFilter().filter(rec)

    assert rec.user_id == "-"  # type: ignore[attr-defined]
    assert rec.client_id == "-"  # type: ignore[attr-defined]


def test_context_filter_uses_request_context() -> None:
    set_request_context(user_id="u1", client_id="c1")
    rec = record(logging.INFO)

    ContextFilter().filter(rec)

    assert rec.user_id == "u1"  # type: ignore[attr-defined]
    assert rec.client_id == "c1"  # type: ignore[attr-defined]


def test_setup_logging_installs_two_handlers_and_level() -> None:
    setup_logging("debug")

    root = logging.getLogger()
    assert len(root.handlers) == 2
    assert root.level == logging.DEBUG


def test_setup_logging_falls_back_to_info_on_unknown_level() -> None:
    setup_logging("nonsense")

    assert logging.getLogger().level == logging.INFO


def test_setup_logging_splits_streams(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging("INFO")
    logger = get_logger("apt_server.test")

    logger.info("hello info")
    logger.error("hello error")

    captured = capsys.readouterr()
    assert "hello info" in captured.out
    assert "hello info" not in captured.err
    assert "hello error" in captured.err
    assert "hello error" not in captured.out
