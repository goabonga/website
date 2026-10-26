# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for customers."""

from behave import given


def _run(context, coro):
    """Run an async coroutine from sync behave steps."""
    return context.loop.run_until_complete(coro)


@given('a customer "{external_id}" exists for the SaaS app')
def step_create_customer(context, external_id):
    """Create a customer via the API and store its ID."""
    saas_id = context.created_ids["saas_id"]
    response = _run(
        context,
        context.client.post(
            f"/platform/{saas_id}/customers",
            json={
                "external_id": external_id,
                "email": f"{external_id}@example.com",
                "name": f"Customer {external_id}",
            },
        ),
    )
    assert response.status_code == 201, (
        f"Failed to create customer '{external_id}': {response.status_code} {response.text}"
    )
    data = response.json()
    context.created_ids["customer_id"] = data["id"]
    context.created_ids["stripe_customer_id"] = data["stripe_customer_id"]
