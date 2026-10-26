# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the outbound webhooks and Celery feature."""

import asyncio
import hashlib
import hmac
import re
from unittest.mock import MagicMock, patch

import httpx
from auth.celery import celery_app
from auth.db.models.tenant import WebhookDelivery
from auth.services.webhook import (
    WebhookURLError,
    compute_matching_patterns,
    sign_body,
    validate_target_url,
    webhook_service,
)
from auth.tasks import webhooks as webhook_tasks
from behave import given, then, when
from factories import make_delivery, make_tenant, make_webhook
from helpers import patch_setting
from sqlalchemy import select
from sqlite_db import use_database


# ------------------------------------------------------- patterns and signature
@when('the matching subscription patterns of "{event}" are computed')
def step_patterns(context, event):
    context.patterns = compute_matching_patterns(event)


@then('the patterns are "{patterns}"')
def step_patterns_are(context, patterns):
    assert context.patterns == patterns.split(", "), context.patterns


@given('the webhook secret "{secret}"')
def step_secret(context, secret):
    context.secret = secret


@when("the body '{body}' is signed at the timestamp {timestamp:d}")
def step_sign(context, body, timestamp):
    context.body = body.encode()
    context.signature = sign_body(context.secret, context.body, timestamp)


@then('the signature has the form "t=1700000000,v1=<64 hex digits>"')
def step_signature_form(context):
    assert re.fullmatch(r"t=1700000000,v1=[0-9a-f]{64}", context.signature), context.signature


@then('the signature is the HMAC-SHA256 of "1700000000.<body>"')
def step_signature_value(context):
    expected = hmac.new(
        context.secret.encode(), b"1700000000." + context.body, hashlib.sha256
    ).hexdigest()
    assert context.signature.endswith(f"v1={expected}")


@then("signing the same body at the timestamp {timestamp:d} gives another signature")
def step_signature_differs(context, timestamp):
    assert sign_body(context.secret, context.body, timestamp) != context.signature


# ------------------------------------------------------------------- SSRF guard
@given("private networks are not allowed")
def step_private_denied(context):
    patch_setting(context, "webhook_allow_private_networks", False)


@given("private networks are allowed")
def step_private_allowed(context):
    patch_setting(context, "webhook_allow_private_networks", True)


@when('the target URL "{url}" is validated')
def step_validate_url(context, url):
    try:
        validate_target_url(url)
        context.url_error = None
    except WebhookURLError as exc:
        context.url_error = exc


@then("the URL is rejected")
def step_url_rejected(context):
    assert context.url_error is not None


@then("the URL is accepted")
def step_url_accepted(context):
    assert context.url_error is None, context.url_error


# --------------------------------------------------------------------- dispatch
@given(
    'the tenant "{slug}" has a webhook subscribed to "{first}" and another subscribed to "{second}"'
)
def step_two_webhooks(context, slug, first, second):
    use_database(context)
    session = context.database.sync_session
    context.tenant = make_tenant(session, slug)
    make_webhook(session, context.tenant, "https://hooks.example.test/a", [first], name="a")
    make_webhook(session, context.tenant, "https://hooks.example.test/b", [second], name="b")
    session.commit()


@when('the event "{event}" is dispatched')
def step_dispatch(context, event):
    with patch.object(webhook_tasks.deliver_webhook, "delay", MagicMock()) as delay:
        context.delivery_ids = asyncio.run(
            webhook_service.dispatch(
                context.db, tenant_id=context.tenant.id, event=event, data={"id": "u1"}
            )
        )
    context.delay = delay
    context.database.commit()


def _deliveries(context):
    return list(context.database.sync_session.scalars(select(WebhookDelivery)))


@then("{count:d} delivery is created")
@then("{count:d} deliveries are created")
def step_delivery_count(context, count):
    assert len(context.delivery_ids) == count
    assert len(_deliveries(context)) == count


@then('the delivery is pending with the event "{event}"')
def step_delivery_pending(context, event):
    delivery = _deliveries(context)[0]
    assert delivery.status == "pending"
    assert delivery.event == event
    assert delivery.request_body["event"] == event
    assert delivery.request_body["data"] == {"id": "u1"}
    assert delivery.request_url == "https://hooks.example.test/a"


@then("the delivery task is queued for it")
def step_task_queued(context):
    context.delay.assert_called_once_with(str(context.delivery_ids[0]))


# --------------------------------------------------------------- delivery task
def _delivery_fixture(context, status_code, max_attempts):
    use_database(context)
    session = context.database.sync_session
    tenant = make_tenant(session, "acme")
    context.hook = make_webhook(session, tenant, "https://hooks.example.test/in", ["*"])
    context.delivery = make_delivery(session, context.hook, max_attempts=max_attempts)
    session.commit()
    context.requests = []

    def handler(request):
        context.requests.append(request)
        return httpx.Response(status_code, text="ok")

    context.transport = httpx.MockTransport(handler)


@given("a pending delivery whose endpoint answers {status:d}")
def step_pending_delivery(context, status):
    _delivery_fixture(context, status, max_attempts=5)


@given("a pending delivery whose endpoint answers {status:d} and allows {attempts:d} attempt")
def step_pending_delivery_limited(context, status, attempts):
    _delivery_fixture(context, status, max_attempts=attempts)


@when("the delivery task runs")
def step_run_delivery(context):
    real_client = httpx.Client

    def client_factory(**kwargs):
        return real_client(transport=context.transport, **kwargs)

    with patch.object(webhook_tasks.httpx, "Client", side_effect=client_factory):
        context.result = webhook_tasks.deliver_webhook(str(context.delivery.id))
    session = context.database.sync_session
    session.refresh(context.delivery)
    session.refresh(context.hook)


@then('the delivery status is "{status}"')
def step_delivery_status(context, status):
    assert context.delivery.status == status, context.result


@then("the request carried a valid signature header")
def step_request_signature(context):
    request = context.requests[0]
    header = request.headers["X-Webhook-Signature"]
    timestamp = request.headers["X-Webhook-Timestamp"]
    expected = hmac.new(
        context.hook.secret.encode(), f"{timestamp}.".encode() + request.content, hashlib.sha256
    ).hexdigest()
    assert header == f"t={timestamp},v1={expected}"


@then("the webhook failure count is {count:d}")
def step_failure_count(context, count):
    assert context.hook.failure_count == count


@then("the next attempt is scheduled in {seconds:d} seconds")
def step_next_attempt(context, seconds):
    assert context.result["retry_in_seconds"] == seconds
    assert context.delivery.next_retry_at is not None


# ----------------------------------------------------------------------- Celery
@then('the Celery application uses the default queue "{queue}"')
def step_default_queue(context, queue):
    assert celery_app.conf.task_default_queue == queue


@then('the task "{name}" is registered')
def step_task_registered(context, name):
    assert name in celery_app.tasks


@then('the beat schedule runs "{task}" every minute')
def step_beat_every_minute(context, task):
    entries = [e for e in celery_app.conf.beat_schedule.values() if e["task"] == task]
    assert len(entries) == 1
    assert entries[0]["schedule"].minute == set(range(60))
