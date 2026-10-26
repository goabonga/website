# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the /ws WebSocket channel and the connection manager."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from reachy_mini_api.main import ConnectionManager, app, manager


class TestConnectionManager:
    """Tests for ConnectionManager."""

    @pytest.mark.asyncio
    async def test_connect(self):
        """Accept and track WebSocket connection."""
        mgr = ConnectionManager()
        ws = AsyncMock()
        await mgr.connect(ws)
        assert ws in mgr.active_connections
        ws.accept.assert_awaited_once()

    def test_disconnect(self):
        """Remove WebSocket from active connections."""
        mgr = ConnectionManager()
        ws = MagicMock()
        mgr.active_connections.append(ws)
        mgr.disconnect(ws)
        assert ws not in mgr.active_connections

    @pytest.mark.asyncio
    async def test_send_personal_message(self):
        """Send JSON message to specific WebSocket."""
        mgr = ConnectionManager()
        ws = AsyncMock()
        msg = {"type": "test", "data": "hello"}
        await mgr.send_personal_message(msg, ws)
        ws.send_json.assert_awaited_once_with(msg)

    @pytest.mark.asyncio
    async def test_broadcast(self):
        """Broadcast message to all connected WebSockets."""
        mgr = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        mgr.active_connections = [ws1, ws2]
        msg = {"type": "broadcast", "data": "hello"}
        await mgr.broadcast(msg)
        ws1.send_json.assert_awaited_once_with(msg)
        ws2.send_json.assert_awaited_once_with(msg)

    @pytest.mark.asyncio
    async def test_broadcast_handles_send_error(self):
        """Continue broadcasting even if one connection fails."""
        mgr = ConnectionManager()
        ws1 = AsyncMock()
        ws1.send_json.side_effect = Exception("connection closed")
        ws2 = AsyncMock()
        mgr.active_connections = [ws1, ws2]
        msg = {"type": "broadcast", "data": "hello"}
        await mgr.broadcast(msg)
        ws2.send_json.assert_awaited_once_with(msg)


class TestWebSocketEndpoint:
    """Tests for /ws WebSocket endpoint."""

    def test_websocket_connect_and_receive_welcome(self):
        """Connect to WebSocket and receive welcome message."""
        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            data = ws.receive_json()
            assert data["type"] == "connected"
            assert "Reachy Mini API" in data["message"]
            assert "timestamp" in data

    def test_websocket_ping(self):
        """Send ping and receive pong."""
        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # welcome message
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"
            assert "timestamp" in data

    def test_websocket_status(self):
        """Send status and receive connection info."""
        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # welcome
            ws.send_json({"type": "status"})
            data = ws.receive_json()
            assert data["type"] == "status"
            assert "connections" in data
            assert data["connections"] >= 1

    def test_websocket_broadcast(self):
        """Send broadcast message."""
        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # welcome
            ws.send_json({"type": "broadcast", "data": {"msg": "hi"}})
            data = ws.receive_json()
            assert data["type"] == "broadcast"
            assert data["data"] == {"msg": "hi"}

    def test_websocket_broadcast_no_data(self):
        """Send broadcast message without data field."""
        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # welcome
            ws.send_json({"type": "broadcast"})
            data = ws.receive_json()
            assert data["type"] == "broadcast"
            assert data["data"] == {}

    def test_websocket_unknown_type(self):
        """Send unknown message type and receive ack."""
        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # welcome
            ws.send_json({"type": "unknown_cmd", "payload": 42})
            data = ws.receive_json()
            assert data["type"] == "ack"
            assert data["received"]["type"] == "unknown_cmd"

    def test_websocket_invalid_json(self):
        """Send invalid JSON and receive error."""
        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # welcome
            ws.send_text("this is not json")
            data = ws.receive_json()
            assert data["type"] == "error"
            assert data["message"] == "Invalid JSON"

    def test_websocket_message_no_type(self):
        """Send message without type field."""
        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # welcome
            ws.send_json({"data": "no type"})
            data = ws.receive_json()
            assert data["type"] == "ack"

    def test_two_clients_receive_the_broadcast(self):
        """A broadcast reaches every connected client."""
        client = TestClient(app)
        with client.websocket_connect("/ws") as first, client.websocket_connect("/ws") as second:
            first.receive_json()
            second.receive_json()
            first.send_json({"type": "broadcast", "data": {"n": 1}})
            assert first.receive_json()["data"] == {"n": 1}
            assert second.receive_json()["data"] == {"n": 1}

    def test_status_counts_connections(self):
        """The status message reports the number of open connections."""
        client = TestClient(app)
        with client.websocket_connect("/ws") as first, client.websocket_connect("/ws") as second:
            first.receive_json()
            second.receive_json()
            first.send_json({"type": "status"})
            assert first.receive_json()["connections"] == 2

    def test_disconnect_removes_the_connection(self):
        """A closed connection is no longer tracked."""
        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
            assert len(manager.active_connections) == 1
        assert manager.active_connections == []

    def test_actions_are_logged(self):
        """Connect, message and disconnect are audited."""
        client = TestClient(app)
        with (
            patch("reachy_mini_api.main.log_action") as mock_log,
            client.websocket_connect("/ws") as ws,
        ):
            ws.receive_json()
            ws.send_json({"type": "ping"})
            ws.receive_json()
        actions = [call.args[1] for call in mock_log.call_args_list]
        assert actions == ["websocket_connect", "websocket_message", "websocket_disconnect"]
