# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the campaign management feature."""

import json

from behave import given, when


def _remembered(context):
    if not hasattr(context, "remembered"):
        context.remembered = {}
    return context.remembered


def _fill(context, template):
    path = template
    for name, value in _remembered(context).items():
        path = path.replace(f"{{{name}}}", str(value))
    return path


@when('I remember the response JSON key "{key}" as "{name}"')
def step_remember(context, key, name):
    _remembered(context)[name] = context.response.json()[key]


def _post(context, path, payload):
    body = json.dumps(payload)
    context.execute_steps(f'When I send a POST request to "{path}" with JSON\n"""\n{body}\n"""\n')


@given("a campaign was created through the API")
def step_campaign_created(context):
    _post(
        context,
        "/api/v1/stats/campaigns",
        {"name": "Spring sale", "destination_url": "https://example.com"},
    )
    assert context.response.status_code == 201, context.response.text
    _remembered(context)["campaign_id"] = context.response.json()["id"]


@given("a pixel was created for the remembered campaign")
def step_pixel_created(context):
    path = _fill(context, "/api/v1/stats/campaigns/{campaign_id}/pixels")
    _post(context, path, {"recipient_email": "alice@example.com"})
    assert context.response.status_code == 201, context.response.text


@when('I send a GET request to "{path}" using the remembered values')
def step_get_remembered(context, path):
    context.execute_steps(f'When I send a GET request to "{_fill(context, path)}"')


@when('I send a POST request to "{path}" using the remembered values with JSON')
def step_post_remembered(context, path):
    _post(context, _fill(context, path), json.loads(context.text))


@when('I send a DELETE request to "{path}" using the remembered values')
def step_delete_remembered(context, path):
    context.execute_steps(f'When I send a DELETE request to "{_fill(context, path)}"')
