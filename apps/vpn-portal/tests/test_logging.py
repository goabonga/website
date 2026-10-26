# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for vpn_portal.logging."""

import logging

import pytest
from vpn_portal.logging import (
    clear_request_context,
    get_logger,
    log_action,
    request_context,
    set_request_context,
    setup_logging,
)


@pytest.fixture
def clean_root_logger():
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    root.handlers.clear()
    yield root
    root.handlers[:] = handlers
    root.setLevel(level)


@pytest.fixture(autouse=True)
def reset_context():
    token = request_context.set(None)
    yield
    request_context.reset(token)


def test_setup_logging_splits_streams(clean_root_logger, capsys):
    setup_logging("DEBUG")
    logger = get_logger("test.split")

    logger.info("an info message")
    logger.debug("a debug message")
    logger.warning("a warning message")
    logger.error("an error message")

    captured = capsys.readouterr()
    assert "an info message" in captured.out
    assert "a debug message" in captured.out
    assert "a warning message" not in captured.out
    assert "a warning message" in captured.err
    assert "an error message" in captured.err
    assert "an info message" not in captured.err


def test_setup_logging_applies_level(clean_root_logger):
    setup_logging("warning")

    assert clean_root_logger.level == logging.WARNING


def test_setup_logging_unknown_level_falls_back_to_info(clean_root_logger):
    setup_logging("nonsense")

    assert clean_root_logger.level == logging.INFO


def test_setup_logging_replaces_handlers(clean_root_logger):
    setup_logging()
    setup_logging()

    assert len(clean_root_logger.handlers) == 2


def test_setup_logging_quiets_third_party_loggers(clean_root_logger):
    setup_logging("DEBUG")

    for name in ("urllib3", "httpx", "httpcore"):
        assert logging.getLogger(name).level == logging.WARNING


def test_records_default_to_dash_without_context(clean_root_logger, capsys):
    setup_logging()

    get_logger("test.ctx").info("hello")

    assert "user=- | client=-" in capsys.readouterr().out


def test_request_context_is_rendered(clean_root_logger, capsys):
    setup_logging()
    set_request_context(user_id="u-1", client_id="c-1")

    get_logger("test.ctx").info("hello")

    assert "user=u-1 | client=c-1" in capsys.readouterr().out


def test_clear_request_context(clean_root_logger, capsys):
    setup_logging()
    set_request_context(user_id="u-1")
    clear_request_context()

    get_logger("test.ctx").info("hello")

    assert "user=- | client=-" in capsys.readouterr().out


def test_set_request_context_keeps_extra_values():
    set_request_context(user_id="u-1", request_id="r-9")

    assert request_context.get() == {"user_id": "u-1", "client_id": "-", "request_id": "r-9"}


def test_log_action_formats_details(clean_root_logger, capsys):
    setup_logging()

    log_action(get_logger("test.action"), "issue", user_id="u-2", serial="abc")

    out = capsys.readouterr().out
    assert "ACTION: issue | serial=abc" in out
    assert "user=u-2" in out


def test_log_action_without_details(clean_root_logger, capsys):
    setup_logging()

    log_action(get_logger("test.action"), "ping")

    assert "ACTION: ping" in capsys.readouterr().out
