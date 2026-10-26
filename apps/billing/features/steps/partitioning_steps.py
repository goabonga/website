# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the partitioning of the API per SaaS application."""

import httpx
from behave import given, then, when
from billing.main import app
from httpx import ASGITransport


def _run(context, coro):
    return context.loop.run_until_complete(coro)


def _post(context, path, payload):
    response = _run(context, context.client.post(path, json=payload))
    assert response.status_code in (200, 201), f"{path}: {response.status_code} {response.text}"
    return response.json()


@given(
    'two SaaS apps "{first}" and "{second}" each with a plan, a price, a customer and a subscription'
)
def step_two_tenants(context, first, second):
    """Create two SaaS apps with the same plan slug and one subscription each.

    The identifiers are stored as ``<slug>_saas_id``, ``<slug>_product_id``,
    ``<slug>_price_id``, ``<slug>_customer_id`` and ``<slug>_subscription_id``.
    """
    for slug in (first, second):
        saas_id = _post(
            context,
            "/platform/saas",
            {
                "name": slug.title(),
                "slug": slug,
                "checkout_url_allowlist": ["https://example.com"],
            },
        )["id"]
        product_id = _post(
            context,
            f"/platform/{saas_id}/products",
            {
                "name": "Pro",
                "slug": "pro",
                "metadata": {"limits": {f"{slug}_seats": 1 if slug == first else 2}},
            },
        )["id"]
        price_id = _post(
            context,
            f"/platform/{saas_id}/products/{product_id}/prices",
            {"unit_amount": 1000, "usage_type": "metered"},
        )["id"]
        customer_id = _post(
            context,
            f"/platform/{saas_id}/customers",
            {"external_id": "user", "email": f"user.{slug}@example.com"},
        )["id"]
        subscription_id = _post(
            context,
            f"/platform/{saas_id}/customers/{customer_id}/subscriptions",
            {"price_id": price_id},
        )["id"]
        context.created_ids.update(
            {
                f"{slug}_saas_id": saas_id,
                f"{slug}_product_id": product_id,
                f"{slug}_price_id": price_id,
                f"{slug}_customer_id": customer_id,
                f"{slug}_subscription_id": subscription_id,
            }
        )


@given('an access token without OAuth client with the scopes "{scopes}"')
def step_token_without_client(context, scopes):
    """Register a token whose claims carry no client id, selected as the client "no-client"."""
    _register_client(context, "no-client", scopes, claim_client_id=None)


@given('the OAuth client "{client_id}" has the scopes "{scopes}"')
def step_oauth_client(context, client_id, scopes):
    """Register an access token of an OAuth client and prepare an HTTP client using it."""
    _register_client(context, client_id, scopes, claim_client_id=client_id)


def _register_client(context, name, scopes, claim_client_id):
    token = f"token-{name}"
    context.register_token(token, scopes.split(), claim_client_id)
    if not hasattr(context, "oauth_clients"):
        context.oauth_clients = {}
    http_client = httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    )
    context.oauth_clients[name] = http_client
    context.add_cleanup(lambda: _run(context, http_client.aclose()))


@given('the OAuth client "{client_id}" is bound to the SaaS app "{slug}"')
def step_bind(context, client_id, slug):
    """Bind a client with the default (admin) token."""
    saas_id = context.created_ids[f"{slug}_saas_id"]
    response = _run(context, context.client.put(f"/platform/saas/{saas_id}/clients/{client_id}"))
    assert response.status_code in (200, 201), response.text


@given('I am authenticated as the OAuth client "{client_id}"')
def step_authenticated_as_client(context, client_id):
    """Send the following requests with the token of an OAuth client."""
    context.use_auth = ("client", client_id)


@when('I send a PUT to "{path}"')
def step_send_put(context, path):
    from steps.common_steps import _get_client, _resolve_path

    context.response = _run(context, _get_client(context).put(_resolve_path(context, path)))


@then('the SaaS app "{slug}" still has {count:d} product')
def step_product_count(context, slug, count):
    saas_id = context.created_ids[f"{slug}_saas_id"]
    response = _run(context, context.client.get(f"/platform/{saas_id}/products"))
    assert len(response.json()) == count, response.json()
