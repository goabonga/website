# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps asserting the admin sidebar as a user sees it in the browser."""

from behave import then, when
from browser_sidebar import LINKS, sidebar_links
from playwright.sync_api import expect


@then('the sidebar menu should have a link "{label}" to "{href}"')
def step_sidebar_has_link(context, label, href):
    links = [(link["label"], link["href"]) for link in sidebar_links(context)]
    assert (label, href) in links, f"sidebar links: {links}"


@then('the sidebar menu should not have a link "{label}"')
def step_sidebar_lacks_link(context, label):
    labels = [link["label"] for link in sidebar_links(context)]
    assert label not in labels, f"sidebar links: {labels}"


@then('the sidebar menu should highlight only "{label}"')
def step_sidebar_highlight(context, label):
    active = [link["label"] for link in sidebar_links(context) if link["active"]]
    assert active == [label], f"highlighted sidebar links: {active}"


@then("the sidebar menu should list exactly these links")
def step_sidebar_exactly(context):
    expected = [(row["label"], row["href"]) for row in context.table]
    actual = [(link["label"], link["href"]) for link in sidebar_links(context)]
    assert actual == expected, f"sidebar links: {actual}"


@then('the sidebar menu should show the user "{email}"')
def step_sidebar_user_email(context, email):
    expect(context.page.locator(".admin-sidebar .user-email")).to_have_text(email)


@then("the sidebar menu should show the signed in user")
def step_sidebar_signed_in_user(context):
    user = context.browser_user
    expect(context.page.locator(".admin-sidebar .user-email")).to_have_text(user.email)
    expect(context.page.locator(".admin-sidebar .user-name")).to_have_text(user.name)


@when('I follow the sidebar link "{label}"')
def step_follow_sidebar_link(context, label):
    labels = [link["label"] for link in sidebar_links(context)]
    assert label in labels, f"sidebar links: {labels}"
    context.page.locator(LINKS).nth(labels.index(label)).click()


@when("I sign out from the sidebar")
def step_sign_out_from_sidebar(context):
    context.page.locator(".admin-sidebar .logout-btn").click()


@then("the sidebar menu should not be shown")
def step_sidebar_not_shown(context):
    expect(context.page.locator(".admin-sidebar")).to_have_count(0)


@then('the sidebar menu entry "{label}" should be {state}')
def step_sidebar_entry_state(context, label, state):
    assert state in ("visible", "hidden"), f"Unknown state '{state}'"
    labels = [link["label"] for link in sidebar_links(context)]
    assert (label in labels) == (state == "visible"), f"sidebar links: {labels}"
