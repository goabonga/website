# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the administration of the mailler clients."""

from unittest.mock import AsyncMock

from behave import given, then
from internal.services.mailler_client import MaillerAPIError


def _client(client_id="app-one", **fields):
    """Build a client record as the mailler service returns it."""
    record = {
        "client_id": client_id,
        "name": "App one",
        "is_active": True,
        "from_email": "no-reply@example.test",
        "from_name": "App one",
        "reply_to": None,
        "allowed_senders": [{"email": "other@example.test", "name": "Other"}],
        "allowed_providers": ["ses"],
        "default_provider": "ses",
        "rate_limit_per_minute": 60,
        "daily_quota": 5000,
        "callback_url": "https://app.example.test/status",
        "has_callback_secret": True,
    }
    record.update(fields)
    return record


@given('the mailler service has the clients "{client_ids}"')
def step_clients_exist(context, client_ids):
    mock = context.mock_mailler_mailler
    items = [_client(client_id.strip()) for client_id in client_ids.split(",")]
    mock.list_clients = AsyncMock(
        return_value={"items": items, "total": len(items), "page": 1, "page_size": 20, "pages": 1}
    )
    mock.get_client = AsyncMock(return_value=items[0])
    mock.get_providers = AsyncMock(return_value=["ses", "smtp"])


@given("the mailler service has no client")
def step_no_client(context):
    mock = context.mock_mailler_mailler
    mock.list_clients = AsyncMock(
        return_value={"items": [], "total": 0, "page": 1, "page_size": 20, "pages": 1}
    )


@given('the mailler service has an inactive client "{client_id}"')
def step_inactive_client(context, client_id):
    mock = context.mock_mailler_mailler
    item = _client(client_id, is_active=False)
    mock.list_clients = AsyncMock(
        return_value={"items": [item], "total": 1, "page": 1, "page_size": 20, "pages": 1}
    )


@given('the mailler service does not know the client "{client_id}"')
def step_unknown_client(context, client_id):
    context.mock_mailler_mailler.get_client = AsyncMock(return_value=None)


@given("the mailler service accepts the client changes")
def step_accepts_changes(context):
    mock = context.mock_mailler_mailler
    mock.create_client = AsyncMock(return_value=_client("app-two"))
    mock.update_client = AsyncMock(return_value=_client())
    mock.get_providers = AsyncMock(return_value=["ses", "smtp"])


@given('the mailler service refuses the client changes with "{message}"')
def step_refuses_changes(context, message):
    mock = context.mock_mailler_mailler
    mock.create_client = AsyncMock(side_effect=MaillerAPIError(message, 409))
    mock.update_client = AsyncMock(side_effect=MaillerAPIError(message, 422))


@then('the client "{client_id}" should have been registered with the sender "{sender}"')
def step_registered(context, client_id, sender):
    sent = context.mock_mailler_mailler.create_client.await_args.args[0]
    assert sent["client_id"] == client_id, sent
    assert sent["from_email"] == sender, sent


@then(
    "the registration should carry a rate limit of {limit:d} per minute and a quota of {quota:d} per day"
)
def step_registered_limits(context, limit, quota):
    sent = context.mock_mailler_mailler.create_client.await_args.args[0]
    assert sent["rate_limit_per_minute"] == limit, sent
    assert sent["daily_quota"] == quota, sent


@then('the registration should allow the providers "{providers}" with "{default}" by default')
def step_registered_providers(context, providers, default):
    sent = context.mock_mailler_mailler.create_client.await_args.args[0]
    assert sent["allowed_providers"] == providers.split(","), sent
    assert sent["default_provider"] == default, sent


@then("no client should have been registered")
def step_nothing_registered(context):
    context.mock_mailler_mailler.create_client.assert_not_awaited()


@then("no client should have been updated")
def step_nothing_updated(context):
    context.mock_mailler_mailler.update_client.assert_not_awaited()


@then('the client "{client_id}" should have been updated with no limits')
def step_updated_without_limits(context, client_id):
    called_id, sent = context.mock_mailler_mailler.update_client.await_args.args
    assert called_id == client_id
    assert sent["rate_limit_per_minute"] is None, sent
    assert sent["daily_quota"] is None, sent


@then('the client "{client_id}" should have been updated with the callback removed')
def step_updated_callback_removed(context, client_id):
    called_id, sent = context.mock_mailler_mailler.update_client.await_args.args
    assert called_id == client_id
    assert sent["callback_url"] is None, sent
    assert sent["callback_secret"] is None, sent


@then('the client "{client_id}" should have been set {state}')
def step_set_state(context, client_id, state):
    expected = {"active": True, "inactive": False}[state]
    context.mock_mailler_mailler.update_client.assert_awaited_once_with(
        client_id, {"is_active": expected}
    )
