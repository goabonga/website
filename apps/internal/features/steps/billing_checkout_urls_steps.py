# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the checkout URL allow-list and branding of billing SaaS apps."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from behave import given, then


def _saas_app(saas_id, urls, branding):
    """Create a mock SaaS app with a checkout URL allow-list and a branding."""
    saas_app = MagicMock()
    saas_app.id = saas_id
    saas_app.name = "Test App"
    saas_app.slug = "test-app"
    saas_app.description = None
    saas_app.is_active = True
    saas_app.webhook_url = ""
    saas_app.created_at = datetime(2024, 1, 1)
    saas_app.checkout_url_allowlist = urls
    saas_app.branding = branding
    return saas_app


@given(
    'the SaaS app "{saas_id}" accepts the checkout URLs "{urls}" and has the branding \'{branding}\''
)
def step_saas_with_checkout_settings(context, saas_id, urls, branding):
    mock = context.mock_billing
    mock.get_saas_app = AsyncMock(
        return_value=_saas_app(saas_id, urls.split(","), json.loads(branding))
    )
    mock.list_products = AsyncMock(return_value=[])
    mock.list_customers = AsyncMock(return_value=[])
    mock.list_subscriptions = AsyncMock(return_value=[])
    mock.list_saas_clients = AsyncMock(return_value=[])


@given('the SaaS app "{saas_id}" has no checkout URL and no branding')
def step_saas_without_checkout_settings(context, saas_id):
    mock = context.mock_billing
    mock.get_saas_app = AsyncMock(return_value=_saas_app(saas_id, None, None))
    mock.list_products = AsyncMock(return_value=[])
    mock.list_customers = AsyncMock(return_value=[])
    mock.list_subscriptions = AsyncMock(return_value=[])
    mock.list_saas_clients = AsyncMock(return_value=[])


@given("the billing service saves the SaaS app")
def step_billing_saves(context):
    mock = context.mock_billing
    mock.create_saas_app = AsyncMock(return_value=_saas_app("saas-new", None, None))
    mock.update_saas_app = AsyncMock(return_value=_saas_app("saas-1", None, None))


@then('the SaaS app should have been created with the checkout URLs "{urls}"')
def step_created_with_urls(context, urls):
    kwargs = context.mock_billing.create_saas_app.await_args.kwargs
    assert kwargs["checkout_url_allowlist"] == urls.split(","), kwargs


@then("the SaaS app should have been created with the branding '{branding}'")
def step_created_with_branding(context, branding):
    kwargs = context.mock_billing.create_saas_app.await_args.kwargs
    assert kwargs["branding"] == json.loads(branding), kwargs


@then("no SaaS app should have been created")
def step_nothing_created(context):
    context.mock_billing.create_saas_app.assert_not_awaited()


@then("no SaaS app should have been updated")
def step_nothing_updated(context):
    context.mock_billing.update_saas_app.assert_not_awaited()


@then("the SaaS app should have been updated with no checkout URL and no branding")
def step_updated_cleared(context):
    kwargs = context.mock_billing.update_saas_app.await_args.kwargs
    assert kwargs["checkout_url_allowlist"] is None, kwargs
    assert kwargs["branding"] is None, kwargs
