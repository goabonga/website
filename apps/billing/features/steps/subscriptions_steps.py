# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for subscription management."""

from behave import given


def _run(context, coro):
    return context.loop.run_until_complete(coro)


@given("a subscription exists for the customer")
def step_create_subscription(context):
    """Create a subscription via the API and store its ID."""
    saas_id = context.created_ids["saas_id"]
    customer_id = context.created_ids["customer_id"]
    price_id = context.created_ids["price_id"]

    response = _run(
        context,
        context.client.post(
            f"/platform/{saas_id}/customers/{customer_id}/subscriptions",
            json={"price_id": price_id},
        ),
    )
    assert response.status_code == 201, (
        f"Failed to create subscription: {response.status_code} {response.text}"
    )
    data = response.json()
    context.created_ids["subscription_id"] = data["id"]
    context.created_ids["stripe_subscription_id"] = data["stripe_subscription_id"]
