# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for mailler.logging module."""

import logging

from mailler.logging import (
    StderrFilter,
    StdoutFilter,
    clear_request_context,
    get_logger,
    request_context,
    setup_logging,
)


class TestStdoutFilter:
    """Tests for StdoutFilter."""

    def test_allows_debug(self):
        f = StdoutFilter()
        record = logging.LogRecord("test", logging.DEBUG, "", 0, "msg", (), None)
        assert f.filter(record) is True

    def test_allows_info(self):
        f = StdoutFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        assert f.filter(record) is True

    def test_blocks_warning(self):
        f = StdoutFilter()
        record = logging.LogRecord("test", logging.WARNING, "", 0, "msg", (), None)
        assert f.filter(record) is False

    def test_blocks_error(self):
        f = StdoutFilter()
        record = logging.LogRecord("test", logging.ERROR, "", 0, "msg", (), None)
        assert f.filter(record) is False

    def test_blocks_critical(self):
        f = StdoutFilter()
        record = logging.LogRecord("test", logging.CRITICAL, "", 0, "msg", (), None)
        assert f.filter(record) is False


class TestStderrFilter:
    """Tests for StderrFilter."""

    def test_blocks_debug(self):
        f = StderrFilter()
        record = logging.LogRecord("test", logging.DEBUG, "", 0, "msg", (), None)
        assert f.filter(record) is False

    def test_blocks_info(self):
        f = StderrFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        assert f.filter(record) is False

    def test_allows_warning(self):
        f = StderrFilter()
        record = logging.LogRecord("test", logging.WARNING, "", 0, "msg", (), None)
        assert f.filter(record) is True

    def test_allows_error(self):
        f = StderrFilter()
        record = logging.LogRecord("test", logging.ERROR, "", 0, "msg", (), None)
        assert f.filter(record) is True

    def test_allows_critical(self):
        f = StderrFilter()
        record = logging.LogRecord("test", logging.CRITICAL, "", 0, "msg", (), None)
        assert f.filter(record) is True


class TestSetupLogging:
    """Tests for setup_logging."""

    def test_sets_root_logger_level(self):
        setup_logging("DEBUG")
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_creates_two_handlers(self):
        setup_logging("INFO")
        root = logging.getLogger()
        assert len(root.handlers) == 2

    def test_reduces_third_party_noise(self):
        setup_logging("DEBUG")
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING
        assert logging.getLogger("uvicorn.access").level == logging.WARNING

    def test_invalid_level_defaults_to_info(self):
        setup_logging("INVALID")
        root = logging.getLogger()
        assert root.level == logging.INFO


class TestGetLogger:
    """Tests for get_logger."""

    def test_returns_named_logger(self):
        logger = get_logger("test.module")
        assert logger.name == "test.module"
        assert isinstance(logger, logging.Logger)


class TestClearRequestContext:
    """Tests for clear_request_context."""

    def test_clears_context(self):
        request_context.set({"user_id": "u1", "client_id": "c1"})
        clear_request_context()
        assert request_context.get() == {}
