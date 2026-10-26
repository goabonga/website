# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for billing.services.saas_webhook.

Covers sign_payload, the event envelope and its stable identifier,
deliver_event and dispatch_webhook, the notify_subscription_* helpers,
get_saas_app_by_id, and the get_http_client singleton.
"""

import hashlib
import hmac
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from billing.config import settings
from billing.services import saas_webhook
from billing.services.saas_webhook import (
    WebhookDeliveryError,
    build_event,
    build_event_id,
    build_subscription_data,
    deliver_event,
    dispatch_webhook,
    get_http_client,
    get_saas_app_by_id,
    notify_subscription_created,
    notify_subscription_deleted,
    notify_subscription_updated,
    sign_payload,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_http_client():
    """Reset the module-level _http_client singleton between tests."""
    saas_webhook._http_client = None
    yield
    saas_webhook._http_client = None


@pytest.fixture
def saas_app():
    """A mock SaasApp with webhook configured."""
    app = MagicMock()
    app.id = "saas-uuid-1"
    app.slug = "test-app"
    app.webhook_url = "https://app.example.com/webhooks"
    app.webhook_secret = "whsec_test_secret"
    return app


@pytest.fixture
def saas_app_no_url():
    """A mock SaasApp without a webhook URL."""
    app = MagicMock()
    app.id = "saas-uuid-2"
    app.slug = "no-url-app"
    app.webhook_url = None
    app.webhook_secret = "whsec_secret"
    return app


@pytest.fixture
def saas_app_no_secret():
    """A mock SaasApp with webhook URL but no secret."""
    app = MagicMock()
    app.id = "saas-uuid-3"
    app.slug = "no-secret-app"
    app.webhook_url = "https://app.example.com/webhooks"
    app.webhook_secret = None
    return app


@pytest.fixture
def mock_http_client():
    """Patch get_http_client to return a mock async client."""
    client = AsyncMock(spec=httpx.AsyncClient)
    with patch("billing.services.saas_webhook.get_http_client", return_value=client):
        yield client


@pytest.fixture
def mock_db():
    """Provide a mock async database session."""
    db = AsyncMock()
    return db


def _make_subscription_mock(
    sub_id="sub-uuid-1",
    customer_external_id="ext_user_1",
    status_value="active",
    plan_name="Pro Plan",
    plan_slug="pro",
    limits=None,
    current_period_start=None,
    current_period_end=None,
    cancel_at_period_end=False,
    canceled_at=None,
    has_customer=True,
    has_price=True,
    has_product=True,
):
    """Build a mock Subscription with nested relationships."""
    sub = MagicMock()
    sub.id = sub_id
    sub.status = MagicMock()
    sub.status.value = status_value
    sub.current_period_start = current_period_start or datetime(2025, 1, 1, tzinfo=UTC)
    sub.current_period_end = current_period_end or datetime(2025, 2, 1, tzinfo=UTC)
    sub.cancel_at_period_end = cancel_at_period_end
    sub.canceled_at = canceled_at

    if has_customer:
        customer = MagicMock()
        customer.external_id = customer_external_id
        customer.saas_app = MagicMock()
        customer.saas_app.id = "saas-uuid-1"
        customer.saas_app.slug = "test-app"
        customer.saas_app.webhook_url = "https://app.example.com/webhooks"
        customer.saas_app.webhook_secret = "whsec_test"
        sub.customer = customer
    else:
        sub.customer = None

    if has_price and has_product:
        product = MagicMock()
        product.name = plan_name
        product.slug = plan_slug
        product.extra_data = {"limits": limits} if limits is not None else {}
        price = MagicMock()
        price.id = "price-uuid-1"
        price.product = product
        sub.price = price
    elif has_price:
        price = MagicMock()
        price.id = "price-uuid-1"
        price.product = None
        sub.price = price
    else:
        sub.price = None

    return sub


# =========================================================================
# sign_payload
# =========================================================================


class TestSignPayload:
    """Tests for the sign_payload helper."""

    def test_sign_payload_correct_hmac(self):
        """Verify the HMAC-SHA256 output matches manual computation."""
        payload = '{"type": "test.event", "data": {}}'
        secret = "my_secret_key"

        result = sign_payload(payload, secret)

        expected = hmac.new(
            secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        assert result == expected

    def test_sign_payload_different_secrets_differ(self):
        """Different secrets produce different signatures."""
        payload = '{"data": 1}'
        sig1 = sign_payload(payload, "secret_a")
        sig2 = sign_payload(payload, "secret_b")
        assert sig1 != sig2

    def test_sign_payload_different_payloads_differ(self):
        """Different payloads produce different signatures."""
        secret = "shared"
        sig1 = sign_payload("payload_a", secret)
        sig2 = sign_payload("payload_b", secret)
        assert sig1 != sig2

    def test_sign_payload_returns_hex_string(self):
        """Output should be a hex-encoded string."""
        result = sign_payload("test", "key")
        assert isinstance(result, str)
        # A SHA256 hex digest is exactly 64 chars
        assert len(result) == 64
        # All chars should be hex digits
        int(result, 16)


# =========================================================================
# get_http_client
# =========================================================================


class TestGetHttpClient:
    """Tests for the get_http_client singleton."""

    def test_returns_async_client(self):
        """First call should create an httpx.AsyncClient."""
        client = get_http_client()
        assert isinstance(client, httpx.AsyncClient)

    def test_singleton_behavior(self):
        """Subsequent calls should return the same instance."""
        client1 = get_http_client()
        client2 = get_http_client()
        assert client1 is client2

    def test_reset_creates_new_client(self):
        """After resetting the module-level variable, a new client is created."""
        client1 = get_http_client()
        saas_webhook._http_client = None
        client2 = get_http_client()
        assert client1 is not client2


# =========================================================================
# get_saas_app_by_id
# =========================================================================


class TestGetSaasAppById:
    """Tests for get_saas_app_by_id."""

    async def test_found(self, mock_db):
        """Returns the SaasApp when found."""
        mock_saas_app = MagicMock()
        mock_saas_app.id = "saas-uuid-1"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_saas_app
        mock_db.execute.return_value = mock_result

        result = await get_saas_app_by_id(mock_db, "saas-uuid-1")

        assert result is mock_saas_app
        mock_db.execute.assert_called_once()

    async def test_not_found(self, mock_db):
        """Returns None when not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await get_saas_app_by_id(mock_db, "nonexistent-id")

        assert result is None


# =========================================================================
# build_event_id / build_event / build_subscription_data
# =========================================================================


class TestEventId:
    """The identifier of an event is stable and unique per notification."""

    def test_same_inputs_give_the_same_id(self):
        first = build_event_id("saas-1", "evt_1", "subscription.updated", "sub-1")
        second = build_event_id("saas-1", "evt_1", "subscription.updated", "sub-1")

        assert first == second

    @pytest.mark.parametrize(
        "other",
        [
            ("saas-2", "evt_1", "subscription.updated", "sub-1"),
            ("saas-1", "evt_2", "subscription.updated", "sub-1"),
            ("saas-1", "evt_1", "subscription.deleted", "sub-1"),
            ("saas-1", "evt_1", "subscription.updated", "sub-2"),
        ],
    )
    def test_any_change_gives_another_id(self, other):
        base = build_event_id("saas-1", "evt_1", "subscription.updated", "sub-1")

        assert build_event_id(*other) != base

    def test_id_is_a_uuid(self):
        import uuid

        uuid.UUID(build_event_id("s", "e", "t", "u"))


class TestBuildEvent:
    def test_envelope(self, saas_app):
        event = build_event(saas_app, "subscription.created", {"a": 1}, "evt-id")

        assert event["id"] == "evt-id"
        assert event["type"] == "subscription.created"
        assert event["saas_id"] == "saas-uuid-1"
        assert event["saas_slug"] == "test-app"
        assert event["data"] == {"a": 1}
        assert "created" in event


class TestBuildSubscriptionData:
    def test_carries_plan_slug_price_and_limits(self):
        sub = _make_subscription_mock(limits={"max_seats": 5, "emails_per_day": -1})

        data = build_subscription_data(sub)

        assert data["plan_slug"] == "pro"
        assert data["plan_name"] == "Pro Plan"
        assert data["price_id"] == "price-uuid-1"
        assert data["limits"] == {"max_seats": 5, "emails_per_day": -1}
        assert data["customer_external_id"] == "ext_user_1"
        assert data["status"] == "active"

    def test_plan_without_limits(self):
        assert build_subscription_data(_make_subscription_mock())["limits"] is None

    def test_non_integer_limits_are_left_out(self):
        sub = _make_subscription_mock(limits={"ok": 1, "bad": "x", "none": None})

        assert build_subscription_data(sub)["limits"] == {"ok": 1}

    def test_subscription_without_price(self):
        data = build_subscription_data(_make_subscription_mock(has_price=False))

        assert data["plan_name"] is None
        assert data["plan_slug"] is None
        assert data["price_id"] is None
        assert data["limits"] is None

    def test_price_without_product(self):
        data = build_subscription_data(_make_subscription_mock(has_product=False))

        assert data["price_id"] == "price-uuid-1"
        assert data["plan_slug"] is None


# =========================================================================
# deliver_event
# =========================================================================


def _ok_response():
    response = AsyncMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    return response


def _status_error(status_code: int) -> httpx.HTTPStatusError:
    response = MagicMock()
    response.status_code = status_code
    return httpx.HTTPStatusError("error", request=MagicMock(), response=response)


class TestDeliverEvent:
    """One attempt, with a classified failure."""

    async def test_success_signs_the_exact_body(self, saas_app, mock_http_client):
        mock_http_client.post.return_value = _ok_response()
        event = {"id": "evt-1", "type": "subscription.created", "data": {"x": 1}}

        await deliver_event(saas_app, event)

        kwargs = mock_http_client.post.call_args[1]
        assert json.loads(kwargs["content"]) == event
        assert kwargs["headers"]["Content-Type"] == "application/json"
        assert kwargs["headers"]["X-Billing-Signature"] == sign_payload(
            kwargs["content"], "whsec_test_secret"
        )

    async def test_no_secret_means_no_signature(self, saas_app_no_secret, mock_http_client):
        mock_http_client.post.return_value = _ok_response()

        await deliver_event(saas_app_no_secret, {"id": "e", "type": "t"})

        assert "X-Billing-Signature" not in mock_http_client.post.call_args[1]["headers"]

    async def test_no_url_is_not_retryable(self, saas_app_no_url):
        with pytest.raises(WebhookDeliveryError) as exc_info:
            await deliver_event(saas_app_no_url, {"id": "e", "type": "t"})

        assert exc_info.value.retryable is False

    @pytest.mark.parametrize("status_code", [500, 502, 503, 408, 425, 429])
    async def test_server_errors_and_throttling_are_retryable(
        self, saas_app, mock_http_client, status_code
    ):
        response = MagicMock()
        response.raise_for_status.side_effect = _status_error(status_code)
        mock_http_client.post.return_value = response

        with pytest.raises(WebhookDeliveryError) as exc_info:
            await deliver_event(saas_app, {"id": "e", "type": "t"})

        assert exc_info.value.retryable is True
        assert str(status_code) in str(exc_info.value)

    @pytest.mark.parametrize("status_code", [400, 401, 403, 404, 410, 422])
    async def test_client_errors_are_not_retryable(self, saas_app, mock_http_client, status_code):
        response = MagicMock()
        response.raise_for_status.side_effect = _status_error(status_code)
        mock_http_client.post.return_value = response

        with pytest.raises(WebhookDeliveryError) as exc_info:
            await deliver_event(saas_app, {"id": "e", "type": "t"})

        assert exc_info.value.retryable is False

    async def test_network_errors_are_retryable(self, saas_app, mock_http_client):
        mock_http_client.post.side_effect = httpx.ConnectError("refused")

        with pytest.raises(WebhookDeliveryError) as exc_info:
            await deliver_event(saas_app, {"id": "e", "type": "t"})

        assert exc_info.value.retryable is True

    def test_http_client_timeout_comes_from_the_settings(self, monkeypatch):
        monkeypatch.setattr(settings, "saas_webhook_timeout", 4.5)

        assert get_http_client().timeout.read == 4.5


# =========================================================================
# dispatch_webhook
# =========================================================================


class TestDispatchWebhook:
    """Tests for dispatch_webhook."""

    async def test_success_with_signature(self, saas_app, mock_http_client):
        """Successful dispatch with HMAC signature header."""
        mock_http_client.post.return_value = _ok_response()

        result = await dispatch_webhook(
            saas_app, "subscription.created", {"key": "value"}, "evt_1", "sub-1"
        )

        assert result is True
        mock_http_client.post.assert_called_once()
        call_kwargs = mock_http_client.post.call_args[1]
        assert call_kwargs["headers"]["Content-Type"] == "application/json"
        assert "X-Billing-Signature" in call_kwargs["headers"]

        payload = json.loads(call_kwargs["content"])
        assert payload["type"] == "subscription.created"
        assert payload["data"] == {"key": "value"}
        assert payload["saas_slug"] == "test-app"
        assert payload["saas_id"] == "saas-uuid-1"
        assert payload["id"] == build_event_id(
            "saas-uuid-1", "evt_1", "subscription.created", "sub-1"
        )
        assert "created" in payload

    async def test_a_redelivered_stripe_event_keeps_its_id(self, saas_app, mock_http_client):
        mock_http_client.post.return_value = _ok_response()

        await dispatch_webhook(saas_app, "subscription.updated", {}, "evt_9", "sub-1")
        await dispatch_webhook(saas_app, "subscription.updated", {}, "evt_9", "sub-1")

        ids = [
            json.loads(call[1]["content"])["id"] for call in mock_http_client.post.call_args_list
        ]
        assert ids[0] == ids[1]

    async def test_no_webhook_url_returns_false(self, saas_app_no_url):
        """Returns False when saas_app has no webhook_url."""
        result = await dispatch_webhook(
            saas_app_no_url, "subscription.created", {"key": "value"}, "evt_1", "sub-1"
        )
        assert result is False

    async def test_http_status_error_returns_false(self, saas_app, mock_http_client):
        """Returns False on HTTP status error."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_http_client.post.return_value = mock_response
        mock_response.raise_for_status.side_effect = _status_error(500)

        result = await dispatch_webhook(saas_app, "subscription.created", {"data": 1}, "e", "s")

        assert result is False

    async def test_generic_exception_returns_false(self, saas_app, mock_http_client):
        """Returns False on any unexpected exception."""
        mock_http_client.post.side_effect = Exception("Connection refused")

        result = await dispatch_webhook(saas_app, "subscription.created", {"data": 1}, "e", "s")

        assert result is False

    async def test_no_webhook_secret_no_signature_header(
        self, saas_app_no_secret, mock_http_client
    ):
        """When webhook_secret is None, X-Billing-Signature should NOT be sent."""
        mock_http_client.post.return_value = _ok_response()

        result = await dispatch_webhook(saas_app_no_secret, "test.event", {"x": 1}, "e", "s")

        assert result is True
        call_kwargs = mock_http_client.post.call_args[1]
        assert "X-Billing-Signature" not in call_kwargs["headers"]

    async def test_posts_to_correct_url(self, saas_app, mock_http_client):
        """Verify the POST is sent to saas_app.webhook_url."""
        mock_http_client.post.return_value = _ok_response()

        await dispatch_webhook(saas_app, "test.event", {}, "e", "s")

        call_args = mock_http_client.post.call_args
        assert call_args[0][0] == "https://app.example.com/webhooks"

    async def test_signature_matches_payload(self, saas_app, mock_http_client):
        """X-Billing-Signature should match sign_payload(payload, secret)."""
        mock_http_client.post.return_value = _ok_response()

        await dispatch_webhook(saas_app, "test.event", {"id": 42}, "e", "s")

        call_kwargs = mock_http_client.post.call_args[1]
        sent_payload = call_kwargs["content"]
        sent_sig = call_kwargs["headers"]["X-Billing-Signature"]

        expected_sig = sign_payload(sent_payload, saas_app.webhook_secret)
        assert sent_sig == expected_sig


# =========================================================================
# notify_subscription_*
# =========================================================================


def _found(sub):
    result = MagicMock()
    result.scalar_one_or_none.return_value = sub
    return result


@pytest.mark.parametrize(
    ("notify", "event_type"),
    [
        (notify_subscription_created, "subscription.created"),
        (notify_subscription_updated, "subscription.updated"),
        (notify_subscription_deleted, "subscription.deleted"),
    ],
)
class TestNotifySubscription:
    """The three notifications share one payload and differ by their type."""

    async def test_success(self, mock_db, notify, event_type):
        canceled_at = datetime(2025, 3, 15, tzinfo=UTC)
        sub = _make_subscription_mock(
            cancel_at_period_end=True,
            canceled_at=canceled_at,
            limits={"max_seats": 5},
        )
        mock_db.execute.return_value = _found(sub)

        with patch(
            "billing.services.saas_webhook.dispatch_webhook", new_callable=AsyncMock
        ) as mock_dispatch:
            mock_dispatch.return_value = True

            result = await notify(mock_db, sub, "evt_77")

        assert result is True
        args = mock_dispatch.call_args[0]
        assert args[0] is sub.customer.saas_app
        assert args[1] == event_type
        data = args[2]
        assert data["subscription_id"] == "sub-uuid-1"
        assert data["customer_external_id"] == "ext_user_1"
        assert data["status"] == "active"
        assert data["plan_name"] == "Pro Plan"
        assert data["plan_slug"] == "pro"
        assert data["price_id"] == "price-uuid-1"
        assert data["limits"] == {"max_seats": 5}
        assert data["cancel_at_period_end"] is True
        assert data["canceled_at"] == canceled_at
        assert "current_period_start" in data
        assert "current_period_end" in data
        assert args[3] == "evt_77"
        assert args[4] == "sub-uuid-1"

    async def test_not_found_returns_false(self, mock_db, notify, event_type):
        mock_db.execute.return_value = _found(None)
        sub = MagicMock()
        sub.id = "nonexistent"

        assert await notify(mock_db, sub, "evt_1") is False

    async def test_no_customer_returns_false(self, mock_db, notify, event_type):
        sub = _make_subscription_mock(has_customer=False)
        mock_db.execute.return_value = _found(sub)

        assert await notify(mock_db, sub, "evt_1") is False

    async def test_no_price_plan_is_none(self, mock_db, notify, event_type):
        sub = _make_subscription_mock(has_price=False)
        mock_db.execute.return_value = _found(sub)

        with patch(
            "billing.services.saas_webhook.dispatch_webhook", new_callable=AsyncMock
        ) as mock_dispatch:
            await notify(mock_db, sub, "evt_1")

        data = mock_dispatch.call_args[0][2]
        assert data["plan_name"] is None
        assert data["plan_slug"] is None

    async def test_end_to_end_payload_is_signed_and_identified(
        self, mock_db, mock_http_client, notify, event_type
    ):
        """Through the real dispatch: slug, plan slug, price id, limits and event id."""
        sub = _make_subscription_mock(limits={"max_seats": 5})
        sub.customer.saas_app.webhook_url = "https://app.example.com/webhooks"
        sub.customer.saas_app.webhook_secret = "whsec_test"
        mock_db.execute.return_value = _found(sub)
        mock_http_client.post.return_value = _ok_response()

        assert await notify(mock_db, sub, "evt_5") is True

        body = mock_http_client.post.call_args[1]["content"]
        event = json.loads(body)
        assert event["type"] == event_type
        assert event["saas_slug"] == "test-app"
        assert event["id"] == build_event_id("saas-uuid-1", "evt_5", event_type, "sub-uuid-1")
        assert event["data"]["plan_slug"] == "pro"
        assert event["data"]["price_id"] == "price-uuid-1"
        assert event["data"]["limits"] == {"max_seats": 5}
        headers = mock_http_client.post.call_args[1]["headers"]
        assert headers["X-Billing-Signature"] == sign_payload(body, "whsec_test")
