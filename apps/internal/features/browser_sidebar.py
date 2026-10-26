# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Reading the admin sidebar in the browser, for the steps of the scenarios."""

import re

from playwright.sync_api import expect

#: The links of the sidebar of every admin page.
LINKS = ".admin-sidebar .admin-nav a"


def _label(text: str) -> str:
    """The text of a sidebar link without its leading icon."""
    return re.sub(r"^[^\w]+", "", text.strip())


def sidebar_links(context) -> list[dict]:
    """The links of the sidebar of the current page: label, href and highlight."""
    links = context.page.locator(LINKS)
    expect(links.first).to_be_visible()
    return [
        {
            "label": _label(link.inner_text()),
            "href": link.get_attribute("href"),
            "active": "active" in (link.get_attribute("class") or "").split(),
        }
        for link in links.all()
    ]
