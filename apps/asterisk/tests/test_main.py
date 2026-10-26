# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for asterisk/main.py."""

import logging
from unittest.mock import patch


class TestSetupLogging:
    def test_configures_root_logger(self):
        from asterisk.main import setup_logging

        root = logging.getLogger()
        before = len(root.handlers)
        try:
            setup_logging()
            assert len(root.handlers) == before + 2
        finally:
            del root.handlers[before:]

    def test_stdout_handler_filters_errors(self):
        from asterisk.main import setup_logging

        root = logging.getLogger()
        before = len(root.handlers)
        try:
            setup_logging()
            stdout_handler, stderr_handler = root.handlers[before:]
            info = logging.LogRecord("t", logging.INFO, "f", 1, "m", None, None)
            error = logging.LogRecord("t", logging.ERROR, "f", 1, "m", None, None)
            assert stdout_handler.filter(info)
            assert not stdout_handler.filter(error)
            assert stderr_handler.level == logging.ERROR
        finally:
            del root.handlers[before:]


class TestLogConfiguration:
    def test_logs_effective_configuration(self, caplog):
        from asterisk.main import log_configuration

        with (
            patch("asterisk.main.config.AUDIOSOCKET_HOST", "127.0.0.1"),
            patch("asterisk.main.config.AUDIOSOCKET_PORT", 9092),
            caplog.at_level(logging.INFO),
        ):
            log_configuration()
        assert "127.0.0.1:9092" in caplog.text

