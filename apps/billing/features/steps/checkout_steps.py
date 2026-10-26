# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for checkout sessions."""

from unittest.mock import MagicMock, patch

from behave import given, then, when
from billing.services.stripe_service import StripeService


def _run(context, coro):
    return context.loop.run_until_complete(coro)


@when("I create a checkout session with customer_id")
def step_checkout_with_customer_id(context):
    """Create a checkout session using internal customer_id."""
    saas_id = context.created_ids["saas_id"]
    customer_id = context.created_ids["customer_id"]
    price_id = context.created_ids["price_id"]

    context.response = _run(
        context,
        context.client.post(
            "/checkout/session",
            json={
                "saas_id": saas_id,
                "customer_id": customer_id,
                "price_id": price_id,
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            },
        ),
    )


@when('I create a checkout session with external_id "{external_id}"')
def step_checkout_with_external_id(context, external_id):
    """Create a checkout session using customer external_id."""
    saas_id = context.created_ids["saas_id"]
    price_id = context.created_ids["price_id"]

    context.response = _run(
        context,
        context.client.post(
            "/checkout/session",
            json={
                "saas_id": saas_id,
                "external_id": external_id,
                "price_id": price_id,
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            },
        ),
    )


@when('I create a checkout session with new external_id "{external_id}" and email "{email}"')
def step_checkout_auto_create(context, external_id, email):
    """Create a checkout session that auto-creates a new customer."""
    saas_id = context.created_ids["saas_id"]
    price_id = context.created_ids["price_id"]

    context.response = _run(
        context,
        context.client.post(
            "/checkout/session",
            json={
                "saas_id": saas_id,
                "external_id": external_id,
                "customer_email": email,
                "customer_name": "New User",
                "price_id": price_id,
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            },
        ),
    )


@when("I create a checkout session with non-existent price")
def step_checkout_bad_price(context):
    """Create a checkout session with a price that doesn't exist."""
    saas_id = context.created_ids["saas_id"]
    customer_id = context.created_ids["customer_id"]

    context.response = _run(
        context,
        context.client.post(
            "/checkout/session",
            json={
                "saas_id": saas_id,
                "customer_id": customer_id,
                "price_id": "00000000-0000-0000-0000-000000000000",
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            },
        ),
    )


def _checkout_payload(context, **overrides):
    payload = {
        "saas_id": context.created_ids["saas_id"],
        "customer_id": context.created_ids["customer_id"],
        "price_id": context.created_ids["price_id"],
        "success_url": "https://example.com/success",
        "cancel_url": "https://example.com/cancel",
    }
    payload.update(overrides)
    return payload


def _post_checkout(context, payload):
    context.response = _run(context, context.client.post("/checkout/session", json=payload))


@given('another SaaS app "{name}" with slug "{slug}" has a price')
def step_foreign_price(context, name, slug):
    """Create a second SaaS app with a product and a price, keeping the first one current."""
    first = dict(context.created_ids)
    response = _run(
        context,
        context.client.post(
            "/platform/saas",
            json={"name": name, "slug": slug, "checkout_url_allowlist": ["https://example.com"]},
        ),
    )
    other_saas_id = response.json()["id"]
    response = _run(
        context,
        context.client.post(f"/platform/{other_saas_id}/products", json={"name": "Foreign Plan"}),
    )
    product_id = response.json()["id"]
    response = _run(
        context,
        context.client.post(
            f"/platform/{other_saas_id}/products/{product_id}/prices", json={"unit_amount": 500}
        ),
    )
    assert response.status_code == 201, response.text
    context.created_ids = first
    context.created_ids["foreign_price_id"] = response.json()["id"]


@when("I create a checkout session with customer_id and the foreign price")
def step_checkout_foreign_price(context):
    _post_checkout(
        context, _checkout_payload(context, price_id=context.created_ids["foreign_price_id"])
    )


@when('I create a checkout session with metadata "{pair}"')
def step_checkout_with_metadata(context, pair):
    key, value = pair.split("=")
    _post_checkout(context, _checkout_payload(context, metadata={key: value}))


@when('I create a checkout session with success URL "{url}"')
def step_checkout_with_success_url(context, url):
    _post_checkout(context, _checkout_payload(context, success_url=url))


@given("the SaaS app has no checkout URL allow-list")
def step_clear_allowlist(context):
    saas_id = context.created_ids["saas_id"]
    response = _run(
        context,
        context.client.patch(f"/platform/saas/{saas_id}", json={"checkout_url_allowlist": None}),
    )
    assert response.status_code == 200, response.text


@given('the SaaS app has the branding locale "{locale}"')
def step_set_branding(context, locale):
    saas_id = context.created_ids["saas_id"]
    response = _run(
        context,
        context.client.patch(f"/platform/saas/{saas_id}", json={"branding": {"locale": locale}}),
    )
    assert response.status_code == 200, response.text


@given("the real Stripe service talks to a mocked Stripe SDK")
def step_real_service(context):
    """Use the real service so that its metadata rules apply; only the SDK is mocked."""
    sdk_patch = patch("billing.services.stripe_service.stripe")
    context.stripe_sdk = sdk_patch.start()
    context.add_cleanup(sdk_patch.stop)
    context.stripe_sdk.checkout.Session.create.return_value = MagicMock(
        id="cs_sdk", url="https://stripe.test/cs"
    )
    service_patch = patch(
        "billing.routes.checkout.get_stripe_service", return_value=StripeService()
    )
    service_patch.start()
    context.add_cleanup(service_patch.stop)


@then("the Stripe SDK checkout session should carry the SaaS identifier of the SaaS app")
def step_check_saas_identifier(context):
    params = context.stripe_sdk.checkout.Session.create.call_args[1]
    assert params["metadata"]["saas_id"] == context.created_ids["saas_id"], params["metadata"]
    assert params["subscription_data"]["metadata"]["saas_id"] == context.created_ids["saas_id"]


@then('the Stripe checkout call should use the locale "{locale}"')
def step_check_locale(context, locale):
    assert context.stripe_mock.create_checkout_session.call_args.kwargs["locale"] == locale
