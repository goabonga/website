# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps shared by the features that exercise the server-rendered pages."""

from behave import then, when


@when('I open "{path}"')
def step_open(context, path):
    context.response = context.call("GET", path, follow_redirects=False)


def _set_cookie_names(response):
    names = []
    for header in response.headers.get_list("set-cookie"):
        name, _, value = header.partition("=")
        names.append((name.strip(), value))
    return names


@then('I should be redirected to "{location}"')
def step_redirected_to(context, location):
    assert context.response.headers["location"] == location, context.response.headers["location"]


@then('I should be redirected to a URL starting with "{prefix}"')
def step_redirected_prefix(context, prefix):
    assert context.response.headers["location"].startswith(prefix), context.response.headers[
        "location"
    ]


@then('the browser should receive the cookies "{names}"')
def step_cookies(context, names):
    received = {name for name, _ in _set_cookie_names(context.response)}
    expected = {name.strip() for name in names.split(",")}
    assert expected <= received, (expected, received)


@then('the browser should be told to delete the cookies "{names}"')
def step_cookies_deleted(context, names):
    deleted = {
        name
        for name, value in _set_cookie_names(context.response)
        if value.startswith('""') or value.startswith(";")
    }
    expected = {name.strip() for name in names.split(",")}
    assert expected <= deleted, (expected, deleted)


@then('the page should say "{text}"')
def step_page_says(context, text):
    assert text in context.response.text, context.response.text[:500]
