# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the admin sidebar on the analytics pages."""

import re

import pytest
from internal import TEMPLATES_DIR

from ..sidebar import (
    PAGES,
    SECTIONS,
    assert_sidebar,
    prepare_page,
    running_app,
    scope_sets,
)


@pytest.mark.parametrize("page", PAGES["analytics"], ids=lambda page: page.path)
async def test_sidebar_on_page(tmp_path, page):
    """The sidebar shows the links the scopes permit and marks the page's section active."""
    async with running_app(tmp_path) as env:
        path = await prepare_page(env, page)
        for scopes in scope_sets(page.section):
            response = await env.get(path, scopes)
            assert response.status_code == 200, f"{path} as {scopes}: {response.status_code}"
            assert_sidebar(response.text, scopes, page.section)


async def test_forbidden_page_renders_without_sidebar(tmp_path):
    """The 403 page is a standalone page: it has no sidebar."""
    async with running_app(tmp_path) as env:
        path = await prepare_page(env, PAGES["analytics"][0])
        response = await env.get(path, ["contacts:read"])
        assert response.status_code == 403
        assert "admin-nav" not in response.text


def test_sections_match_the_base_template():
    """The sections the tests expect are links of ``admin/base.html``, gated as expected."""
    template = (TEMPLATES_DIR / "admin" / "base.html").read_text()
    links = {}
    gate = None
    for line in template.splitlines():
        if match := re.search(r"{% if user and user.has_scope\('([^']+)'\) %}", line):
            gate = match.group(1)
        elif "{% endif %}" in line and "active_section" not in line:
            gate = None
        elif match := re.search(
            r'<a href="([^"]+)" class="{% if active_section == \'(\w+)\'', line
        ):
            links[match.group(2)] = (match.group(1), gate)
    registered = {key: (section.href, section.gate) for key, section in SECTIONS.items()}
    assert {key: links.get(key) for key in SECTIONS} == registered
