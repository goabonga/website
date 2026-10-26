# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for products."""

from behave import given


def _run(context, coro):
    """Run an async coroutine from sync behave steps."""
    return context.loop.run_until_complete(coro)


@given('a product "{name}" exists for the SaaS app')
def step_create_product(context, name):
    """Create a product via the API and store its ID."""
    saas_id = context.created_ids["saas_id"]
    response = _run(
        context,
        context.client.post(
            f"/platform/{saas_id}/products",
            json={"name": name, "description": f"BDD product: {name}"},
        ),
    )
    assert response.status_code == 201, (
        f"Failed to create product '{name}': {response.status_code} {response.text}"
    )
    data = response.json()
    context.created_ids["product_id"] = data["id"]
