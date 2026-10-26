# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for prices."""

from behave import given


def _run(context, coro):
    """Run an async coroutine from sync behave steps."""
    return context.loop.run_until_complete(coro)


@given('a price "{nickname}" exists for the product')
def step_create_price(context, nickname):
    """Create a price via the API and store its ID."""
    saas_id = context.created_ids["saas_id"]
    product_id = context.created_ids["product_id"]
    response = _run(
        context,
        context.client.post(
            f"/platform/{saas_id}/products/{product_id}/prices",
            json={
                "nickname": nickname,
                "currency": "usd",
                "unit_amount": 2999,
                "billing_type": "recurring",
                "recurring_interval": "month",
                "recurring_interval_count": 1,
                "usage_type": "licensed",
            },
        ),
    )
    assert response.status_code == 201, (
        f"Failed to create price '{nickname}': {response.status_code} {response.text}"
    )
    data = response.json()
    context.created_ids["price_id"] = data["id"]


@given('a second price "{nickname}" exists for the product')
def step_create_second_price(context, nickname):
    """Create an additional price and store as new_price_id (for upgrade tests)."""
    saas_id = context.created_ids["saas_id"]
    product_id = context.created_ids["product_id"]
    response = _run(
        context,
        context.client.post(
            f"/platform/{saas_id}/products/{product_id}/prices",
            json={
                "nickname": nickname,
                "currency": "usd",
                "unit_amount": 4999,
                "billing_type": "recurring",
                "recurring_interval": "month",
                "recurring_interval_count": 1,
                "usage_type": "licensed",
            },
        ),
    )
    assert response.status_code == 201, (
        f"Failed to create second price '{nickname}': {response.status_code} {response.text}"
    )
    data = response.json()
    context.created_ids["new_price_id"] = data["id"]


@given('a metered price "{nickname}" exists for the product')
def step_create_metered_price(context, nickname):
    """Create a metered price (for usage billing) and store its ID."""
    saas_id = context.created_ids["saas_id"]
    product_id = context.created_ids["product_id"]
    response = _run(
        context,
        context.client.post(
            f"/platform/{saas_id}/products/{product_id}/prices",
            json={
                "nickname": nickname,
                "currency": "usd",
                "unit_amount": 10,
                "billing_type": "recurring",
                "recurring_interval": "month",
                "recurring_interval_count": 1,
                "usage_type": "metered",
            },
        ),
    )
    assert response.status_code == 201, (
        f"Failed to create metered price '{nickname}': {response.status_code} {response.text}"
    )
    data = response.json()
    context.created_ids["price_id"] = data["id"]


@given('a SaaS app "{name}" with slug "{slug}" exists with products and prices')
def step_create_saas_with_plans(context, name, slug):
    """Create a SaaS app with a product and price for plan listing tests."""
    # Create SaaS app
    resp = _run(
        context,
        context.client.post(
            "/platform/saas",
            json={"name": name, "slug": slug},
        ),
    )
    assert resp.status_code == 201
    saas_id = resp.json()["id"]
    context.created_ids["saas_id"] = saas_id

    # Create product
    resp = _run(
        context,
        context.client.post(
            f"/platform/{saas_id}/products",
            json={
                "name": "Starter Plan",
                "description": "For getting started",
            },
        ),
    )
    assert resp.status_code == 201
    product_id = resp.json()["id"]

    # Create price
    resp = _run(
        context,
        context.client.post(
            f"/platform/{saas_id}/products/{product_id}/prices",
            json={
                "nickname": "Monthly",
                "currency": "usd",
                "unit_amount": 999,
                "billing_type": "recurring",
                "recurring_interval": "month",
                "recurring_interval_count": 1,
                "usage_type": "licensed",
            },
        ),
    )
    assert resp.status_code == 201
