# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for team/logging.py."""

import logging

from team.logging import (
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

    def test_adds_default_context_values(self):
        """Should add default '-' values when no context is set."""
        clear_request_context()
        f = ContextFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test message",
            args=(),
            exc_info=None,
        )

        result = f.filter(record)

        assert result is True
        assert record.user_id == "-"
        assert record.client_id == "-"
        assert record.saas_id == "-"

    def test_adds_context_from_context_var(self):
        """Should add values from the request context ContextVar."""
        set_request_context(
            user_id="user-123",
            client_id="client-456",
            saas_id="saas-789",
        )
        f = ContextFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test message",
            args=(),
            exc_info=None,
        )

        result = f.filter(record)

        assert result is True
        assert record.user_id == "user-123"
        assert record.client_id == "client-456"
        assert record.saas_id == "saas-789"
        clear_request_context()

    def test_always_returns_true(self):
        """Filter should always return True (never suppress records)."""
        clear_request_context()
        f = ContextFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="error",
            args=(),
            exc_info=None,
        )

        assert f.filter(record) is True


class TestStdoutFilter:
    """Tests for StdoutFilter."""

    def test_allows_debug(self):
        """Should allow DEBUG level records."""
        f = StdoutFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="debug",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is True

    def test_allows_info(self):
        """Should allow INFO level records."""
        f = StdoutFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="info",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is True

    def test_blocks_warning(self):
        """Should block WARNING level records."""
        f = StdoutFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="warning",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is False

    def test_blocks_error(self):
        """Should block ERROR level records."""
        f = StdoutFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="error",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is False

    def test_blocks_critical(self):
        """Should block CRITICAL level records."""
        f = StdoutFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.CRITICAL,
            pathname="",
            lineno=0,
            msg="critical",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is False


class TestStderrFilter:
    """Tests for StderrFilter."""

    def test_blocks_debug(self):
        """Should block DEBUG level records."""
        f = StderrFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="debug",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is False

    def test_blocks_info(self):
        """Should block INFO level records."""
        f = StderrFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="info",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is False

    def test_allows_warning(self):
        """Should allow WARNING level records."""
        f = StderrFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="warning",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is True

    def test_allows_error(self):
        """Should allow ERROR level records."""
        f = StderrFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="error",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is True

    def test_allows_critical(self):
        """Should allow CRITICAL level records."""
        f = StderrFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.CRITICAL,
            pathname="",
            lineno=0,
            msg="critical",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is True


class TestSetupLogging:
    """Tests for setup_logging()."""

    def test_configures_root_logger_with_two_handlers(self):
        """Should configure root logger with stdout and stderr handlers."""
        setup_logging("INFO")
        root = logging.getLogger()

        assert len(root.handlers) == 2
        assert root.level == logging.INFO

    def test_sets_log_level_debug(self):
        """Should set log level to DEBUG when specified."""
        setup_logging("DEBUG")
        root = logging.getLogger()

        assert root.level == logging.DEBUG

    def test_sets_log_level_warning(self):
        """Should set log level to WARNING when specified."""
        setup_logging("WARNING")
        root = logging.getLogger()

        assert root.level == logging.WARNING

    def test_invalid_level_defaults_to_info(self):
        """Should default to INFO when an invalid level string is provided."""
        setup_logging("INVALID_LEVEL")
        root = logging.getLogger()

        assert root.level == logging.INFO

    def test_handlers_have_correct_filters(self):
        """Each handler should have the correct filters attached."""
        setup_logging("INFO")
        root = logging.getLogger()

        stdout_handler = root.handlers[0]
        stderr_handler = root.handlers[1]

        # stdout handler should have StdoutFilter and ContextFilter
        stdout_filter_types = [type(f) for f in stdout_handler.filters]
        assert StdoutFilter in stdout_filter_types
        assert ContextFilter in stdout_filter_types

        # stderr handler should have StderrFilter and ContextFilter
        stderr_filter_types = [type(f) for f in stderr_handler.filters]
        assert StderrFilter in stderr_filter_types
        assert ContextFilter in stderr_filter_types

    def test_clears_existing_handlers(self):
        """Should clear any pre-existing handlers on root logger."""
        root = logging.getLogger()
        # Add a dummy handler
        dummy = logging.StreamHandler()
        root.addHandler(dummy)

        setup_logging("INFO")

        # After setup, should have exactly 2 handlers (not initial_count + 2)
        assert len(root.handlers) == 2

    def test_reduces_third_party_noise(self):
        """Should set third-party loggers to WARNING level."""
        setup_logging("DEBUG")

        assert logging.getLogger("urllib3").level == logging.WARNING
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING
        assert logging.getLogger("stripe").level == logging.WARNING


class TestSetRequestContext:
    """Tests for set_request_context()."""

    def test_sets_all_context_values(self):
        """Should set user_id, client_id, and saas_id in context."""
        set_request_context(
            user_id="u1",
            client_id="c1",
            saas_id="s1",
        )
        ctx = request_context.get()

        assert ctx["user_id"] == "u1"
        assert ctx["client_id"] == "c1"
        assert ctx["saas_id"] == "s1"
        clear_request_context()

    def test_none_values_become_dash(self):
        """Should replace None values with '-'."""
        set_request_context(user_id=None, client_id=None, saas_id=None)
        ctx = request_context.get()

        assert ctx["user_id"] == "-"
        assert ctx["client_id"] == "-"
        assert ctx["saas_id"] == "-"
        clear_request_context()

    def test_extra_kwargs_are_included(self):
        """Should include extra keyword arguments in context."""
        set_request_context(user_id="u1", extra_key="extra_value")
        ctx = request_context.get()

        assert ctx["extra_key"] == "extra_value"
        clear_request_context()


class TestClearRequestContext:
    """Tests for clear_request_context()."""

    def test_clears_context_to_empty_dict(self):
        """Should reset context to an empty dict."""
        set_request_context(user_id="u1", client_id="c1", saas_id="s1")
        clear_request_context()
        ctx = request_context.get()

        assert ctx == {}


class TestGetLogger:
    """Tests for get_logger()."""

    def test_returns_named_logger(self):
        """Should return a logger with the given name."""
        logger = get_logger("my.module")

        assert isinstance(logger, logging.Logger)
        assert logger.name == "my.module"

    def test_returns_same_logger_for_same_name(self):
        """Should return the same logger instance for the same name."""
        logger1 = get_logger("same.name")
        logger2 = get_logger("same.name")

        assert logger1 is logger2


class TestLogAction:
    """Tests for log_action()."""

    def test_logs_action_message(self, caplog):
        """Should log a message containing the action name."""
        logger = get_logger("test.log_action")

        with caplog.at_level(logging.INFO, logger="test.log_action"):
            log_action(logger, "create_user")

        assert any("ACTION: create_user" in r.message for r in caplog.records)

    def test_logs_action_with_details(self, caplog):
        """Should include detail key=value pairs in the log message."""
        logger = get_logger("test.log_action_details")

        with caplog.at_level(logging.INFO, logger="test.log_action_details"):
            log_action(logger, "update_plan", plan_id="plan-1", amount=100)

        assert any("plan_id=plan-1" in r.message for r in caplog.records)
        assert any("amount=100" in r.message for r in caplog.records)

    def test_sets_context_when_user_id_provided(self):
        """Should update request context when user_id is explicitly provided."""
        clear_request_context()
        setup_logging("INFO")
        logger = get_logger("test.log_action_context")

        log_action(logger, "test_action", user_id="user-override")
        ctx = request_context.get()

        assert ctx["user_id"] == "user-override"
        clear_request_context()

    def test_uses_existing_context_when_no_override(self, caplog):
        """Should use existing context values when none are explicitly provided."""
        set_request_context(user_id="ctx-user", client_id="ctx-client", saas_id="ctx-saas")
        logger = get_logger("test.log_action_no_override")

        with caplog.at_level(logging.INFO, logger="test.log_action_no_override"):
            log_action(logger, "read_data")

        assert any("ACTION: read_data" in r.message for r in caplog.records)
        clear_request_context()

    def test_log_action_without_details(self, caplog):
        """Should log action without detail separator when no details are given."""
        logger = get_logger("test.log_action_no_details")

        with caplog.at_level(logging.INFO, logger="test.log_action_no_details"):
            log_action(logger, "simple_action")

        matching = [r for r in caplog.records if "ACTION: simple_action" in r.message]
        assert len(matching) == 1
        # No " | " separator for details
        assert " | " not in matching[0].message.replace("ACTION: simple_action", "")
