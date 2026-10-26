# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.core.logging — structured logging with context."""

import logging

from auth.core.logging import (
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

# ── ContextFilter ───────────────────────────────────────────────────────────


class TestContextFilter:
    def test_adds_default_context(self):
        clear_request_context()
        f = ContextFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        result = f.filter(record)
        assert result is True
        assert record.user_id == "-"
        assert record.client_id == "-"

    def test_adds_set_context(self):
        set_request_context(user_id="u1", client_id="c1")
        f = ContextFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        f.filter(record)
        assert record.user_id == "u1"
        assert record.client_id == "c1"
        clear_request_context()


# ── StdoutFilter ────────────────────────────────────────────────────────────


class TestStdoutFilter:
    def test_allows_debug(self):
        f = StdoutFilter()
        record = logging.LogRecord("t", logging.DEBUG, "", 0, "", (), None)
        assert f.filter(record) is True

    def test_allows_info(self):
        f = StdoutFilter()
        record = logging.LogRecord("t", logging.INFO, "", 0, "", (), None)
        assert f.filter(record) is True

    def test_rejects_warning(self):
        f = StdoutFilter()
        record = logging.LogRecord("t", logging.WARNING, "", 0, "", (), None)
        assert f.filter(record) is False

    def test_rejects_error(self):
        f = StdoutFilter()
        record = logging.LogRecord("t", logging.ERROR, "", 0, "", (), None)
        assert f.filter(record) is False

    def test_rejects_critical(self):
        f = StdoutFilter()
        record = logging.LogRecord("t", logging.CRITICAL, "", 0, "", (), None)
        assert f.filter(record) is False


# ── StderrFilter ────────────────────────────────────────────────────────────


class TestStderrFilter:
    def test_rejects_debug(self):
        f = StderrFilter()
        record = logging.LogRecord("t", logging.DEBUG, "", 0, "", (), None)
        assert f.filter(record) is False

    def test_rejects_info(self):
        f = StderrFilter()
        record = logging.LogRecord("t", logging.INFO, "", 0, "", (), None)
        assert f.filter(record) is False

    def test_allows_warning(self):
        f = StderrFilter()
        record = logging.LogRecord("t", logging.WARNING, "", 0, "", (), None)
        assert f.filter(record) is True

    def test_allows_error(self):
        f = StderrFilter()
        record = logging.LogRecord("t", logging.ERROR, "", 0, "", (), None)
        assert f.filter(record) is True

    def test_allows_critical(self):
        f = StderrFilter()
        record = logging.LogRecord("t", logging.CRITICAL, "", 0, "", (), None)
        assert f.filter(record) is True


# ── setup_logging ───────────────────────────────────────────────────────────


class TestSetupLogging:
    def test_default_level(self):
        setup_logging()
        root = logging.getLogger()
        assert root.level == logging.INFO
        assert len(root.handlers) == 2

    def test_debug_level(self):
        setup_logging("DEBUG")
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_warning_level(self):
        setup_logging("WARNING")
        root = logging.getLogger()
        assert root.level == logging.WARNING

    def test_invalid_level_defaults_to_info(self):
        setup_logging("INVALID")
        root = logging.getLogger()
        assert root.level == logging.INFO

    def test_silences_third_party(self):
        setup_logging()
        assert logging.getLogger("urllib3").level == logging.WARNING
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING


# ── get_logger ──────────────────────────────────────────────────────────────


class TestGetLogger:
    def test_returns_logger(self):
        logger = get_logger("test.module")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.module"


# ── set_request_context / clear_request_context ─────────────────────────────


class TestRequestContext:
    def test_set_and_get(self):
        set_request_context(user_id="u1", client_id="c1")
        ctx = request_context.get()
        assert ctx["user_id"] == "u1"
        assert ctx["client_id"] == "c1"
        clear_request_context()

    def test_none_defaults_to_dash(self):
        set_request_context()
        ctx = request_context.get()
        assert ctx["user_id"] == "-"
        assert ctx["client_id"] == "-"
        clear_request_context()

    def test_extra_kwargs(self):
        set_request_context(user_id="u1", tenant="t1")
        ctx = request_context.get()
        assert ctx["tenant"] == "t1"
        clear_request_context()

    def test_clear(self):
        set_request_context(user_id="u1")
        clear_request_context()
        ctx = request_context.get()
        assert ctx == {}


# ── log_action ──────────────────────────────────────────────────────────────


class TestLogAction:
    def test_basic(self):
        clear_request_context()
        logger = logging.getLogger("test.action")
        logger.handlers = []
        handler = logging.Handler()
        records = []
        handler.emit = lambda r: records.append(r)
        # Add context filter so user_id/client_id attributes exist
        handler.addFilter(ContextFilter())
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        log_action(logger, "test_action")
        assert len(records) == 1
        assert "ACTION: test_action" in records[0].getMessage()
        clear_request_context()

    def test_with_details(self):
        clear_request_context()
        logger = logging.getLogger("test.action2")
        logger.handlers = []
        records = []
        handler = logging.Handler()
        handler.emit = lambda r: records.append(r)
        handler.addFilter(ContextFilter())
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        log_action(logger, "create_user", key1="val1", key2="val2")
        msg = records[0].getMessage()
        assert "ACTION: create_user" in msg
        assert "key1=val1" in msg
        assert "key2=val2" in msg
        clear_request_context()

    def test_with_user_context(self):
        clear_request_context()
        logger = logging.getLogger("test.action3")
        logger.handlers = []
        records = []
        handler = logging.Handler()
        handler.emit = lambda r: records.append(r)
        handler.addFilter(ContextFilter())
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        log_action(logger, "login", user_id="u99", client_id="c99")
        # Verify context was updated
        ctx = request_context.get()
        assert ctx["user_id"] == "u99"
        assert ctx["client_id"] == "c99"
        clear_request_context()

    def test_uses_existing_context(self):
        set_request_context(user_id="ctx_user", client_id="ctx_client")
        logger = logging.getLogger("test.action4")
        logger.handlers = []
        records = []
        handler = logging.Handler()
        handler.emit = lambda r: records.append(r)
        handler.addFilter(ContextFilter())
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        log_action(logger, "action_with_ctx")
        assert len(records) == 1
        clear_request_context()
