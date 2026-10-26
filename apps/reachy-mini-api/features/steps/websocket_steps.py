# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the WebSocket feature."""

from behave import given, then, when
from fastapi.testclient import TestClient


def open_websocket(context):
    """Open the /ws connection in-process and return the welcome message."""
    context.ws = TestClient(context.app).websocket_connect("/ws")
    context.ws.__enter__()
    return context.ws.receive_json()


@when("I connect to the WebSocket endpoint")
def step_connect(context):
    """Connect and keep the welcome message as the last message."""
    context.last_message = open_websocket(context)


@given("I am connected to the WebSocket endpoint")
def step_already_connected(context):
    """Connect and discard the welcome message."""
    open_websocket(context)


@when('I send a WebSocket message with type "{msg_type}"')
def step_send_message(context, msg_type):
    """Send a JSON message with the given type and read the reply."""
    context.ws.send_json({"type": msg_type})
    context.last_message = context.ws.receive_json()


@when('I send a WebSocket broadcast with data "{data}"')
def step_send_broadcast(context, data):
    """Send a broadcast message carrying data and read the reply."""
    context.ws.send_json({"type": "broadcast", "data": data})
    context.last_message = context.ws.receive_json()


@when('I send raw text "{text}"')
def step_send_raw(context, text):
    """Send text that is not JSON and read the reply."""
    context.ws.send_text(text)
    context.last_message = context.ws.receive_json()


@then('I should receive a message with type "{msg_type}"')
def step_message_type(context, msg_type):
    """Check the type of the last message."""
    assert context.last_message is not None, "No message received"
    assert context.last_message.get("type") == msg_type, context.last_message


@then('the message should contain "{field}"')
def step_message_contains(context, field):
    """Check that the last message has the field."""
    assert field in context.last_message, context.last_message


@then('the message field "{field}" should be "{value}"')
def step_message_field_equals(context, field, value):
    """Check a string field of the last message."""
    assert context.last_message[field] == value, context.last_message


@then('the message field "{field}" should be at least {minimum:d}')
def step_message_field_minimum(context, field, minimum):
    """Check a numeric field of the last message."""
    assert context.last_message[field] >= minimum, context.last_message


@then('the message field "{field}" should be an empty object')
def step_message_field_empty(context, field):
    """Check that a field of the last message is an empty object."""
    assert context.last_message[field] == {}, context.last_message
