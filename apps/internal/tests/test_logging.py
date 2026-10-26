# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for logging filters, context management, and log_action."""

import logging

from internal.logging import (
    ContextFilter,
    StderrFilter,
    StdoutFilter,
    clear_request_context,
    log_action,
    request_context,
    set_request_context,
)


class TestContextFilter:
    def test_adds_context_values(self):
        token = request_context.set({"user_id": "user-123", "client_id": "client-456"})
        try:
            f = ContextFilter()
            record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
            result = f.filter(record)
            assert result is True
            assert record.user_id == "user-123"  # type: ignore[attr-defined]
            assert record.client_id == "client-456"  # type: ignore[attr-defined]
        finally:
            request_context.reset(token)

    def test_defaults_without_context(self):
        token = request_context.set(None)
        try:
            f = ContextFilter()
            record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
            f.filter(record)
            assert record.user_id == "-"  # type: ignore[attr-defined]
            assert record.client_id == "-"  # type: ignore[attr-defined]
        finally:
            request_context.reset(token)


class TestStdoutFilter:
    def test_allows_info(self):
        f = StdoutFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        assert f.filter(record) is True

    def test_allows_debug(self):
        f = StdoutFilter()
        record = logging.LogRecord("test", logging.DEBUG, "", 0, "msg", (), None)
        assert f.filter(record) is True

    def test_blocks_warning(self):
        f = StdoutFilter()
        record = logging.LogRecord("test", logging.WARNING, "", 0, "msg", (), None)
        assert f.filter(record) is False

    def test_blocks_error(self):
        f = StdoutFilter()
        record = logging.LogRecord("test", logging.ERROR, "", 0, "msg", (), None)
        assert f.filter(record) is False


class TestStderrFilter:
    def test_allows_warning(self):
        f = StderrFilter()
        record = logging.LogRecord("test", logging.WARNING, "", 0, "msg", (), None)
        assert f.filter(record) is True

    def test_allows_error(self):
        f = StderrFilter()
        record = logging.LogRecord("test", logging.ERROR, "", 0, "msg", (), None)
        assert f.filter(record) is True

    def test_blocks_info(self):
        f = StderrFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        assert f.filter(record) is False

    def test_blocks_debug(self):
        f = StderrFilter()
        record = logging.LogRecord("test", logging.DEBUG, "", 0, "msg", (), None)
        assert f.filter(record) is False


class TestSetRequestContext:
    def test_sets_context(self):
        set_request_context(user_id="u1", client_id="c1")
        ctx = request_context.get()
        assert ctx == {"user_id": "u1", "client_id": "c1"}
        clear_request_context()

    def test_defaults_to_dash(self):
        set_request_context()
        ctx = request_context.get()
        assert ctx == {"user_id": "-", "client_id": "-"}
        clear_request_context()

    def test_extra_kwargs(self):
        set_request_context(user_id="u1", client_id="c1", custom="val")
        ctx = request_context.get()
        assert ctx["custom"] == "val"
        clear_request_context()


class TestClearRequestContext:
    def test_clears_context(self):
        set_request_context(user_id="u1", client_id="c1")
        clear_request_context()
        ctx = request_context.get()
        assert ctx == {}


class TestLogAction:
    def test_log_action_basic(self, caplog):
        logger = logging.getLogger("test.log_action")
        logger.addFilter(ContextFilter())
        with caplog.at_level(logging.INFO, logger="test.log_action"):
            log_action(logger, "test_action")
        assert "ACTION: test_action" in caplog.text

    def test_log_action_with_details(self, caplog):
        logger = logging.getLogger("test.log_action_details")
        logger.addFilter(ContextFilter())
        with caplog.at_level(logging.INFO, logger="test.log_action_details"):
            log_action(logger, "create", resource="user", id="123")
        assert "ACTION: create" in caplog.text
        assert "resource=user" in caplog.text
        assert "id=123" in caplog.text

    def test_log_action_with_explicit_user_id(self, caplog):
        logger = logging.getLogger("test.log_action_uid")
        logger.addFilter(ContextFilter())
        with caplog.at_level(logging.INFO, logger="test.log_action_uid"):
            log_action(logger, "delete", user_id="explicit-user")
        assert "ACTION: delete" in caplog.text
        ctx = request_context.get() or {}
        assert ctx.get("user_id") == "explicit-user"

    def test_log_action_with_explicit_client_id(self, caplog):
        logger = logging.getLogger("test.log_action_cid")
        logger.addFilter(ContextFilter())
        with caplog.at_level(logging.INFO, logger="test.log_action_cid"):
            log_action(logger, "update", client_id="explicit-client")
        assert "ACTION: update" in caplog.text
        ctx = request_context.get() or {}
        assert ctx.get("client_id") == "explicit-client"


class TestSetupLogging:
    def test_configures_root_logger(self):
        from internal.logging import setup_logging

        setup_logging("DEBUG")
        root = logging.getLogger()
        assert root.level == logging.DEBUG
        assert len(root.handlers) == 2

    def test_default_level(self):
        from internal.logging import setup_logging

        setup_logging()
        root = logging.getLogger()
        assert root.level == logging.INFO

    def test_suppresses_third_party_loggers(self):
        from internal.logging import setup_logging

        setup_logging("DEBUG")
        assert logging.getLogger("urllib3").level == logging.WARNING
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING

    def test_invalid_level_defaults_to_info(self):
        from internal.logging import setup_logging

        setup_logging("INVALID")
        root = logging.getLogger()
        assert root.level == logging.INFO


class TestGetLogger:
    def test_returns_logger(self):
        from internal.logging import get_logger

        lgr = get_logger("test.module")
        assert isinstance(lgr, logging.Logger)
        assert lgr.name == "test.module"
