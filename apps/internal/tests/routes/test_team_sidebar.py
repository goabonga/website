# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the admin sidebar on the team AI pages."""

import pytest

from ..sidebar import (
    PAGES,
    assert_sidebar,
    prepare_page,
    running_app,
    scope_sets,
    sidebar_hrefs,
)


@pytest.mark.parametrize("page", PAGES["team"], ids=lambda page: page.path)
async def test_sidebar_on_page(tmp_path, page):
    """The sidebar shows the links the scopes permit and marks the page's section active."""
    async with running_app(tmp_path) as env:
        path = await prepare_page(env, page)
        for scopes in scope_sets(page.section):
            response = await env.get(path, scopes)
            assert response.status_code == 200, f"{path} as {scopes}: {response.status_code}"
            assert_sidebar(response.text, scopes, page.section)


async def test_team_pages_show_gated_links(tmp_path):
    """Team pages ask for the sidebar scopes too, so they show the VPN and billing links."""
    async with running_app(tmp_path) as env:
        for page in PAGES["team"]:
            path = await prepare_page(env, page)
            response = await env.get(path, ["team:*", "vpn:admin", "billing:read"])
            hrefs = sidebar_hrefs(response.text)
            assert "/vpn/sessions" in hrefs and "/billing" in hrefs, path
