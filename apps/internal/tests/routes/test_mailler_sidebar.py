# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the admin sidebar on the mailler statistics pages."""

import pytest

from ..sidebar import (
    PAGES,
    assert_sidebar,
    prepare_page,
    running_app,
    scope_sets,
    sidebar_hrefs,
)


@pytest.mark.parametrize("page", PAGES["mailler"], ids=lambda page: page.path)
async def test_sidebar_on_page(tmp_path, page):
    """The sidebar shows the links the scopes permit and marks the page's section active."""
    async with running_app(tmp_path) as env:
        path = await prepare_page(env, page)
        for scopes in scope_sets(page.section):
            response = await env.get(path, scopes)
            assert response.status_code == 200, f"{path} as {scopes}: {response.status_code}"
            assert_sidebar(response.text, scopes, page.section)


@pytest.mark.parametrize(
    "path", ["/mailler/clients", "/mailler/clients/new", "/mailler/clients/client-001/edit"]
)
async def test_clients_pages_add_no_sidebar_link(tmp_path, path):
    """The clients pages belong to the Mailler section: they add no link of their own."""
    page = next(page for page in PAGES["mailler"] if page.path == path)
    async with running_app(tmp_path) as env:
        await prepare_page(env, page)
        response = await env.get(path, ["mailler:*"])
        assert response.status_code == 200
        hrefs = sidebar_hrefs(response.text)
        assert "/mailler" in hrefs
        assert not [href for href in hrefs if href.startswith("/mailler/")]
