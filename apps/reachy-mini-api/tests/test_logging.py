# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for reachy_mini_api/logging.py."""

import logging
from unittest.mock import MagicMock

from reachy_mini_api.logging import (
    ContextFilter,
    StderrFilter,
    StdoutFilter,
    clear_request_context,
    get_logger,
    log_action,
    request_context,
    set_request_context,
    setup_logging,
)


class TestContextFilter:
    """Tests for ContextFilter."""

    def test_adds_default_context(self):
        """Add default context values when no context is set."""
        clear_request_context()
        f = ContextFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        result = f.filter(record)
        assert result is True
        assert record.user_id == "-"
        assert record.client_id == "-"

    def test_adds_context_from_request(self):
        """Add context values from request context."""
        set_request_context(user_id="user1", client_id="client1")
        f = ContextFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        result = f.filter(record)
        assert result is True
        assert record.user_id == "user1"
        assert record.client_id == "client1"
        clear_request_context()


class TestStdoutFilter:
    """Tests for StdoutFilter."""

    def test_allows_debug(self):
        """Allow DEBUG level messages."""
        f = StdoutFilter()
        record = logging.LogRecord("test", logging.DEBUG, "", 0, "msg", (), None)
        assert f.filter(record) is True

    def test_allows_info(self):
        """Allow INFO level messages."""
        f = StdoutFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        assert f.filter(record) is True

    def test_blocks_warning(self):
        """Block WARNING level messages."""
        f = StdoutFilter()
        record = logging.LogRecord("test", logging.WARNING, "", 0, "msg", (), None)
        assert f.filter(record) is False

    def test_blocks_error(self):
        """Block ERROR level messages."""
        f = StdoutFilter()
        record = logging.LogRecord("test", logging.ERROR, "", 0, "msg", (), None)
        assert f.filter(record) is False

    def test_blocks_critical(self):
        """Block CRITICAL level messages."""
        f = StdoutFilter()
        record = logging.LogRecord("test", logging.CRITICAL, "", 0, "msg", (), None)
        assert f.filter(record) is False


class TestStderrFilter:
    """Tests for StderrFilter."""

    def test_blocks_debug(self):
        """Block DEBUG level messages."""
        f = StderrFilter()
        record = logging.LogRecord("test", logging.DEBUG, "", 0, "msg", (), None)
        assert f.filter(record) is False

    def test_blocks_info(self):
        """Block INFO level messages."""
        f = StderrFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        assert f.filter(record) is False

    def test_allows_warning(self):
        """Allow WARNING level messages."""
        f = StderrFilter()
        record = logging.LogRecord("test", logging.WARNING, "", 0, "msg", (), None)
        assert f.filter(record) is True

    def test_allows_error(self):
        """Allow ERROR level messages."""
        f = StderrFilter()
        record = logging.LogRecord("test", logging.ERROR, "", 0, "msg", (), None)
        assert f.filter(record) is True

    def test_allows_critical(self):
        """Allow CRITICAL level messages."""
        f = StderrFilter()
        record = logging.LogRecord("test", logging.CRITICAL, "", 0, "msg", (), None)
        assert f.filter(record) is True


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_configures_root_logger(self):
        """Configure root logger with correct level and handlers."""
        setup_logging(level="DEBUG")
        root = logging.getLogger()
        assert root.level == logging.DEBUG
        assert len(root.handlers) == 2

    def test_configures_info_level(self):
        """Configure with INFO level."""
        setup_logging(level="INFO")
        root = logging.getLogger()
        assert root.level == logging.INFO

    def test_reduces_third_party_noise(self):
        """Set third-party loggers to WARNING."""
        setup_logging()
        assert logging.getLogger("urllib3").level == logging.WARNING
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING

    def test_invalid_level_defaults_to_info(self):
        """Default to INFO when invalid level is provided."""
        setup_logging(level="INVALID")
        root = logging.getLogger()
        assert root.level == logging.INFO


class TestGetLogger:
    """Tests for get_logger function."""

    def test_returns_logger(self):
        """Return a logger instance."""
        logger = get_logger("test.module")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.module"


class TestRequestContext:
    """Tests for set_request_context and clear_request_context."""

    def test_set_context(self):
        """Set request context variables."""
        set_request_context(user_id="user1", client_id="client1")
        ctx = request_context.get()
        assert ctx["user_id"] == "user1"
        assert ctx["client_id"] == "client1"
        clear_request_context()

    def test_set_context_with_none(self):
        """Set context with None values defaults to dash."""
        set_request_context(user_id=None, client_id=None)
        ctx = request_context.get()
        assert ctx["user_id"] == "-"
        assert ctx["client_id"] == "-"
        clear_request_context()

    def test_set_context_with_extra(self):
        """Set context with extra key-value pairs."""
        set_request_context(user_id="u1", client_id="c1", request_id="req123")
        ctx = request_context.get()
        assert ctx["request_id"] == "req123"
        clear_request_context()

    def test_clear_context(self):
        """Clear request context."""
        set_request_context(user_id="user1")
        clear_request_context()
        ctx = request_context.get()
        assert ctx == {}


class TestLogAction:
    """Tests for log_action function."""

    def test_log_action_basic(self):
        """Log action with basic parameters."""
        mock_logger = MagicMock()
        clear_request_context()
        log_action(mock_logger, "test_action")
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        assert "ACTION: test_action" in call_args

    def test_log_action_with_details(self):
        """Log action with additional details."""
        mock_logger = MagicMock()
        clear_request_context()
        log_action(mock_logger, "test_action", key1="val1", key2="val2")
        call_args = mock_logger.info.call_args[0][0]
        assert "key1=val1" in call_args
        assert "key2=val2" in call_args

    def test_log_action_with_user_context(self):
        """Log action sets request context when user_id provided."""
        mock_logger = MagicMock()
        clear_request_context()
        log_action(mock_logger, "test_action", user_id="user1", client_id="client1")
        mock_logger.info.assert_called_once()
        ctx = request_context.get()
        assert ctx["user_id"] == "user1"
        assert ctx["client_id"] == "client1"
        clear_request_context()

    def test_log_action_uses_existing_context(self):
        """Log action uses existing context when no user_id/client_id provided."""
        mock_logger = MagicMock()
        set_request_context(user_id="ctx_user", client_id="ctx_client")
        log_action(mock_logger, "test_action")
        mock_logger.info.assert_called_once()
        clear_request_context()

    def test_log_action_no_details(self):
        """Log action with no extra details omits detail string."""
        mock_logger = MagicMock()
        clear_request_context()
        log_action(mock_logger, "simple_action")
        call_args = mock_logger.info.call_args[0][0]
        assert call_args == "ACTION: simple_action"
        clear_request_context()
