# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the Stripe service.

The real ``StripeService`` class is used; only the Stripe SDK entry points are
replaced by mocks.
"""

from unittest.mock import MagicMock, patch

from behave import then, when
from billing.services.stripe_service import StripeService, build_stripe_description


def _call(context, sdk_object, method, action):
    """Run ``action`` with ``stripe.<sdk_object>.<method>`` mocked."""
    with patch(f"billing.services.stripe_service.stripe.{sdk_object}.{method}") as mocked:
        mocked.return_value = MagicMock(id="stripe_bdd")
        action(StripeService())
    context.stripe_call = mocked.call_args.kwargs


@when('I create the Stripe product "{name}" for SaaS "{saas_id}"')
def step_create_product(context, name, saas_id):
    _call(
        context,
        "Product",
        "create",
        lambda service: service.create_product(saas_id=saas_id, name=name),
    )


@when('I register the Stripe product "{name}" with metadata "{pair}" for SaaS "{saas_id}"')
def step_create_product_with_metadata(context, name, pair, saas_id):
    key, value = pair.split("=")
    _call(
        context,
        "Product",
        "create",
        lambda service: service.create_product(saas_id=saas_id, name=name, metadata={key: value}),
    )


@when('I create a Stripe checkout session for SaaS "{saas_id}" with metadata "{pair}"')
def step_create_checkout(context, saas_id, pair):
    key, value = pair.split("=")
    _call(
        context,
        "checkout.Session",
        "create",
        lambda service: service.create_checkout_session(
            saas_id=saas_id,
            stripe_customer_id="cus_bdd",
            stripe_price_id="price_bdd",
            success_url="https://app.example.test/ok",
            cancel_url="https://app.example.test/ko",
            metadata={key: value},
        ),
    )


@when(
    'I create the Stripe product "{name}" for SaaS "{saas_id}" with the limits document \'{document}\''
)
def step_create_product_with_limits(context, name, saas_id, document):
    import json

    _call(
        context,
        "Product",
        "create",
        lambda service: service.create_product(
            saas_id=saas_id, name=name, metadata={"limits": json.loads(document)}
        ),
    )


@when('I create the Stripe customer "{external_id}" for SaaS "{saas_id}"')
def step_create_customer(context, external_id, saas_id):
    _call(
        context,
        "Customer",
        "create",
        lambda service: service.create_customer(
            saas_id=saas_id, email=f"{external_id}@example.com", external_id=external_id
        ),
    )


@when('I create a metered Stripe price for SaaS "{saas_id}"')
def step_create_metered_price(context, saas_id):
    _call(
        context,
        "Price",
        "create",
        lambda service: service.create_price(
            saas_id=saas_id,
            stripe_product_id="prod_bdd",
            unit_amount=None,
            usage_type="metered",
        ),
    )


@when('I build a description "{description}" with the features "{first}" and "{second}"')
def step_build_description(context, description, first, second):
    context.description = build_stripe_description(
        description,
        {"features": [{"label": first}, {"label": second}, {"label": "Hidden", "disabled": True}]},
    )


@then("the Stripe call metadata should contain \"{key}\" with value '{value}'")
def step_check_metadata_quoted(context, key, value):
    assert context.stripe_call["metadata"].get(key) == value, context.stripe_call["metadata"]


@then('the Stripe call metadata should contain "{key}" with value "{value}"')
def step_check_metadata(context, key, value):
    assert context.stripe_call["metadata"].get(key) == value, context.stripe_call["metadata"]


@then('the Stripe call parameter "{key}" should be "{value}"')
def step_check_parameter(context, key, value):
    assert str(context.stripe_call[key]) == value


@then('the Stripe price should aggregate usage with "{aggregate}"')
def step_check_aggregate(context, aggregate):
    assert context.stripe_call["recurring"]["aggregate_usage"] == aggregate


@then("the description should be")
def step_check_description(context):
    assert context.description == context.text, context.description
