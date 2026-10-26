# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for Stripe webhook handling."""

import hashlib
import hmac
import json
import time
from unittest.mock import MagicMock, patch

import stripe
from behave import given, then, when
from billing.config import settings


def _run(context, coro):
    return context.loop.run_until_complete(coro)


def _webhook_client(context):
    """Stripe posts anonymously; the proxy posts with its token when a scenario says so."""
    if getattr(context, "proxy_token", False):
        return context.webhook_client
    return context.anon_client


def _send_webhook(context, event_type, event_data):
    """Send a mocked Stripe webhook event (the signature check is mocked)."""
    event = {
        "id": getattr(context, "stripe_event_id", f"evt_bdd_{int(time.time())}"),
        "type": event_type,
        "data": {"object": event_data},
    }

    patches = [
        patch("billing.routes.webhooks.stripe.Webhook.construct_event", return_value=event),
    ]
    if not getattr(context, "real_notifications", False):
        patches += [
            patch("billing.routes.webhooks.notify_subscription_created", return_value=True),
            patch("billing.routes.webhooks.notify_subscription_updated", return_value=True),
            patch("billing.routes.webhooks.notify_subscription_deleted", return_value=True),
        ]
    for patcher in patches:
        patcher.start()
    try:
        context.response = _run(
            context,
            _webhook_client(context).post(
                "/webhooks/stripe",
                content=json.dumps(event).encode(),
                headers={"Stripe-Signature": "bdd_test_sig"},
            ),
        )
    finally:
        for patcher in patches:
            patcher.stop()


@when(
    'I receive a Stripe "customer.created" event with customer "{stripe_cust_id}" for SaaS "{saas_id}"'
)
def step_webhook_customer_created(context, stripe_cust_id, saas_id):
    """Simulate a customer.created Stripe webhook."""
    # Resolve saas_id placeholder
    resolved_saas_id = context.created_ids.get("saas_id", saas_id)
    _send_webhook(
        context,
        "customer.created",
        {
            "id": stripe_cust_id,
            "email": "webhook@example.com",
            "name": "Webhook Customer",
            "metadata": {"saas_id": resolved_saas_id, "external_id": "wh_ext_001"},
        },
    )


@when('I receive a Stripe "customer.deleted" event for customer "{stripe_cust_id}"')
def step_webhook_customer_deleted(context, stripe_cust_id):
    """Simulate a customer.deleted Stripe webhook."""
    resolved = context.created_ids.get("stripe_customer_id", stripe_cust_id)
    _send_webhook(
        context,
        "customer.deleted",
        {
            "id": resolved,
        },
    )


@when('I receive a Stripe "checkout.session.completed" event')
def step_webhook_checkout_completed(context):
    """Simulate a checkout.session.completed Stripe webhook."""
    saas_id = context.created_ids.get("saas_id", "")
    stripe_cust_id = context.created_ids.get("stripe_customer_id", "cus_wh_test")

    with patch("billing.routes.webhooks.stripe.Subscription.retrieve") as mock_retrieve:
        mock_retrieve.return_value = {"items": {"data": []}}
        _send_webhook(
            context,
            "checkout.session.completed",
            {
                "id": "cs_bdd_webhook",
                "metadata": {"saas_id": saas_id},
                "customer": stripe_cust_id,
                "subscription": "sub_bdd_webhook",
            },
        )


@when('I receive a Stripe "invoice.paid" event for subscription "{stripe_sub_id}"')
def step_webhook_invoice_paid(context, stripe_sub_id):
    """Simulate an invoice.paid Stripe webhook."""
    resolved = context.created_ids.get("stripe_subscription_id", stripe_sub_id)
    _send_webhook(
        context,
        "invoice.paid",
        {
            "id": "in_bdd_test",
            "subscription": resolved,
            "status": "paid",
        },
    )


@when('I receive a Stripe "customer.subscription.updated" event for subscription "{stripe_sub_id}"')
def step_webhook_subscription_updated(context, stripe_sub_id):
    """Simulate a customer.subscription.updated Stripe webhook."""
    resolved = context.created_ids.get("stripe_subscription_id", stripe_sub_id)
    _send_webhook(
        context,
        "customer.subscription.updated",
        {
            "id": resolved,
            "status": "active",
            "cancel_at_period_end": False,
            "current_period_start": 1704067200,
            "current_period_end": 1706745600,
            "items": {"data": []},
        },
    )


@when("I receive a Stripe event with invalid signature")
def step_webhook_invalid_signature(context):
    """Send a webhook with a signature that fails verification."""
    with patch(
        "billing.routes.webhooks.stripe.Webhook.construct_event",
        side_effect=stripe.SignatureVerificationError("bad sig", "sig_header"),
    ):
        context.response = _run(
            context,
            _webhook_client(context).post(
                "/webhooks/stripe",
                content=b"invalid payload",
                headers={"Stripe-Signature": "bad_sig"},
            ),
        )


# -- Authentication of the endpoint --------------------------------------------


@given("the webhooks proxy sends its bearer token")
def step_proxy_token(context):
    """The following events are posted with the token of the webhooks service."""
    context.proxy_token = True


@given('Stripe webhooks require the scope "{scope}"')
def step_require_scope(context, scope):
    patcher = patch.object(settings, "stripe_webhook_required_scope", scope)
    patcher.start()
    context.add_cleanup(patcher.stop)


# -- Subscriptions created by the checkout -------------------------------------


@given('the Stripe event identifier is "{event_id}"')
def step_event_id(context, event_id):
    context.stripe_event_id = event_id


@given('another SaaS app "{name}" with slug "{slug}" exists')
def step_other_saas(context, name, slug):
    """Create a second SaaS app, keeping the first one under ``first_saas_id``."""
    context.created_ids["first_saas_id"] = context.created_ids["saas_id"]
    response = _run(
        context,
        context.client.post("/platform/saas", json={"name": name, "slug": slug}),
    )
    assert response.status_code == 201, response.text
    context.created_ids["saas_id"] = response.json()["id"]


def _subscriptions_of(context, saas_id):
    response = _run(context, context.client.get(f"/platform/{saas_id}/subscriptions"))
    assert response.status_code == 200, response.text
    return response.json()


@then('the SaaS app has a subscription created from the checkout session "{session_id}"')
def step_subscription_from_session(context, session_id):
    subscriptions = _subscriptions_of(context, context.created_ids["saas_id"])
    sessions = [(sub.get("extra_data") or {}).get("checkout_session_id") for sub in subscriptions]
    assert session_id in sessions, sessions


@then("the first SaaS app has no subscription")
def step_first_saas_without_subscription(context):
    assert _subscriptions_of(context, context.created_ids["first_saas_id"]) == []


# -- Notifications sent to the SaaS app -----------------------------------------


class _Recorder:
    """Stands for the HTTP client that posts to the SaaS app webhook URL."""

    def __init__(self):
        self.posts = []

    async def post(self, url, content, headers):
        self.posts.append({"url": url, "content": content, "headers": headers})
        response = MagicMock()
        response.status_code = 200
        return response


@given('the SaaS app receives its notifications at "{url}" with the secret "{secret}"')
def step_webhook_endpoint(context, url, secret):
    saas_id = context.created_ids["saas_id"]
    response = _run(
        context,
        context.client.patch(
            f"/platform/saas/{saas_id}", json={"webhook_url": url, "webhook_secret": secret}
        ),
    )
    assert response.status_code == 200, response.text
    context.webhook_secret = secret
    context.recorder = _Recorder()
    patcher = patch("billing.services.saas_webhook.get_http_client", return_value=context.recorder)
    patcher.start()
    context.add_cleanup(patcher.stop)
    context.real_notifications = True


@given("the plan \"{slug}\" of the SaaS app has the limits '{limits}'")
def step_plan_limits(context, slug, limits):
    saas_id = context.created_ids["saas_id"]
    response = _run(
        context,
        context.client.patch(
            f"/platform/{saas_id}/products/{context.created_ids['product_id']}",
            json={"slug": slug, "metadata": {"limits": json.loads(limits)}},
        ),
    )
    assert response.status_code == 200, response.text


def _last_event(context):
    assert context.recorder.posts, "the SaaS app received no notification"
    return json.loads(context.recorder.posts[-1]["content"])


@then("the SaaS app should receive one notification")
def step_one_notification(context):
    assert len(context.recorder.posts) == 1, len(context.recorder.posts)


@then('the notification should be a "{event_type}" of the SaaS app "{slug}"')
def step_notification_type(context, event_type, slug):
    event = _last_event(context)
    assert event["type"] == event_type
    assert event["saas_slug"] == slug
    assert event["saas_id"] == context.created_ids["saas_id"]


@then("the notification should carry the plan \"{slug}\" with the limits '{limits}'")
def step_notification_plan(context, slug, limits):
    data = _last_event(context)["data"]
    assert data["plan_slug"] == slug, data
    assert data["limits"] == json.loads(limits), data
    assert data["price_id"] == context.created_ids["price_id"], data
    assert data["customer_external_id"] == "wh_notif_user"


@then("the notification should be signed with the secret of the SaaS app")
def step_notification_signature(context):
    post = context.recorder.posts[-1]
    expected = hmac.new(
        context.webhook_secret.encode(), post["content"].encode(), hashlib.sha256
    ).hexdigest()
    assert post["headers"]["X-Billing-Signature"] == expected


@then("both notifications should have the same identifier")
def step_same_notification_id(context):
    ids = [json.loads(post["content"])["id"] for post in context.recorder.posts]
    assert len(ids) == 2 and ids[0] == ids[1], ids
