# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

import logging

import pytest
from fastapi.testclient import TestClient
from frontend.config import Settings
from frontend.logging import (
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


@pytest.fixture(autouse=True)
def _reset_context():
    clear_request_context()
    yield
    clear_request_context()


@pytest.fixture
def restore_root_logger():
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield root
    root.handlers[:] = handlers
    root.setLevel(level)


def make_record(level: int) -> logging.LogRecord:
    return logging.LogRecord("t", level, __file__, 1, "message", None, None)


def test_log_level_setting_default(monkeypatch) -> None:
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    assert Settings(_env_file=None).log_level == "INFO"


def test_stdout_filter_keeps_info_and_below() -> None:
    f = StdoutFilter()
    assert f.filter(make_record(logging.DEBUG))
    assert f.filter(make_record(logging.INFO))
    assert not f.filter(make_record(logging.WARNING))


def test_stderr_filter_keeps_warning_and_above() -> None:
    f = StderrFilter()
    assert not f.filter(make_record(logging.INFO))
    assert f.filter(make_record(logging.WARNING))
    assert f.filter(make_record(logging.CRITICAL))


def test_context_filter_defaults_to_dash() -> None:
    record = make_record(logging.INFO)
    assert ContextFilter().filter(record)
    assert (record.user_id, record.client_id) == ("-", "-")


def test_context_filter_uses_request_context() -> None:
    set_request_context(user_id="u1", client_id="c1")
    record = make_record(logging.INFO)
    ContextFilter().filter(record)
    assert (record.user_id, record.client_id) == ("u1", "c1")


def test_set_and_clear_request_context() -> None:
    set_request_context(user_id="u1", extra_key="x")
    assert request_context.get() == {"user_id": "u1", "client_id": "-", "extra_key": "x"}
    clear_request_context()
    assert request_context.get() == {}


def test_get_logger_returns_named_logger() -> None:
    assert get_logger("frontend.test").name == "frontend.test"


def test_setup_logging_splits_streams(capsys, restore_root_logger) -> None:
    setup_logging("DEBUG")
    logger = get_logger("frontend.split")
    logger.info("hello-info")
    logger.warning("hello-warning")
    captured = capsys.readouterr()
    assert "hello-info" in captured.out
    assert "hello-warning" not in captured.out
    assert "hello-warning" in captured.err
    assert "hello-info" not in captured.err
    assert "user=- | client=-" in captured.out


def test_setup_logging_level_and_unknown_level(restore_root_logger) -> None:
    setup_logging("warning")
    assert restore_root_logger.level == logging.WARNING
    setup_logging("not-a-level")
    assert restore_root_logger.level == logging.INFO


def test_setup_logging_replaces_handlers(restore_root_logger) -> None:
    setup_logging("INFO")
    setup_logging("INFO")
    assert len(restore_root_logger.handlers) == 2


def test_setup_logging_quiets_http_libraries(restore_root_logger) -> None:
    setup_logging("DEBUG")
    for name in ("urllib3", "httpx", "httpcore"):
        assert logging.getLogger(name).level == logging.WARNING


def test_log_action_formats_details(caplog) -> None:
    logger = get_logger("frontend.action")
    with caplog.at_level(logging.INFO, logger="frontend.action"):
        log_action(logger, "login", user_id="u1", ip="1.2.3.4")
        log_action(logger, "logout")
    assert caplog.messages == ["ACTION: login | ip=1.2.3.4", "ACTION: logout"]
    assert request_context.get()["user_id"] == "u1"


def test_health_request_is_logged(client: TestClient, caplog) -> None:
    with caplog.at_level(logging.INFO, logger="frontend.main"):
        client.get("/health")
    assert "Health check requested" in caplog.messages
