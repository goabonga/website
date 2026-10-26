# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for mta_sts.mta_sts module."""

from unittest.mock import PropertyMock, patch

import httpx
from mta_sts.main import app
from mta_sts.mta_sts import mta_sts_policy, render_mta_sts_policy


def render(mode: str, max_age: int, hosts: list[str]) -> str:
    with patch("mta_sts.mta_sts.settings") as mock_settings:
        mock_settings.mta_sts_mode = mode
        mock_settings.mta_sts_max_age = max_age
        type(mock_settings).mx_hosts = PropertyMock(return_value=hosts)
        return render_mta_sts_policy()


class TestRenderMtaStsPolicy:
    """Tests for render_mta_sts_policy function."""

    def test_default_policy(self):
        result = render("enforce", 86400, ["mail.goabonga.com"])
        assert result == "version: STSv1\nmode: enforce\nmx: mail.goabonga.com\nmax_age: 86400"

    def test_testing_mode(self):
        result = render("testing", 3600, ["mx.example.com"])
        assert "mode: testing" in result
        assert "max_age: 3600" in result

    def test_none_mode(self):
        assert "mode: none" in render("none", 86400, ["mail.example.com"])

    def test_multiple_mx_hosts(self):
        result = render("enforce", 86400, ["mx1.example.com", "mx2.example.com"])
        assert result == (
            "version: STSv1\n"
            "mode: enforce\n"
            "mx: mx1.example.com\n"
            "mx: mx2.example.com\n"
            "max_age: 86400"
        )

    def test_policy_starts_with_version(self):
        assert render("enforce", 86400, ["mail.example.com"]).startswith("version: STSv1")

    def test_policy_ends_with_max_age(self):
        assert render("enforce", 604800, ["mail.example.com"]).endswith("max_age: 604800")


class TestMtaStsPolicyEndpoint:
    """Tests for the policy endpoint."""

    @patch("mta_sts.mta_sts.render_mta_sts_policy", return_value="version: STSv1\nmode: enforce")
    async def test_returns_plain_text_response(self, mock_render):
        response = await mta_sts_policy()

        assert response.body == b"version: STSv1\nmode: enforce"
        assert response.media_type == "text/plain"

    async def test_http_response_with_default_settings(self):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/.well-known/mta-sts.txt")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert response.text.startswith("version: STSv1\nmode: ")
        assert response.text.splitlines()[-1].startswith("max_age: ")
