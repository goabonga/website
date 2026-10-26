# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the browser scenarios of the sidebar across all the pages."""

import time

import browser_support
from behave import given, then, when
from browser_sidebar import LINKS, sidebar_links

#: The services answer with something on every page of the sidebar.
SERVICES_WITH_DATA = """
    Given the dashboard analytics are available
    And the analytics overview returns data
    And the campaigns list returns data
    And the IP stats returns data
    And the mailler stats returns data
    And the mailler emails list returns data
    And the contacts list returns data
    And the contact groups list returns groups
    And the templates API returns a list of templates
    And the campaigns API returns a list of campaigns
    And the campaigns API returns templates and groups for the form
    And VPN sessions exist
    And the billing SaaS apps list returns data
    And the team list returns data
"""


@given("every service answers with some data")
def step_services_with_data(context):
    context.execute_steps(SERVICES_WITH_DATA)


@given("a narrow screen")
def step_narrow_screen(context):
    context.page.set_viewport_size({"width": 400, "height": 800})


@when("I open the menu")
def step_open_menu(context):
    context.page.locator("label.hamburger-btn").click()


@then("the sidebar menu should be off screen")
def step_menu_off_screen(context):
    box = context.page.locator(".admin-sidebar").bounding_box()
    assert box is not None and box["x"] + box["width"] <= 0, box


@then("the sidebar menu should be on screen")
def step_menu_on_screen(context):
    deadline = time.monotonic() + context.e2e.settings.timeout / 1000
    while True:
        box = context.page.locator(".admin-sidebar").bounding_box()
        if box is not None and box["x"] >= 0:
            return
        assert time.monotonic() < deadline, box
        context.page.wait_for_timeout(50)


@when("I follow every link of the sidebar in turn")
def step_follow_every_link(context):
    visited = []
    for link in sidebar_links(context):
        context.page.locator(LINKS).nth(len(visited)).click()
        context.page.wait_for_load_state()
        visited.append((link["label"], context.page.url.removeprefix(context.base_url)))
        active = [item["label"] for item in sidebar_links(context) if item["active"]]
        assert active == [link["label"]], (link["label"], active, context.page.url)
    context.visited = visited


@then("the sidebar links should have led to these pages")
def step_visited_pages(context):
    expected = [(row["label"], row["path"]) for row in context.table]
    assert context.visited == expected, context.visited


def _exchanges(context):
    requests = browser_support.provider(context).requests_to("/oauth2/token")
    return [r for r in requests if "token-exchange" in r.form.get("grant_type", "")]


@then('the last token exchange should have asked for the scopes "{scopes}"')
def step_exchange_scopes(context, scopes):
    exchanges = _exchanges(context)
    assert exchanges, "the provider received no token exchange"
    asked = exchanges[-1].form.get("scope", "").split()
    missing = [scope for scope in scopes.split() if scope not in asked]
    assert not missing, f"asked {asked}, missing {missing}"


@then('the last token exchange should have granted only "{scopes}"')
def step_exchange_granted(context, scopes):
    exchanges = _exchanges(context)
    assert exchanges, "the provider received no token exchange"
    granted = sorted(exchanges[-1].json["scope"].split())
    assert granted == sorted(scopes.split()), granted
