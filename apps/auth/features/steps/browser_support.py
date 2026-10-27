# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Helpers shared by the steps of the ``@browser`` scenarios.

The application runs in a thread of the interpreter that executes the steps, so the
SQLite stand-in, the captured e-mails and the patched settings of
``sqlite_db``, ``mailcapture`` and ``helpers`` serve the browser exactly as they serve
the in-process client.
"""

import re
from urllib.parse import urljoin

from behave import given, then
from bs4 import BeautifulSoup
from e2e_support import steps  # noqa: F401  (registers the generic browser steps)
from helpers import patch_setting


@given("the application is served at its public address")
def step_public_address(context):
    """E-mailed links and issued tokens point at the server the browser talks to."""
    patch_setting(context, "issuer", context.base_url)


def mail_links(context, address):
    """Absolute URLs of the links of the latest e-mail sent to ``address``."""
    message = context.mailbox.to(address)[-1]
    anchors = BeautifulSoup(message["html"], "html.parser").find_all("a", href=True)
    return [urljoin(context.base_url + "/", a["href"]) for a in anchors]


def mail_link(context, address, fragment):
    """The first link of the latest e-mail to ``address`` that contains ``fragment``."""
    for link in mail_links(context, address):
        if fragment in link:
            return link
    raise AssertionError(f"no link containing {fragment!r} in {mail_links(context, address)}")


def mail_code(context, address):
    """The six digit code of the latest e-mail sent to ``address``."""
    return context.mailbox.last_code_for(address)


@then('the page should link "{text}" to "{href}"')
def step_page_links(context, text, href):
    link = context.page.get_by_role("link", name=re.compile(re.escape(text), re.I)).first
    link.wait_for(state="visible")
    actual = link.get_attribute("href")
    assert actual == href, f"link {text!r} points to {actual!r}, expected {href!r}"


@then('the field "{name}" should have the value "{value}"')
def step_field_value(context, name, value):
    field = context.page.get_by_label(re.compile(re.escape(name), re.I)).first
    actual = field.input_value()
    assert actual == value, f"field {name!r} holds {actual!r}, expected {value!r}"


@given("the browser records the dialogs of the page")
def step_record_dialogs(context):
    """Alerts are accepted as Playwright does by default, and remembered for the assertions."""
    context.dialogs = []

    def on_dialog(dialog):
        context.dialogs.append(dialog.message)
        dialog.accept()

    context.page.on("dialog", on_dialog)


@then('the page showed a dialog saying "{message}"')
def step_dialog_shown(context, message):
    context.page.wait_for_timeout(100)
    assert any(message in shown for shown in context.dialogs), f"dialogs shown: {context.dialogs}"
