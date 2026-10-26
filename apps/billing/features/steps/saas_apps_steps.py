# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for SaaS applications."""

from behave import given, then


def _run(context, coro):
    """Run an async coroutine from sync behave steps."""
    return context.loop.run_until_complete(coro)


@given('a SaaS app "{name}" with slug "{slug}" exists')
def step_create_saas_app(context, name, slug):
    """Create a SaaS app via the API and store its ID."""
    response = _run(
        context,
        context.client.post(
            "/platform/saas",
            json={
                "name": name,
                "slug": slug,
                "description": f"BDD test app: {name}",
            },
        ),
    )
    assert response.status_code == 201, (
        f"Failed to create SaaS app '{slug}': {response.status_code} {response.text}"
    )
    data = response.json()
    context.created_ids["saas_id"] = data["id"]


@then('the checkout URL allow-list should be "{entries}"')
def step_check_allowlist(context, entries):
    """Compare the stored allow-list with a comma separated list."""
    assert context.response.json()["checkout_url_allowlist"] == entries.split(",")
