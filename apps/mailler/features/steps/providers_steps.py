# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for provider and signature scenarios."""

from behave import given, then, when
from mailler.services.providers.factory import get_available_providers, get_provider
from mailler.services.webhook_signature import (
    build_mailin_custom,
    generate_unsubscribe_signature,
    parse_mailin_custom,
    verify_unsubscribe_signature,
)
from steps.settings_steps import set_setting


@given('the "{provider}" provider is configured')
def step_provider_configured(context, provider):
    if provider == "brevo":
        set_setting(context, "brevo_api_key", "bdd-brevo-key")
    elif provider == "sendgrid":
        set_setting(context, "sendgrid_api_key", "bdd-sendgrid-key")
    elif provider == "ses":
        set_setting(context, "ses_region", "bdd-region-1")
        set_setting(context, "ses_access_key", "bdd-access")
        set_setting(context, "ses_secret_key", "bdd-secret")
    elif provider == "protonmail":
        set_setting(context, "protonmail_host", "smtp.bdd.example")
        set_setting(context, "protonmail_port", 25)
        set_setting(context, "protonmail_user", "bdd@example.com")
        set_setting(context, "protonmail_password", "bdd-password")
    else:
        raise AssertionError(f"unknown provider {provider}")


@then('the response JSON "providers" should be')
def step_providers_equal(context):
    expected = [line.strip() for line in context.text.splitlines() if line.strip()]
    assert context.response.json()["providers"] == expected, context.response.json()


@then('the response JSON "providers" should contain "{name}"')
def step_providers_contain(context, name):
    assert name in context.response.json()["providers"]


@when("I list the available providers")
def step_list_available(context):
    context.result = get_available_providers()


@when('I look up the provider "{name}"')
def step_get_provider(context, name):
    try:
        context.result = get_provider(name)
        context.error = None
    except ValueError as exc:
        context.result = None
        context.error = str(exc)


@then("the available providers should be empty")
def step_available_empty(context):
    assert context.result == [], context.result


@then('the lookup should fail with "{message}"')
def step_lookup_fails(context, message):
    assert context.error and message in context.error, context.error


@then('the lookup should return a provider named "{name}"')
def step_lookup_ok(context, name):
    assert context.result is not None and context.result.provider_name == name, context.result


@given('the signing secret is "{secret}"')
def step_signing_secret(context, secret):
    set_setting(context, "webhook_hmac_secret", secret)


@when('I sign the unsubscribe link of "{email}" for client "{client}"')
def step_sign_unsubscribe(context, email, client):
    context.signature = generate_unsubscribe_signature(email, client)


@then('the signature should be valid for "{email}" and client "{client}"')
def step_signature_valid(context, email, client):
    assert verify_unsubscribe_signature(email, client, context.signature)


@then('the signature should be rejected for "{email}" and client "{client}"')
def step_signature_rejected(context, email, client):
    assert not verify_unsubscribe_signature(email, client, context.signature)


@when('I build the Brevo custom header for email "{email_id}" to "{to_email}"')
def step_build_header(context, email_id, to_email):
    context.header = build_mailin_custom(email_id, to_email, {"campaign_id": 7})


@then('parsing the custom header should give email_id "{email_id}" and campaign_id "{campaign}"')
def step_parse_header(context, email_id, campaign):
    parsed = parse_mailin_custom(context.header)
    assert parsed["email_id"] == email_id, parsed
    assert parsed["campaign_id"] == campaign, parsed
    assert "signature" in parsed, parsed
