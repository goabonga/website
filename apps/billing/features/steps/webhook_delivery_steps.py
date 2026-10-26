# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the retried delivery of the SaaS notifications.

The Celery tasks run eagerly: a retry runs again at once, without waiting for
its countdown.
"""

import json
from unittest.mock import patch

from behave import given, then
from billing.config import settings
from billing.tasks.webhook_tasks import deliver_saas_webhook


@given('the receiver of the SaaS app answers with the statuses "{statuses}"')
def step_receiver_statuses(context, statuses):
    context.recorder.statuses = [int(status) for status in statuses.split(",")]


@given("the notifications are tried at most {attempts:d} times")
def step_max_attempts(context, attempts):
    patcher = patch.object(settings, "saas_webhook_max_attempts", attempts)
    patcher.start()
    context.add_cleanup(patcher.stop)


@given("the Celery broker is unavailable")
def step_broker_down(context):
    patcher = patch.object(
        deliver_saas_webhook, "apply_async", side_effect=ConnectionError("broker down")
    )
    patcher.start()
    context.add_cleanup(patcher.stop)
    # Without a queue the notification is sent from the API process with the shared client
    client_patcher = patch(
        "billing.services.saas_webhook.get_http_client", return_value=context.recorder
    )
    client_patcher.start()
    context.add_cleanup(client_patcher.stop)


@then("the receiver should have been called {count:d} times")
def step_call_count(context, count):
    assert len(context.recorder.posts) == count, len(context.recorder.posts)


@then("every attempt should carry the same event identifier, body and signature")
def step_same_attempts(context):
    posts = context.recorder.posts
    assert len(posts) > 1
    assert len({json.loads(post["content"])["id"] for post in posts}) == 1
    assert len({post["content"] for post in posts}) == 1
    assert len({post["headers"]["X-Billing-Signature"] for post in posts}) == 1
