# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for backend.logging module."""

import logging
from unittest.mock import MagicMock

from backend.logging import (
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


class TestStdoutFilter:
    """Tests for StdoutFilter (allows INFO and DEBUG, blocks WARNING+)."""

    def test_allows_debug(self) -> None:
        """DEBUG records pass through StdoutFilter."""
        f = StdoutFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="debug msg",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is True

    def test_allows_info(self) -> None:
        """INFO records pass through StdoutFilter."""
        f = StdoutFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="info msg",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is True

    def test_blocks_warning(self) -> None:
        """WARNING records are blocked by StdoutFilter."""
        f = StdoutFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="warning msg",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is False

    def test_blocks_error(self) -> None:
        """ERROR records are blocked by StdoutFilter."""
        f = StdoutFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="error msg",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is False

    def test_blocks_critical(self) -> None:
        """CRITICAL records are blocked by StdoutFilter."""
        f = StdoutFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.CRITICAL,
            pathname="",
            lineno=0,
            msg="critical msg",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is False


class TestStderrFilter:
    """Tests for StderrFilter (allows WARNING+, blocks INFO and DEBUG)."""

    def test_blocks_debug(self) -> None:
        """DEBUG records are blocked by StderrFilter."""
        f = StderrFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="debug msg",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is False

    def test_blocks_info(self) -> None:
        """INFO records are blocked by StderrFilter."""
        f = StderrFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="info msg",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is False

    def test_allows_warning(self) -> None:
        """WARNING records pass through StderrFilter."""
        f = StderrFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="warning msg",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is True

    def test_allows_error(self) -> None:
        """ERROR records pass through StderrFilter."""
        f = StderrFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="error msg",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is True

    def test_allows_critical(self) -> None:
        """CRITICAL records pass through StderrFilter."""
        f = StderrFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.CRITICAL,
            pathname="",
            lineno=0,
            msg="critical msg",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is True


class TestContextFilter:
    """Tests for ContextFilter (adds user_id and client_id to record)."""

    def test_adds_user_id_and_client_id_from_context(self) -> None:
        """ContextFilter enriches the record with user_id and client_id from context."""
        set_request_context(user_id="user-42", client_id="client-7")
        try:
            f = ContextFilter()
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg="msg",
                args=(),
                exc_info=None,
            )
            result = f.filter(record)
            assert result is True
            assert record.user_id == "user-42"
            assert record.client_id == "client-7"
        finally:
            clear_request_context()

    def test_defaults_to_dash_when_context_empty(self) -> None:
        """ContextFilter sets user_id and client_id to '-' when context is empty."""
        clear_request_context()
        f = ContextFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="msg",
            args=(),
            exc_info=None,
        )
        f.filter(record)
        assert record.user_id == "-"
        assert record.client_id == "-"


class TestGetLogger:
    """Tests for get_logger."""

    def test_returns_logger_with_given_name(self) -> None:
        """get_logger returns a logging.Logger with the specified name."""
        logger = get_logger("my.module")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "my.module"

    def test_returns_same_logger_for_same_name(self) -> None:
        """get_logger returns the same instance for repeated calls."""
        logger1 = get_logger("duplicate.name")
        logger2 = get_logger("duplicate.name")
        assert logger1 is logger2


class TestSetRequestContext:
    """Tests for set_request_context."""

    def test_sets_user_id_and_client_id(self) -> None:
        """set_request_context stores user_id and client_id in the context var."""
        set_request_context(user_id="u1", client_id="c1")
        try:
            ctx = request_context.get()
            assert ctx["user_id"] == "u1"
            assert ctx["client_id"] == "c1"
        finally:
            clear_request_context()

    def test_defaults_to_dash_when_none(self) -> None:
        """set_request_context uses '-' when user_id or client_id is None."""
        set_request_context(user_id=None, client_id=None)
        try:
            ctx = request_context.get()
            assert ctx["user_id"] == "-"
            assert ctx["client_id"] == "-"
        finally:
            clear_request_context()

    def test_stores_extra_kwargs(self) -> None:
        """set_request_context stores additional keyword arguments."""
        set_request_context(user_id="u1", client_id="c1", request_id="r1")
        try:
            ctx = request_context.get()
            assert ctx["request_id"] == "r1"
        finally:
            clear_request_context()


class TestClearRequestContext:
    """Tests for clear_request_context."""

    def test_clears_context(self) -> None:
        """clear_request_context resets the context to an empty dict."""
        set_request_context(user_id="u1", client_id="c1")
        clear_request_context()
        ctx = request_context.get()
        assert ctx == {}


class TestSetupLogging:
    """Tests for setup_logging."""

    def test_configures_root_logger_handlers(self) -> None:
        """setup_logging adds exactly two handlers to the root logger."""
        setup_logging(level="INFO")
        root = logging.getLogger()
        assert len(root.handlers) == 2

    def test_sets_root_logger_level(self) -> None:
        """setup_logging sets the root logger level correctly."""
        setup_logging(level="DEBUG")
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_sets_warning_level(self) -> None:
        """setup_logging with WARNING level configures root logger at WARNING."""
        setup_logging(level="WARNING")
        root = logging.getLogger()
        assert root.level == logging.WARNING

    def test_stdout_handler_has_stdout_filter(self) -> None:
        """The first handler (stdout) has a StdoutFilter attached."""
        setup_logging(level="INFO")
        root = logging.getLogger()
        stdout_handler = root.handlers[0]
        filter_types = [type(f) for f in stdout_handler.filters]
        assert StdoutFilter in filter_types

    def test_stderr_handler_has_stderr_filter(self) -> None:
        """The second handler (stderr) has a StderrFilter attached."""
        setup_logging(level="INFO")
        root = logging.getLogger()
        stderr_handler = root.handlers[1]
        filter_types = [type(f) for f in stderr_handler.filters]
        assert StderrFilter in filter_types

    def test_third_party_loggers_suppressed(self) -> None:
        """setup_logging raises third-party logger levels to WARNING."""
        setup_logging(level="DEBUG")
        assert logging.getLogger("urllib3").level == logging.WARNING
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING


class TestLogAction:
    """Tests for log_action."""

    def test_logs_action_message(self) -> None:
        """log_action calls logger.info with the action in the message."""
        logger = MagicMock(spec=logging.Logger)
        log_action(logger, "user.login")
        logger.info.assert_called_once()
        message = logger.info.call_args[0][0]
        assert "ACTION: user.login" in message

    def test_logs_action_with_details(self) -> None:
        """log_action includes extra details in the message."""
        logger = MagicMock(spec=logging.Logger)
        log_action(logger, "file.upload", size=1024, filename="test.txt")
        logger.info.assert_called_once()
        message = logger.info.call_args[0][0]
        assert "ACTION: file.upload" in message
        assert "size=1024" in message
        assert "filename=test.txt" in message

    def test_sets_context_when_user_id_provided(self) -> None:
        """log_action sets request context when user_id is explicitly passed."""
        logger = MagicMock(spec=logging.Logger)
        clear_request_context()
        log_action(logger, "admin.action", user_id="admin-1")
        ctx = request_context.get()
        assert ctx["user_id"] == "admin-1"
        clear_request_context()

    def test_sets_context_when_client_id_provided(self) -> None:
        """log_action sets request context when client_id is explicitly passed."""
        logger = MagicMock(spec=logging.Logger)
        clear_request_context()
        log_action(logger, "api.call", client_id="service-x")
        ctx = request_context.get()
        assert ctx["client_id"] == "service-x"
        clear_request_context()

    def test_uses_existing_context_when_no_ids_provided(self) -> None:
        """log_action uses the existing request context when no user_id/client_id."""
        set_request_context(user_id="ctx-user", client_id="ctx-client")
        try:
            logger = MagicMock(spec=logging.Logger)
            log_action(logger, "some.action")
            logger.info.assert_called_once()
            message = logger.info.call_args[0][0]
            assert "ACTION: some.action" in message
        finally:
            clear_request_context()
