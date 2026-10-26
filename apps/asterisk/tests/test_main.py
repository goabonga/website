# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for asterisk/main.py."""

import asyncio
import logging
import signal
from unittest.mock import AsyncMock, MagicMock, patch


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


class TestShutdown:
    async def test_stops_server(self):
        from asterisk.main import shutdown

        server = AsyncMock()

        await shutdown(server, signal.SIGTERM)
        server.stop.assert_called_once()


class TestMain:
    @patch("asterisk.main.AudioSocketServer")
    @patch("asterisk.main.config")
    async def test_creates_server_with_config(self, mock_config, MockServer):
        from asterisk.main import main

        mock_config.AUDIOSOCKET_HOST = "127.0.0.1"
        mock_config.AUDIOSOCKET_PORT = 9092

        mock_server_instance = MagicMock()
        mock_server_instance.start = AsyncMock(side_effect=asyncio.CancelledError)
        MockServer.return_value = mock_server_instance

        await main()
        MockServer.assert_called_once_with("127.0.0.1", 9092)
        mock_server_instance.start.assert_awaited_once()

    @patch("asterisk.main.AudioSocketServer")
    @patch("asterisk.main.config")
    async def test_registers_call_handler(self, mock_config, MockServer):
        from asterisk.call_handler import handle_call
        from asterisk.main import main

        mock_config.AUDIOSOCKET_HOST = "127.0.0.1"
        mock_config.AUDIOSOCKET_PORT = 9092

        mock_server_instance = MagicMock()
        mock_server_instance.start = AsyncMock(side_effect=asyncio.CancelledError)
        MockServer.return_value = mock_server_instance

        await main()
        mock_server_instance.set_handler.assert_called_once_with(handle_call)

    @patch("asterisk.main.AudioSocketServer")
    @patch("asterisk.main.config")
    async def test_handles_cancelled_error(self, mock_config, MockServer):
        from asterisk.main import main

        mock_config.AUDIOSOCKET_HOST = "127.0.0.1"
        mock_config.AUDIOSOCKET_PORT = 9092

        mock_server_instance = MagicMock()
        mock_server_instance.start = AsyncMock(side_effect=asyncio.CancelledError)
        MockServer.return_value = mock_server_instance

        # Should not raise
        await main()

    @patch("asterisk.main.shutdown", new_callable=AsyncMock)
    @patch("asterisk.main.AudioSocketServer")
    @patch("asterisk.main.config")
    async def test_signal_handler_calls_shutdown(self, mock_config, MockServer, mock_shutdown):
        """A SIGTERM received while serving schedules the graceful shutdown."""
        from asterisk.main import main

        mock_config.AUDIOSOCKET_HOST = "127.0.0.1"
        mock_config.AUDIOSOCKET_PORT = 9092

        mock_server_instance = MagicMock()
        mock_server_instance.stop = AsyncMock()

        registered_handlers = {}

        async def start_then_signal():
            # Simulate a signal being received during server.start()
            if signal.SIGTERM in registered_handlers:
                registered_handlers[signal.SIGTERM]()
            # Allow the created task to run
            await asyncio.sleep(0)
            raise asyncio.CancelledError

        mock_server_instance.start = start_then_signal
        MockServer.return_value = mock_server_instance

        loop = asyncio.get_running_loop()

        def capture_handler(sig, callback, *args):
            registered_handlers[sig] = callback

        with patch.object(loop, "add_signal_handler", side_effect=capture_handler):
            await main()

        mock_shutdown.assert_called_once()
