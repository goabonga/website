# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the client status webhooks feature."""

import httpx
from behave import given, then, when
from celery.exceptions import Retry
from custom_domain.client.webhooks import WebhookSignatureError, construct_event
from custom_domain.models import AuthorizedClient
from custom_domain.services.certbot import CertbotResult
from custom_domain.services.events import publish_event as real_publish_event
from custom_domain.tasks.provisioning import deprovision_domain, provision_domain_ssl
from custom_domain.tasks.webhooks import deliver_webhook
from custom_domain.webhook_signature import SIGNATURE_HEADER, signature_header
from environment import start_patch
from ssl_provisioning_steps import fake_provisioning_environment, load_domain

URL = "https://app.example.com/hooks"
SECRET = "0123456789abcdef0123456789abcdef"


@given('an authorized client "{client_id}" with a webhook')
def step_client_with_webhook(context, client_id):
    with context.db.session() as session:
        session.add(
            AuthorizedClient(
                client_id=client_id,
                name=client_id.title(),
                default_upstream_target="/run/app.sock",
                default_cname_target="apps.example.com",
                webhook_url=URL,
                webhook_secret=SECRET,
                is_active=True,
            )
        )
        session.commit()


@given("webhook deliveries are recorded")
def step_deliveries_recorded(context):
    context.queued = []
    context.deliveries = []
    start_patch(context, "custom_domain.services.events.redis")
    queue = start_patch(context, "custom_domain.tasks.webhooks.deliver_webhook.apply_async")
    queue.side_effect = lambda **kwargs: context.queued.append(kwargs["args"])
    start_patch(
        context,
        "custom_domain.tasks.webhooks.get_sync_db",
        side_effect=lambda: context.db.session(),
    )

    def post(url, **kwargs):
        context.deliveries.append({"url": url, **kwargs})
        return httpx.Response(context.receiver_status)

    context.receiver_status = 200
    start_patch(context, "custom_domain.tasks.webhooks.httpx.post", side_effect=post)


@given("the receiver answers with the status {status:d}")
def step_receiver_status(context, status):
    if not hasattr(context, "deliveries"):
        step_deliveries_recorded(context)
    context.receiver_status = status


def use_real_events(context):
    """Let the task's events go through the real ``publish_event`` (Redis is faked)."""
    if not hasattr(context, "nginx"):
        fake_provisioning_environment(context, CertbotResult(success=True), record_events=False)
    start_patch(
        context,
        "custom_domain.tasks.provisioning.publish_event",
        side_effect=real_publish_event,
    )


@when('the SSL provisioning task publishes its real events for "{name}"')
def step_provision_real_events(context, name):
    use_real_events(context)
    provision_domain_ssl(load_domain(context, name).id)


@when('the deprovisioning task publishes its real events for "{name}"')
def step_deprovision_real_events(context, name):
    use_real_events(context)
    deprovision_domain(load_domain(context, name).id)


@when("the queued webhooks are delivered")
def step_deliver_queued(context):
    for args in context.queued:
        deliver_webhook(*args)


@when('a webhook is delivered for "{name}"')
def step_deliver_one(context, name):
    domain = load_domain(context, name)
    context.retry_requested = False
    deliver_webhook.push_request(retries=0)
    try:
        deliver_webhook(
            domain.id,
            "domain.active",
            {"status": "active"},
            "delivery-1",
            "2026-01-01T00:00:00+00:00",
        )
    except Retry:
        context.retry_requested = True
    finally:
        deliver_webhook.pop_request()


@then('the client received the events "{events}"')
def step_received(context, events):
    received = [d["headers"]["X-Custom-Domain-Event"] for d in context.deliveries]
    assert received == [e.strip() for e in events.split(",")], received


@then("the client received no webhook")
def step_received_nothing(context):
    assert context.deliveries == []


@then("every delivery is correctly signed")
def step_signed(context):
    for delivery in context.deliveries:
        assert delivery["url"] == URL
        construct_event(delivery["content"], delivery["headers"][SIGNATURE_HEADER], SECRET)


@then('the last delivery describes the domain "{name}" as "{status}"')
def step_last_delivery(context, name, status):
    delivery = context.deliveries[-1]
    event = construct_event(delivery["content"], delivery["headers"][SIGNATURE_HEADER], SECRET)
    assert event.domain["domain"] == name
    assert event.status == status


@then("the delivery is retried later")
def step_retried(context):
    assert context.retry_requested


@then('the SDK reads the event "{name}" from the delivery')
def step_sdk_reads(context, name):
    delivery = context.deliveries[0]
    event = construct_event(delivery["content"], delivery["headers"][SIGNATURE_HEADER], SECRET)
    assert event.event == name
    assert event.id == "delivery-1"


@then("the SDK refuses the delivery when its body is altered")
def step_sdk_tampered(context):
    delivery = context.deliveries[0]
    try:
        construct_event(delivery["content"] + b" ", delivery["headers"][SIGNATURE_HEADER], SECRET)
    except WebhookSignatureError:
        return
    raise AssertionError("an altered body was accepted")


@then("the SDK refuses the delivery when it is signed with another secret")
def step_sdk_wrong_secret(context):
    delivery = context.deliveries[0]
    forged = signature_header("x" * 32, delivery["content"])
    try:
        construct_event(delivery["content"], forged, SECRET)
    except WebhookSignatureError:
        return
    raise AssertionError("a forged signature was accepted")
