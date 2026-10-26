# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/logging.py."""

import logging
from unittest.mock import patch

from custom_domain.logging import (
    StderrFilter,
    StdoutFilter,
    clear_request_context,
    get_logger,
    set_request_context,
    setup_logging,
)


class TestStdoutFilter:
    """Tests for StdoutFilter."""

    def test_allows_debug(self):
        """Test allows DEBUG level."""
        filter = StdoutFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )
        assert filter.filter(record) is True

    def test_allows_info(self):
        """Test allows INFO level."""
        filter = StdoutFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )
        assert filter.filter(record) is True

    def test_blocks_warning(self):
        """Test blocks WARNING level."""
        filter = StdoutFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )
        assert filter.filter(record) is False

    def test_blocks_error(self):
        """Test blocks ERROR level."""
        filter = StdoutFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )
        assert filter.filter(record) is False


class TestStderrFilter:
    """Tests for StderrFilter."""

    def test_blocks_debug(self):
        """Test blocks DEBUG level."""
        filter = StderrFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )
        assert filter.filter(record) is False

    def test_blocks_info(self):
        """Test blocks INFO level."""
        filter = StderrFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )
        assert filter.filter(record) is False

    def test_allows_warning(self):
        """Test allows WARNING level."""
        filter = StderrFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )
        assert filter.filter(record) is True

    def test_allows_error(self):
        """Test allows ERROR level."""
        filter = StderrFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )
        assert filter.filter(record) is True

    def test_allows_critical(self):
        """Test allows CRITICAL level."""
        filter = StderrFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.CRITICAL,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )
        assert filter.filter(record) is True


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_setup_logging_default_level(self):
        """Test setup with default level."""
        with patch("custom_domain.logging.settings") as mock_settings:
            mock_settings.log_level = "INFO"

            setup_logging()

            root = logging.getLogger()
            assert len(root.handlers) == 2

    def test_setup_logging_debug_mode(self):
        """Test setup in debug mode."""
        with patch("custom_domain.logging.settings") as mock_settings:
            mock_settings.log_level = "DEBUG"

            setup_logging()

            root = logging.getLogger()
            assert root.level == logging.DEBUG

    def test_setup_logging_custom_level(self):
        """Test setup with custom level."""
        with patch("custom_domain.logging.settings") as mock_settings:
            mock_settings.log_level = "INFO"

            setup_logging(level="WARNING")

            root = logging.getLogger()
            assert root.level == logging.WARNING


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_returns_logger(self):
        """Test get_logger returns a logger instance."""
        logger = get_logger("test.module")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.module"

    def test_get_logger_same_name_returns_same_logger(self):
        """Test same name returns same logger."""
        logger1 = get_logger("test.same")
        logger2 = get_logger("test.same")
        assert logger1 is logger2


class TestRequestContext:
    """Tests for request context functions."""

    def test_clear_request_context(self):
        """Test clear_request_context resets context to empty dict."""
        set_request_context(request_id="abc123")
        clear_request_context()
        # After clearing, set_request_context should start from empty
        set_request_context(key="value")
        from custom_domain.logging import _request_context

        assert _request_context.get() == {"key": "value"}
