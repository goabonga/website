# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the OAuth client bindings of the billing SaaS apps."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from behave import given, then


def _make_binding(client_id, saas_id="saas-1"):
    """Create a mock client binding."""
    binding = MagicMock()
    binding.id = f"binding-{client_id}"
    binding.saas_app_id = saas_id
    binding.client_id = client_id
    binding.created_at = datetime(2024, 1, 2, 3, 4)
    return binding


def _saas_app_page(context, saas_id):
    """Make the billing service return a SaaS app with nothing else on its page."""
    saas_app = MagicMock()
    saas_app.id = saas_id
    saas_app.name = "Test App"
    saas_app.slug = "test-app"
    saas_app.description = None
    saas_app.is_active = True
    saas_app.webhook_url = ""
    saas_app.created_at = datetime(2024, 1, 1)
    mock = context.mock_billing
    mock.get_saas_app = AsyncMock(return_value=saas_app)
    mock.list_products = AsyncMock(return_value=[])
    mock.list_customers = AsyncMock(return_value=[])
    mock.list_subscriptions = AsyncMock(return_value=[])


@given('the SaaS app "{saas_id}" is bound to the OAuth clients "{client_ids}"')
def step_saas_bound_to(context, saas_id, client_ids):
    _saas_app_page(context, saas_id)
    bindings = [_make_binding(client_id.strip(), saas_id) for client_id in client_ids.split(",")]
    context.mock_billing.list_saas_clients = AsyncMock(return_value=bindings)


@given('the SaaS app "{saas_id}" is bound to no OAuth client')
def step_saas_bound_to_nothing(context, saas_id):
    _saas_app_page(context, saas_id)
    context.mock_billing.list_saas_clients = AsyncMock(return_value=[])


@given("binding an OAuth client succeeds")
def step_bind_succeeds(context):
    context.mock_billing.bind_client = AsyncMock(return_value=_make_binding("client-a"))


@given("binding an OAuth client fails")
def step_bind_fails(context):
    context.mock_billing.bind_client = AsyncMock(return_value=None)


@given("unbinding an OAuth client succeeds")
def step_unbind_succeeds(context):
    context.mock_billing.unbind_client = AsyncMock(return_value=True)


@given("unbinding an OAuth client fails")
def step_unbind_fails(context):
    context.mock_billing.unbind_client = AsyncMock(return_value=False)


@then('the OAuth client "{client_id}" should have been bound to the SaaS app "{saas_id}"')
def step_client_bound(context, client_id, saas_id):
    context.mock_billing.bind_client.assert_awaited_once_with(saas_id, client_id)


@then('the OAuth client "{client_id}" should have been unbound from the SaaS app "{saas_id}"')
def step_client_unbound(context, client_id, saas_id):
    context.mock_billing.unbind_client.assert_awaited_once_with(saas_id, client_id)


@then("no OAuth client should have been bound")
def step_nothing_bound(context):
    context.mock_billing.bind_client.assert_not_awaited()


@then("the OAuth clients of the SaaS app should not have been fetched")
def step_clients_not_fetched(context):
    context.mock_billing.list_saas_clients.assert_not_awaited()
