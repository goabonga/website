# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Generic behave steps for ``@browser`` scenarios.

Importing this module registers the steps; an application does it from a module of its
``features/steps`` directory::

    from e2e_support import steps  # noqa: F401

Targets are described the way a user sees the page, never by CSS: the accessible name of
a button or link, a label, a placeholder or visible text. Prefix a target with ``css=``
to fall back on a CSS selector (``css=#submit``).
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from behave import step, then
from playwright.sync_api import Locator, Page, expect

from e2e_support.diagnostics import slugify

#: Prefix of a target that is a CSS selector instead of a user-facing description.
CSS_PREFIX = "css="
#: Selector of the navigation landmarks searched by the navigation steps.
NAVIGATION = "nav, [role='navigation']"
#: Seconds between two attempts to find a target that is not on the page yet.
POLL_INTERVAL = 0.05


def current_page(context: Any) -> Page:
    """The page of the running scenario, with a clear error outside ``@browser``."""
    page = getattr(context, "page", None)
    if page is None:
        raise AssertionError(
            "this step needs a browser page: tag the scenario or the feature with @browser "
            "and call e2e_support.behave_hooks from features/environment.py"
        )
    return page


def _timeout(context: Any) -> float:
    state = getattr(context, "e2e", None)
    return (state.settings.timeout if state else 10_000) / 1000


def _find(context: Any, candidates: list[Locator], description: str) -> Locator:
    """The first candidate that matches something, waiting for the page to settle."""
    deadline = time.monotonic() + _timeout(context)
    while True:
        for candidate in candidates:
            if candidate.count() > 0:
                return candidate.first
        if time.monotonic() >= deadline:
            raise AssertionError(f"nothing on the page matches {description}")
        time.sleep(POLL_INTERVAL)


def clickable(context: Any, target: str) -> Locator:
    """A button, a link, a labelled control or visible text called ``target``."""
    page = current_page(context)
    if target.startswith(CSS_PREFIX):
        return page.locator(target[len(CSS_PREFIX) :]).first
    return _find(
        context,
        [
            page.get_by_role("button", name=target),
            page.get_by_role("link", name=target),
            page.get_by_label(target),
            page.get_by_text(target),
        ],
        f'a button, link or text "{target}"',
    )


def field(context: Any, name: str) -> Locator:
    """A form control labelled, named or described by a placeholder ``name``."""
    page = current_page(context)
    if name.startswith(CSS_PREFIX):
        return page.locator(name[len(CSS_PREFIX) :]).first
    return _find(
        context,
        [
            page.get_by_label(name),
            page.get_by_placeholder(name),
            page.get_by_role("textbox", name=name),
            page.locator(f"[name='{name}']"),
        ],
        f'a field "{name}"',
    )


def visible_text(context: Any, text: str) -> Locator:
    return current_page(context).get_by_text(text).first


def url_for(context: Any, location: str) -> str:
    """Resolve a path against the base URL; absolute URLs are kept."""
    if re.match(r"^[a-z][a-z0-9+.-]*://", location):
        return location
    base = (getattr(context, "base_url", None) or "").rstrip("/")
    return f"{base}/{location.lstrip('/')}" if base else location


@step('I navigate to "{path}"')
def navigate(context: Any, path: str) -> None:
    current_page(context).goto(url_for(context, path))


@step('I click "{target}"')
def click(context: Any, target: str) -> None:
    clickable(context, target).click()


@step('I fill "{name}" with "{value}"')
def fill(context: Any, name: str, value: str) -> None:
    field(context, name).fill(value)


@step('I select "{option}" from "{name}"')
def select(context: Any, option: str, name: str) -> None:
    field(context, name).select_option(label=option)


@step('I press "{key}"')
def press(context: Any, key: str) -> None:
    current_page(context).keyboard.press(key)


@then('I should see "{text}"')
def see_text(context: Any, text: str) -> None:
    expect(visible_text(context, text)).to_be_visible()


@then('I should not see "{text}"')
def not_see_text(context: Any, text: str) -> None:
    expect(visible_text(context, text)).to_be_hidden()


@then('the URL should be "{location}"')
def url_is(context: Any, location: str) -> None:
    expect(current_page(context)).to_have_url(url_for(context, location))


@then('the URL should contain "{fragment}"')
def url_contains(context: Any, fragment: str) -> None:
    expect(current_page(context)).to_have_url(re.compile(re.escape(fragment)))


@then('the page title should be "{title}"')
def title_is(context: Any, title: str) -> None:
    expect(current_page(context)).to_have_title(title)


@then('the page title should contain "{fragment}"')
def title_contains(context: Any, fragment: str) -> None:
    expect(current_page(context)).to_have_title(re.compile(re.escape(fragment)))


def _located(context: Any, target: str) -> Locator:
    page = current_page(context)
    if target.startswith(CSS_PREFIX):
        return page.locator(target[len(CSS_PREFIX) :]).first
    return page.get_by_text(target).first


@then('"{target}" should be visible')
def is_visible(context: Any, target: str) -> None:
    expect(_located(context, target)).to_be_visible()


@then('"{target}" should be hidden')
def is_hidden(context: Any, target: str) -> None:
    expect(_located(context, target)).to_be_hidden()


def _navigation_link(context: Any, text: str) -> Locator:
    navigation = current_page(context).locator(NAVIGATION)
    return navigation.get_by_role("link", name=text).first


@then('the navigation should contain a link "{text}"')
def navigation_has_link(context: Any, text: str) -> None:
    expect(_navigation_link(context, text)).to_be_visible()


@then('the navigation link "{text}" should point to "{href}"')
def navigation_has_link_to(context: Any, text: str, href: str) -> None:
    link = _navigation_link(context, text)
    expect(link).to_be_visible()
    expect(link).to_have_attribute("href", href)


@then('the navigation should not contain a link "{text}"')
def navigation_lacks_link(context: Any, text: str) -> None:
    expect(_navigation_link(context, text)).to_have_count(0)


@step('I take a screenshot "{name}"')
def screenshot(context: Any, name: str) -> None:
    state = context.e2e
    directory = Path(state.settings.artifacts_dir) / "screenshots"
    directory.mkdir(parents=True, exist_ok=True)
    current_page(context).screenshot(path=directory / f"{slugify(name)}.png", full_page=True)


@then("the browser should report no errors")
def no_browser_errors(context: Any) -> None:
    context.e2e.scenario.assert_no_browser_errors()
