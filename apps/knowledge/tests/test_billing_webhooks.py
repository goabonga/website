# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for billing webhook routes (knowledge/routes/billing_webhooks.py)."""

import hashlib
import hmac
import json
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from knowledge.database import get_db
from knowledge.main import app
from knowledge.models.enums import PlanType
from knowledge.routes.billing_webhooks import (
    plan_slug_to_plan_type,
    update_tenant_plan,
    verify_signature,
)

# ============================================================
# Helpers
# ============================================================

WEBHOOK_SECRET = "test-webhook-secret"
SAAS_ID = "saas-id-of-this-application"
TENANT_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
MODULE = "knowledge.routes.billing_webhooks"


@pytest.fixture
async def webhook_client(mock_db):
    """Test client for billing webhook (no auth needed)."""

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


def _sign_payload(payload: bytes, secret: str) -> str:
    """Create billing webhook signature."""
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _make_billing_event(
    event_type: str, data: dict, event_id: str = "evt-1", saas_id: str | None = SAAS_ID
) -> dict:
    """Create a billing webhook event."""
    event = {
        "id": event_id,
        "type": event_type,
        "created": "2026-01-01T00:00:00Z",
        "saas_slug": "any-slug",
        "data": data,
    }
    if saas_id is not None:
        event["saas_id"] = saas_id
    return event


def _subscription_data(
    status: str = "active",
    plan_slug: str | None = "pro",
    customer_id: str = TENANT_ID,
    plan_name: str = "Display name",
) -> dict:
    data = {
        "subscription_id": "sub_123",
        "customer_external_id": customer_id,
        "status": status,
        "plan_name": plan_name,
        "limits": {"max_seats": 5},
    }
    if plan_slug is not None:
        data["plan_slug"] = plan_slug
    return data


def _settings(secret: str = WEBHOOK_SECRET, saas_id: str = SAAS_ID) -> MagicMock:
    settings = MagicMock()
    settings.billing_webhook_secret = secret
    settings.billing_saas_id = saas_id
    settings.billing_event_ttl = 600
    return settings


def _session(commit_error: Exception | None = None) -> MagicMock:
    session = MagicMock()
    session.commit = AsyncMock(side_effect=commit_error)
    session.rollback = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


@contextmanager
def _receiver(settings=None, processed=False, commit_error=None):
    """Patch what the webhook route talks to: settings, database, plan update, event store."""
    with (
        patch(f"{MODULE}.get_settings", return_value=settings or _settings()),
        patch(f"{MODULE}.async_session_factory", return_value=_session(commit_error)),
        patch(f"{MODULE}.update_tenant_plan", new=AsyncMock(return_value=True)) as update,
        patch(
            f"{MODULE}.event_dedupe.already_processed", new=AsyncMock(return_value=processed)
        ) as seen,
        patch(f"{MODULE}.event_dedupe.mark_processed", new=AsyncMock()) as mark,
    ):
        yield update, seen, mark


async def _post(client, event: dict, secret: str | None = WEBHOOK_SECRET):
    payload = json.dumps(event).encode()
    headers = {"X-Billing-Signature": _sign_payload(payload, secret)} if secret else {}
    return await client.post("/webhooks/billing", content=payload, headers=headers)


# ============================================================
# Unit tests for helper functions
# ============================================================


def test_verify_signature_valid():
    """Test valid signature verification."""
    payload = b"test payload"
    sig = _sign_payload(payload, WEBHOOK_SECRET)
    assert verify_signature(payload, sig, WEBHOOK_SECRET) is True


def test_verify_signature_invalid():
    """Test invalid signature verification."""
    assert verify_signature(b"test payload", "invalid_sig", WEBHOOK_SECRET) is False


def test_plan_slug_to_plan_type():
    """The plan is identified by its slug, never by its display name."""
    assert plan_slug_to_plan_type("free") == PlanType.FREE
    assert plan_slug_to_plan_type("starter") == PlanType.STARTER
    assert plan_slug_to_plan_type("pro") == PlanType.PRO
    assert plan_slug_to_plan_type("enterprise") == PlanType.ENTERPRISE
    assert plan_slug_to_plan_type(None) is None
    assert plan_slug_to_plan_type("") is None
    assert plan_slug_to_plan_type("unknown") is None
    assert plan_slug_to_plan_type("Pro Plus") is None


@pytest.mark.asyncio
async def test_update_tenant_plan_tenant_not_found():
    """Test update_tenant_plan when tenant is not found in DB."""
    mock_db = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await update_tenant_plan(mock_db, "nonexistent-tenant-id", PlanType.PRO)
    assert result is False


@pytest.mark.asyncio
async def test_update_tenant_plan_sets_the_plan():
    mock_tenant = MagicMock()
    mock_tenant.plan = PlanType.FREE
    mock_db = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_tenant
    mock_db.execute = AsyncMock(return_value=mock_result)

    assert await update_tenant_plan(mock_db, TENANT_ID, PlanType.PRO) is True
    assert mock_tenant.plan == PlanType.PRO


# ============================================================
# Configuration and signature: nothing is accepted without them
# ============================================================


@pytest.mark.asyncio
async def test_webhook_refused_without_secret(webhook_client: AsyncClient):
    """Without BILLING_WEBHOOK_SECRET no event is accepted, even a well formed one."""
    with _receiver(settings=_settings(secret="")) as (update, _seen, _mark):
        response = await _post(
            webhook_client, _make_billing_event("subscription.created", {}), None
        )
    assert response.status_code == 503
    update.assert_not_called()


@pytest.mark.asyncio
async def test_webhook_refused_without_saas_id(webhook_client: AsyncClient):
    """Without BILLING_SAAS_ID the application cannot tell which events are its own."""
    with _receiver(settings=_settings(saas_id="")) as (update, _seen, _mark):
        response = await _post(webhook_client, _make_billing_event("subscription.created", {}))
    assert response.status_code == 503
    update.assert_not_called()


@pytest.mark.asyncio
async def test_webhook_missing_signature(webhook_client: AsyncClient):
    with _receiver() as (update, _seen, _mark):
        response = await _post(
            webhook_client, _make_billing_event("subscription.created", {}), secret=None
        )
    assert response.status_code == 401
    update.assert_not_called()


@pytest.mark.asyncio
async def test_webhook_invalid_signature(webhook_client: AsyncClient):
    with _receiver() as (update, _seen, _mark):
        response = await _post(
            webhook_client,
            _make_billing_event("subscription.created", _subscription_data()),
            secret="another-secret",
        )
    assert response.status_code == 401
    update.assert_not_called()


@pytest.mark.asyncio
async def test_webhook_invalid_payload(webhook_client: AsyncClient):
    payload = b"not valid json"
    with _receiver():
        response = await webhook_client.post(
            "/webhooks/billing",
            content=payload,
            headers={"X-Billing-Signature": _sign_payload(payload, WEBHOOK_SECRET)},
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_webhook_without_event_id_is_invalid(webhook_client: AsyncClient):
    event = _make_billing_event("subscription.created", _subscription_data())
    del event["id"]
    with _receiver() as (update, _seen, _mark):
        response = await _post(webhook_client, event)
    assert response.status_code == 400
    update.assert_not_called()


@pytest.mark.asyncio
async def test_webhook_for_another_saas_is_refused(webhook_client: AsyncClient):
    event = _make_billing_event("subscription.created", _subscription_data(), saas_id="other")
    with _receiver() as (update, _seen, _mark):
        response = await _post(webhook_client, event)
    assert response.status_code == 400
    update.assert_not_called()


# ============================================================
# Events
# ============================================================


@pytest.mark.asyncio
async def test_subscription_created_active_sets_the_plan_from_the_slug(
    webhook_client: AsyncClient,
):
    event = _make_billing_event(
        "subscription.created", _subscription_data(status="active", plan_slug="pro")
    )
    with _receiver() as (update, _seen, mark):
        response = await _post(webhook_client, event)

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert update.await_args.args[1:] == (TENANT_ID, PlanType.PRO)
    mark.assert_awaited_once_with("billing", "evt-1", 600)


@pytest.mark.asyncio
async def test_plan_name_is_ignored(webhook_client: AsyncClient):
    """A plan renamed in billing keeps working: only the slug counts."""
    event = _make_billing_event(
        "subscription.updated",
        _subscription_data(status="active", plan_slug="starter", plan_name="Pro"),
    )
    with _receiver() as (update, _seen, _mark):
        response = await _post(webhook_client, event)

    assert response.status_code == 200
    assert update.await_args.args[2] == PlanType.STARTER


@pytest.mark.asyncio
async def test_subscription_trialing(webhook_client: AsyncClient):
    event = _make_billing_event(
        "subscription.updated", _subscription_data(status="trialing", plan_slug="starter")
    )
    with _receiver() as (update, _seen, _mark):
        response = await _post(webhook_client, event)

    assert response.status_code == 200
    assert update.await_args.args[2] == PlanType.STARTER


@pytest.mark.asyncio
@pytest.mark.parametrize("plan_slug", ["unknown", None])
async def test_subscription_unknown_plan_changes_nothing(webhook_client: AsyncClient, plan_slug):
    event = _make_billing_event(
        "subscription.created", _subscription_data(status="active", plan_slug=plan_slug)
    )
    with _receiver() as (update, _seen, _mark):
        response = await _post(webhook_client, event)

    assert response.status_code == 200
    update.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["canceled", "unpaid", "incomplete_expired"])
async def test_subscription_ended_falls_back_to_free(webhook_client: AsyncClient, status):
    event = _make_billing_event("subscription.updated", _subscription_data(status=status))
    with _receiver() as (update, _seen, _mark):
        response = await _post(webhook_client, event)

    assert response.status_code == 200
    assert update.await_args.args[1:] == (TENANT_ID, PlanType.FREE)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["past_due", "pending"])
async def test_subscription_other_status_keeps_the_plan(webhook_client: AsyncClient, status):
    event = _make_billing_event("subscription.updated", _subscription_data(status=status))
    with _receiver() as (update, _seen, _mark):
        response = await _post(webhook_client, event)

    assert response.status_code == 200
    update.assert_not_called()


@pytest.mark.asyncio
async def test_subscription_deleted_falls_back_to_free(webhook_client: AsyncClient):
    event = _make_billing_event("subscription.deleted", _subscription_data(status="canceled"))
    with _receiver() as (update, _seen, _mark):
        response = await _post(webhook_client, event)

    assert response.status_code == 200
    assert update.await_args.args[1:] == (TENANT_ID, PlanType.FREE)


@pytest.mark.asyncio
async def test_unhandled_event(webhook_client: AsyncClient):
    event = _make_billing_event("invoice.paid", {"subscription_id": "sub_123"})
    with _receiver() as (update, _seen, _mark):
        response = await _post(webhook_client, event)

    assert response.status_code == 200
    update.assert_not_called()


@pytest.mark.asyncio
async def test_event_without_saas_id_is_accepted(webhook_client: AsyncClient):
    event = _make_billing_event("subscription.created", _subscription_data(), saas_id=None)
    with _receiver() as (update, _seen, _mark):
        response = await _post(webhook_client, event)

    assert response.status_code == 200
    update.assert_awaited_once()


# ============================================================
# Idempotency
# ============================================================


@pytest.mark.asyncio
async def test_event_processed_twice_is_applied_once(webhook_client: AsyncClient):
    event = _make_billing_event("subscription.created", _subscription_data())
    with _receiver(processed=True) as (update, seen, mark):
        response = await _post(webhook_client, event)

    assert response.status_code == 200
    assert response.json() == {"status": "duplicate"}
    seen.assert_awaited_once_with("billing", "evt-1")
    update.assert_not_called()
    mark.assert_not_called()


@pytest.mark.asyncio
async def test_failed_event_is_not_recorded_so_billing_can_retry(webhook_client: AsyncClient):
    event = _make_billing_event("subscription.created", _subscription_data())
    with _receiver(commit_error=Exception("DB error")) as (_update, _seen, mark):
        response = await _post(webhook_client, event)

    assert response.status_code == 500
    mark.assert_not_called()
