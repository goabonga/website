# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for backend.utils.request.get_client_ip."""

from unittest.mock import MagicMock

from backend.utils.request import get_client_ip


def _make_request(headers=None, client_host=None):
    """Helper to create a mock Request object."""
    request = MagicMock()
    _headers = headers or {}
    request.headers = _headers

    if client_host is not None:
        request.client = MagicMock()
        request.client.host = client_host
    else:
        request.client = None

    return request


class TestGetClientIp:
    """Tests for get_client_ip."""

    def test_returns_first_ip_from_x_forwarded_for(self):
        """Should return the first IP from X-Forwarded-For header."""
        request = _make_request(
            headers={"X-Forwarded-For": "203.0.113.50, 70.41.3.18, 150.172.238.178"},
            client_host="127.0.0.1",
        )

        result = get_client_ip(request)

        assert result == "203.0.113.50"

    def test_returns_x_real_ip_when_no_forwarded_for(self):
        """Should return X-Real-IP when X-Forwarded-For is not present."""
        request = _make_request(
            headers={"X-Real-IP": "198.51.100.42"},
            client_host="127.0.0.1",
        )

        result = get_client_ip(request)

        assert result == "198.51.100.42"

    def test_returns_client_host_when_no_headers(self):
        """Should return request.client.host when no proxy headers are present."""
        request = _make_request(
            headers={},
            client_host="192.168.1.100",
        )

        result = get_client_ip(request)

        assert result == "192.168.1.100"

    def test_returns_unknown_when_no_client(self):
        """Should return 'unknown' when there is no client information."""
        request = _make_request(headers={}, client_host=None)

        result = get_client_ip(request)

        assert result == "unknown"
