# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for mta_sts.logging module."""

import logging

from mta_sts.logging import StderrFilter, StdoutFilter, get_logger, setup_logging


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
    """Tests for setup_logging function."""

    def test_configures_root_logger_level(self):
        setup_logging(level="DEBUG")
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_configures_two_handlers(self):
        setup_logging(level="INFO")
        root = logging.getLogger()
        assert len(root.handlers) == 2

    def test_clears_existing_handlers(self):
        root = logging.getLogger()
        root.addHandler(logging.StreamHandler())
        root.addHandler(logging.StreamHandler())
        setup_logging(level="INFO")
        assert len(root.handlers) == 2

    def test_invalid_level_defaults_to_info(self):
        setup_logging(level="INVALID")
        root = logging.getLogger()
        assert root.level == logging.INFO

    def test_third_party_loggers_set_to_warning(self):
        setup_logging(level="DEBUG")
        assert logging.getLogger("urllib3").level == logging.WARNING
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING


class TestGetLogger:
    """Tests for get_logger function."""

    def test_returns_logger_with_name(self):
        logger = get_logger("test.module")
        assert logger.name == "test.module"
        assert isinstance(logger, logging.Logger)

    def test_returns_same_logger_for_same_name(self):
        logger1 = get_logger("same.name")
        logger2 = get_logger("same.name")
        assert logger1 is logger2
