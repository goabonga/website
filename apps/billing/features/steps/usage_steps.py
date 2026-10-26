# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for usage reporting."""

from behave import given, then, when


def _run(context, coro):
    return context.loop.run_until_complete(coro)


@when("I report a batch of {count:d} usage events")
def step_report_batch(context, count):
    """Report a batch of usage events."""
    saas_id = context.created_ids["saas_id"]
    subscription_id = context.created_ids["subscription_id"]

    events = [
        {
            "subscription_id": subscription_id,
            "quantity": 10 * (i + 1),
            "action": f"batch_action_{i}",
        }
        for i in range(count)
    ]

    context.response = _run(
        context,
        context.client.post(
            f"/usage/{saas_id}/batch",
            json={"events": events},
        ),
    )


@when('I report usage with idempotency key "{key}"')
def step_report_usage_idempotent(context, key):
    """Report a usage event with an idempotency key."""
    saas_id = context.created_ids["saas_id"]
    subscription_id = context.created_ids["subscription_id"]

    context.response = _run(
        context,
        context.client.post(
            f"/usage/{saas_id}/report",
            json={
                "subscription_id": subscription_id,
                "quantity": 1,
                "idempotency_key": key,
                "action": "idempotent_test",
            },
        ),
    )


@when('I report a batch of {count:d} usage events with the idempotency key "{key}"')
def step_report_batch_same_key(context, count, key):
    """Report a batch whose events all repeat one idempotency key."""
    saas_id = context.created_ids["saas_id"]
    event = {
        "subscription_id": context.created_ids["subscription_id"],
        "quantity": 1,
        "idempotency_key": key,
    }
    context.response = _run(
        context,
        context.client.post(f"/usage/{saas_id}/batch", json={"events": [event] * count}),
    )


@given('a second SaaS app "{name}" with slug "{slug}" has a metered subscription')
def step_second_tenant(context, name, slug):
    """Create another SaaS app with a metered subscription, kept under ``second_*`` ids."""
    client = context.client

    def post(path, payload):
        response = _run(context, client.post(path, json=payload))
        assert response.status_code in (200, 201), f"{path}: {response.status_code} {response.text}"
        return response.json()

    saas_id = post("/platform/saas", {"name": name, "slug": slug})["id"]
    product_id = post(f"/platform/{saas_id}/products", {"name": "Second Product"})["id"]
    price_id = post(
        f"/platform/{saas_id}/products/{product_id}/prices",
        {"unit_amount": 10, "usage_type": "metered"},
    )["id"]
    customer_id = post(
        f"/platform/{saas_id}/customers",
        {"external_id": "second_user", "email": "second_user@example.com"},
    )["id"]
    subscription_id = post(
        f"/platform/{saas_id}/customers/{customer_id}/subscriptions", {"price_id": price_id}
    )["id"]
    context.created_ids["second_saas_id"] = saas_id
    context.created_ids["second_subscription_id"] = subscription_id


@when('I report usage with idempotency key "{key}" for the second SaaS app')
def step_report_second(context, key):
    saas_id = context.created_ids["second_saas_id"]
    context.response = _run(
        context,
        context.client.post(
            f"/usage/{saas_id}/report",
            json={
                "subscription_id": context.created_ids["second_subscription_id"],
                "quantity": 1,
                "idempotency_key": key,
            },
        ),
    )


@when("I report usage on the second SaaS app for the first subscription")
def step_report_cross(context):
    saas_id = context.created_ids["second_saas_id"]
    context.response = _run(
        context,
        context.client.post(
            f"/usage/{saas_id}/report",
            json={"subscription_id": context.created_ids["subscription_id"], "quantity": 1},
        ),
    )


@then("the usage events of the batch should be the same event")
def step_batch_same_event(context):
    ids = {event["id"] for event in context.response.json()}
    assert len(ids) == 1, ids


@then('the usage event should be the stored event "{alias}"')
def step_same_event(context, alias):
    assert context.response.json()["id"] == context.created_ids[alias]


@then('the usage event should not be the stored event "{alias}"')
def step_other_event(context, alias):
    assert context.response.json()["id"] != context.created_ids[alias]
