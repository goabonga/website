# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the Brevo webhook scenarios."""

from behave import when
from mailler.services.webhook_signature import build_mailin_custom
from steps.database_steps import load_email


def _post_event(context, alias, event, custom, **fields):
    email = load_email(email_id=context.created_ids[alias])
    payload = {"event": event, "email": email.to_email, "X-Mailin-custom": custom, **fields}
    context.response = context.loop.run_until_complete(
        context.client.post("/api/v1/webhooks/brevo", json=payload)
    )
    return email


@when('Brevo sends a signed "{event}" event for "{alias}"')
def step_brevo_event(context, event, alias):
    email = load_email(email_id=context.created_ids[alias])
    custom = build_mailin_custom(str(email.id), email.to_email)
    _post_event(context, alias, event, custom)


@when('Brevo sends a signed "{event}" event with reason "{reason}" for "{alias}"')
def step_brevo_event_with_reason(context, event, reason, alias):
    email = load_email(email_id=context.created_ids[alias])
    custom = build_mailin_custom(str(email.id), email.to_email)
    _post_event(context, alias, event, custom, reason=reason)


@when('Brevo sends a "{event}" event for "{alias}" with a forged signature')
def step_brevo_event_forged(context, event, alias):
    email = load_email(email_id=context.created_ids[alias])
    _post_event(context, alias, event, f"email_id:{email.id},signature:forged")


@when('Brevo sends a "{event}" event for "{alias}" without signature')
def step_brevo_event_unsigned(context, event, alias):
    email = load_email(email_id=context.created_ids[alias])
    _post_event(context, alias, event, f"email_id:{email.id}")
