# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the public unsubscribe scenarios."""

import html
import re

from behave import given, when
from mailler.config import settings
from mailler.services.webhook_signature import generate_unsubscribe_signature
from steps.settings_steps import set_setting


@given('a valid unsubscribe signature for "{email}" of client "{client}"')
def step_valid_unsubscribe_signature(context, email, client):
    """Sign the address for a client and store the signature as ``{unsub_sig}``.

    A signing secret is configured for the scenario when none is set.
    """
    if not settings.webhook_hmac_secret:
        set_setting(context, "webhook_hmac_secret", "bdd-hmac-secret")
    context.created_ids["unsub_sig"] = generate_unsubscribe_signature(email, client)


@when("I submit the confirmation form")
def step_submit_confirmation_form(context):
    """Submit the form of the last response the way a browser would."""
    action = re.search(r'<form method="POST" action="([^"]+)"', context.response.text)
    assert action, "No form found in the response"
    context.response = context.loop.run_until_complete(
        context.client.post(html.unescape(action.group(1)))
    )
