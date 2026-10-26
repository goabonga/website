# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps shared by the ``@browser`` scenarios.

Besides the generic steps of ``e2e-support`` (navigate, click, fill, expect), they cover what
every page of the application needs: the users of the identity provider, the sign-in round
trip through the provider and the cookies of the session. The stack they run on is described
in ``browser_stack``.
"""

import re
from urllib.parse import urljoin

import browser_stack
from behave import given, then, when
from e2e_support import steps  # noqa: F401
from playwright.sync_api import expect

from knowledge.models import Organization
from knowledge.models.enums import PlanType


def _scopes(text):
    return [] if text in ("", "no scope") else text.replace(",", " ").split()


def email_of(name):
    return f"{name.lower()}@example.test"


# --- users of the identity provider -------------------------------------------------


@given('a user "{name}" who holds the scopes "{scopes}"')
def step_user_with_scopes(context, name, scopes):
    browser_stack.add_user(context, name, _scopes(scopes))


@given('a user "{name}" who holds every knowledge scope')
def step_user_with_all_scopes(context, name):
    browser_stack.add_user(context, name, browser_stack.API_SCOPES)


@given('a user "{name}" who holds no scope')
def step_user_without_scopes(context, name):
    browser_stack.add_user(context, name)


# --- workspaces ---------------------------------------------------------------------


def workspace(context, name):
    """The workspace called ``name`` as stored (a detached copy)."""
    with context.stack.db.session() as session:
        return session.query(Organization).filter(Organization.name == name).one()


@then('the workspace "{name}" should exist on the "{plan}" plan')
def step_workspace_exists(context, name, plan):
    assert workspace(context, name).plan == PlanType(plan)


# --- signing in through the identity provider ---------------------------------------


def sign_in_at_provider(context, name):
    """Fill the login page of the provider the browser has been sent to."""
    page = context.page
    expect(page.get_by_role("heading", name="Sign in")).to_be_visible()
    page.get_by_label("Email").fill(email_of(name))
    page.get_by_label("Password").fill(browser_stack.PASSWORD)
    page.get_by_role("button", name="Sign in").click()


def wait_for_application(context):
    expect(context.page).to_have_url(re.compile(f"^{re.escape(context.base_url)}"))


@when('I sign in as "{name}" at the identity provider')
def step_sign_in_at_provider(context, name):
    sign_in_at_provider(context, name)
    wait_for_application(context)


@given('I have signed in as "{name}" through the identity provider')
def step_signed_in(context, name):
    context.page.goto("/auth/login")
    sign_in_at_provider(context, name)
    wait_for_application(context)


@then("I should be at the identity provider")
def step_at_provider(context):
    expect(context.page).to_have_url(re.compile(f"^{re.escape(context.stack.issuer)}"))


@then("I should be on the application")
def step_on_application(context):
    wait_for_application(context)


# --- the cookies of the session -------------------------------------------------------


def cookie_names(context):
    return {cookie["name"] for cookie in context.browser_context.cookies(context.base_url)}


@then('the browser should hold the cookie "{name}"')
def step_holds_cookie(context, name):
    assert name in cookie_names(context), cookie_names(context)


@then('the browser should not hold the cookie "{name}"')
def step_no_cookie(context, name):
    assert name not in cookie_names(context), cookie_names(context)


# --- the navigation -----------------------------------------------------------------------

#: Links that perform an action when followed: the crawl below must not follow them.
ACTION_LINKS = ("/auth/logout",)


def internal_links(context, selector):
    """The addresses of the links of the page (``selector``) that stay in the application."""
    hrefs = context.page.eval_on_selector_all(
        selector, "elements => elements.map(element => element.getAttribute('href'))"
    )
    return sorted({h for h in hrefs if h.startswith("/") and h not in ACTION_LINKS})


def assert_links_lead_to_pages(context, selector):
    """Fetch each link as the signed-in browser would and check that a page answers."""
    links = internal_links(context, selector)
    assert links, f"no link found with {selector}"
    broken = {}
    for href in links:
        status = context.browser_context.request.get(urljoin(context.base_url, href)).status
        if status >= 400:
            broken[href] = status
    assert not broken, f"links that lead nowhere: {broken}"


@then("every link of the navigation leads to a page of the application")
def step_navigation_links(context):
    assert_links_lead_to_pages(context, "nav a[href]")


@then("every link of the page leads to a page of the application")
def step_page_links(context):
    assert_links_lead_to_pages(context, "a[href]")


@then('the sidebar item "{name}" should be the active one')
def step_active_sidebar(context, name):
    expect(context.page.locator("aside .nav-item.active")).to_contain_text(name)
