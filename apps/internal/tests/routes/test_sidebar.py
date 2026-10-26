# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the admin sidebar across every page and scope combination."""

import re

import pytest
from internal import TEMPLATES_DIR

from ..sidebar import (
    PAGES,
    SECTIONS,
    app,
    assert_sidebar,
    prepare_page,
    running_app,
    scope_sets,
)

ALL_PAGES = [page for pages in PAGES.values() for page in pages]


@pytest.mark.parametrize("page", ALL_PAGES, ids=lambda page: page.path)
async def test_sidebar_on_every_page(tmp_path, page):
    """Every page shows the links each scope combination permits, with its own section active."""
    async with running_app(tmp_path) as env:
        path = await prepare_page(env, page)
        for scopes in scope_sets(page.section):
            response = await env.get(path, scopes)
            assert response.status_code == 200, f"{path} as {scopes}: {response.status_code}"
            assert_sidebar(response.text, scopes, page.section, strict=True)


def _html_route_patterns() -> dict[str, re.Pattern]:
    """Return the GET routes rendering HTML, as patterns matching concrete URLs."""
    patterns = {}
    for path, operations in app.openapi()["paths"].items():
        content = operations.get("get", {}).get("responses", {}).get("200", {}).get("content", {})
        # The OAuth2 callback only renders the standalone error page
        if "text/html" in content and path != "/auth/callback":
            patterns[path] = re.compile("^" + re.sub(r"{[^}]+}", "[^/]+", path) + "$")
    return patterns


def test_every_html_route_is_covered():
    """Adding an HTML page without registering it for the sidebar tests fails here."""
    paths = [page.path for page in ALL_PAGES]
    uncovered = [
        route
        for route, pattern in _html_route_patterns().items()
        if not any(pattern.match(path) for path in paths)
    ]
    assert uncovered == []


def test_every_registered_page_is_a_route():
    """A registered page must match an existing HTML route."""
    patterns = list(_html_route_patterns().values())
    unknown = [
        page.path for page in ALL_PAGES if not any(pattern.match(page.path) for pattern in patterns)
    ]
    assert unknown == []


def test_the_template_has_no_unregistered_link():
    """Every link of ``admin/base.html`` is a registered section."""
    template = (TEMPLATES_DIR / "admin" / "base.html").read_text()
    keys = set(re.findall(r"active_section == '(\w+)'", template))
    assert keys == set(SECTIONS)


def test_every_sidebar_link_opens_a_registered_page():
    """Each sidebar link points to a page of the registry, which renders (see above)."""
    paths = {page.path for page in ALL_PAGES}
    assert {section.href for section in SECTIONS.values()} <= paths
