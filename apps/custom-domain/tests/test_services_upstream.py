# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/services/upstream.py."""

import pytest
from custom_domain.services.upstream import (
    TCP,
    UNIX,
    InvalidUpstreamError,
    Upstream,
    parse_upstream,
)


class TestUnixSockets:
    """Socket paths."""

    @pytest.mark.parametrize(
        ("target", "address"),
        [
            ("/run/app.sock", "/run/app.sock"),
            ("unix:/run/app/app.sock", "/run/app/app.sock"),
            ("  /run/my-app_1@x.sock  ", "/run/my-app_1@x.sock"),
        ],
    )
    def test_accepted(self, target, address):
        upstream = parse_upstream(target)
        assert upstream == Upstream(UNIX, address)
        assert upstream.nginx_server == f"unix:{address}"

    @pytest.mark.parametrize(
        "target",
        [
            "/run/../etc/app.sock",
            "/run/app.sock;",
            "/run/app sock",
            "/run/app.sock\n}",
            "/run/$x",
            "unix:relative.sock",
            "/",
        ],
    )
    def test_rejected(self, target):
        with pytest.raises(InvalidUpstreamError):
            parse_upstream(target)


class TestTcpAddresses:
    """host:port addresses."""

    @pytest.mark.parametrize(
        "target",
        ["app.internal:8000", "10.0.0.5:80", "localhost:65535", "a-b.example.com:1", "[::1]:8000"],
    )
    def test_accepted(self, target):
        upstream = parse_upstream(target)
        assert upstream == Upstream(TCP, target)
        assert upstream.nginx_server == target

    def test_port_is_normalized(self):
        assert parse_upstream("app.internal:08000").address == "app.internal:8000"

    @pytest.mark.parametrize(
        "target",
        [
            "",
            "   ",
            "app.internal",
            "app.internal:",
            "app.internal:0",
            "app.internal:65536",
            "app.internal:80a",
            "app.internal:٣٣",
            "http://app.internal:8000",
            "app internal:80",
            "app.internal:80;",
            "app.internal:80 backup",
            "-bad.example.com:80",
            "[not-an-address]:80",
            "[::1]",
            ":8000",
            "a" * 600 + ":80",
        ],
    )
    def test_rejected(self, target):
        with pytest.raises(InvalidUpstreamError):
            parse_upstream(target)
