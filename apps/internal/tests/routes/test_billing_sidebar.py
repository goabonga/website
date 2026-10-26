# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the admin sidebar on the billing pages."""

import pytest

from ..sidebar import (
    PAGES,
    assert_sidebar,
    prepare_page,
    running_app,
    scope_sets,
    sidebar_hrefs,
)


@pytest.mark.parametrize("page", PAGES["billing"], ids=lambda page: page.path)
async def test_sidebar_on_page(tmp_path, page):
    """The sidebar shows the links the scopes permit and marks the page's section active."""
    async with running_app(tmp_path) as env:
        path = await prepare_page(env, page)
        for scopes in scope_sets(page.section):
            response = await env.get(path, scopes)
            assert response.status_code == 200, f"{path} as {scopes}: {response.status_code}"
            assert_sidebar(response.text, scopes, page.section)


async def test_billing_link_follows_billing_read_on_other_sections(tmp_path):
    """Pages of other sections show the billing link to ``billing:read`` holders only."""
    async with running_app(tmp_path) as env:
        path = await prepare_page(env, PAGES["analytics"][0])
        without = await env.get(path, ["analytics:*"])
        with_scope = await env.get(path, ["analytics:*", "billing:read"])
        assert "/billing" not in sidebar_hrefs(without.text)
        assert "/billing" in sidebar_hrefs(with_scope.text)
