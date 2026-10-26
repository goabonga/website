# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for tenant webhook routes and helpers in settings.py."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from tests.conftest import make_execute_result, make_user

MODULE = "auth.api.routes.auth.settings"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def session_service():
    return AsyncMock()


def _mock_request(form_fields=None, cookies=None):
    request = MagicMock()
    request.cookies = cookies or {"session": "good"}
    form = MagicMock()
    form.get = lambda key, default="": (form_fields or {}).get(key, default)

    def getlist(key):
        raw = (form_fields or {}).get(key)
        if raw is None:
            return []
        return raw if isinstance(raw, list) else [raw]

    form.getlist = getlist
    request.form = AsyncMock(return_value=form)
    return request


def _make_webhook(tenant_id=None, events=None, is_active=True, **kw):
    return SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
        name=kw.get("name", "Slack"),
        url=kw.get("url", "https://example.com/hook"),
        events=events or ["user.created"],
        secret=kw.get("secret", "old-secret"),
        headers=kw.get("headers", {}),
        is_active=is_active,
        last_triggered_at=None,
        last_status_code=None,
        last_error=None,
        failure_count=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _make_delivery(webhook_id=None, tenant_id=None, **kw):
    return SimpleNamespace(
        id=uuid.uuid4(),
        webhook_id=webhook_id or uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
        event=kw.get("event", "user.created"),
        status=kw.get("status", "success"),
        attempt=kw.get("attempt", 1),
        max_attempts=kw.get("max_attempts", 5),
        response_status=kw.get("response_status", 200),
        error=kw.get("error"),
        duration_ms=kw.get("duration_ms", 123),
        delivered_at=datetime.now(UTC),
        next_retry_at=None,
        created_at=datetime.now(UTC),
        request_body=kw.get("request_body", {"event": "user.created", "data": {}}),
        request_url=kw.get("request_url", "https://example.com/hook"),
    )


def _patch_require_manager(user, tenant, membership):
    """Replace require_tenant_manager with an AsyncMock returning the triple."""
    return patch(
        f"{MODULE}.require_tenant_manager",
        AsyncMock(return_value=(user, tenant, membership)),
    )


# ---------------------------------------------------------------------------
# _sanitize_events
# ---------------------------------------------------------------------------


class TestSanitizeEvents:
    def test_keeps_exact_match(self):
        from auth.api.routes.auth.settings import _sanitize_events

        assert _sanitize_events(["user.created"]) == ["user.created"]

    def test_keeps_group_wildcard(self):
        from auth.api.routes.auth.settings import _sanitize_events

        assert _sanitize_events(["user.*"]) == ["user.*"]

    def test_keeps_global_wildcard(self):
        from auth.api.routes.auth.settings import _sanitize_events

        assert _sanitize_events(["*"]) == ["*"]

    def test_rejects_unknown_event(self):
        from auth.api.routes.auth.settings import _sanitize_events

        assert _sanitize_events(["fake.event"]) == []

    def test_rejects_unknown_group_wildcard(self):
        from auth.api.routes.auth.settings import _sanitize_events

        assert _sanitize_events(["notarealgroup.*"]) == []

    def test_dedupes(self):
        from auth.api.routes.auth.settings import _sanitize_events

        assert _sanitize_events(["user.created", "user.created"]) == ["user.created"]

    def test_keeps_nested_wildcard(self):
        from auth.api.routes.auth.settings import _sanitize_events

        # ``mfa.challenge.*`` matches real mfa.challenge.success/failed events.
        assert _sanitize_events(["mfa.challenge.*"]) == ["mfa.challenge.*"]


# ---------------------------------------------------------------------------
# _build_webhook_events_by_group
# ---------------------------------------------------------------------------


class TestBuildEventsByGroup:
    def test_groups_exist(self):
        from auth.api.routes.auth.settings import _build_webhook_events_by_group

        groups = _build_webhook_events_by_group()
        assert "user" in groups
        assert "login" in groups
        assert "mfa" in groups

    def test_events_are_sorted(self):
        from auth.api.routes.auth.settings import _build_webhook_events_by_group

        groups = _build_webhook_events_by_group()
        for events in groups.values():
            assert events == sorted(events)


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


class TestWebhookToDict:
    def test_basic_fields(self):
        from auth.api.routes.auth.settings import webhook_to_dict

        w = _make_webhook(events=["user.*", "login.success"])
        out = webhook_to_dict(w)
        assert out["events"] == ["user.*", "login.success"]
        assert out["is_active"] is True
        assert out["recent_deliveries"] == []

    def test_embeds_recent_deliveries(self):
        from auth.api.routes.auth.settings import webhook_to_dict

        w = _make_webhook()
        deliveries = [_make_delivery(webhook_id=w.id)]
        out = webhook_to_dict(w, deliveries)
        assert len(out["recent_deliveries"]) == 1
        assert out["recent_deliveries"][0]["response_status"] == 200


class TestDeliveryToDict:
    def test_enum_status_serialized(self):
        from auth.api.routes.auth.settings import webhook_delivery_to_dict
        from auth.db.models.tenant import WebhookDeliveryStatus

        d = _make_delivery(status=WebhookDeliveryStatus.RETRYING)
        out = webhook_delivery_to_dict(d)
        assert out["status"] == "retrying"

    def test_string_status_passthrough(self):
        from auth.api.routes.auth.settings import webhook_delivery_to_dict

        d = _make_delivery(status="failed")
        out = webhook_delivery_to_dict(d)
        assert out["status"] == "failed"


# ---------------------------------------------------------------------------
# Route: create webhook
# ---------------------------------------------------------------------------


class TestCreateWebhook:
    async def test_requires_name(self, db, session_service):
        from auth.api.routes.auth.settings import org_webhook_create_submit

        tenant = MagicMock(id=uuid.uuid4())
        with _patch_require_manager(make_user(), tenant, MagicMock()):
            request = _mock_request(form_fields={"name": "", "url": "https://x.example"})
            resp = await org_webhook_create_submit(request, str(tenant.id), db, session_service)
        assert "error" in str(resp.headers.get("location", "")).lower()

    async def test_rejects_empty_events(self, db, session_service):
        from auth.api.routes.auth.settings import org_webhook_create_submit

        tenant = MagicMock(id=uuid.uuid4())
        with _patch_require_manager(make_user(), tenant, MagicMock()):
            request = _mock_request(
                form_fields={
                    "name": "Slack",
                    "url": "https://example.com/hook",
                    "events": [],
                }
            )
            with patch(f"{MODULE}.webhook_validate_target_url"):
                resp = await org_webhook_create_submit(request, str(tenant.id), db, session_service)
        assert "event" in str(resp.headers.get("location", "")).lower()

    async def test_rejects_invalid_url(self, db, session_service):
        from auth.api.routes.auth.settings import org_webhook_create_submit
        from auth.services.webhook import WebhookURLError

        tenant = MagicMock(id=uuid.uuid4())
        with _patch_require_manager(make_user(), tenant, MagicMock()):
            request = _mock_request(
                form_fields={
                    "name": "Slack",
                    "url": "http://10.0.0.1/x",
                    "events": ["user.created"],
                }
            )
            with patch(
                f"{MODULE}.webhook_validate_target_url",
                side_effect=WebhookURLError("private"),
            ):
                resp = await org_webhook_create_submit(request, str(tenant.id), db, session_service)
        assert "private" in str(resp.headers.get("location", "")).lower()

    async def test_happy_path_creates_and_commits(self, db, session_service):
        from auth.api.routes.auth.settings import org_webhook_create_submit

        tenant = MagicMock(id=uuid.uuid4())
        with _patch_require_manager(make_user(), tenant, MagicMock()):
            request = _mock_request(
                form_fields={
                    "name": "Slack",
                    "url": "https://example.com/hook",
                    "events": ["user.created", "login.success"],
                }
            )
            with patch(f"{MODULE}.webhook_validate_target_url"):
                resp = await org_webhook_create_submit(request, str(tenant.id), db, session_service)
        db.add.assert_called_once()
        db.commit.assert_awaited()
        assert "success" in str(resp.headers.get("location", "")).lower()


# ---------------------------------------------------------------------------
# Route: toggle
# ---------------------------------------------------------------------------


class TestToggleWebhook:
    async def test_flips_is_active(self, db, session_service):
        from auth.api.routes.auth.settings import org_webhook_toggle

        tenant = MagicMock(id=uuid.uuid4())
        webhook = _make_webhook(is_active=True)
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=webhook))
        with _patch_require_manager(make_user(), tenant, MagicMock()):
            request = _mock_request()
            resp = await org_webhook_toggle(
                request, str(tenant.id), str(webhook.id), db, session_service
            )
        assert webhook.is_active is False
        db.commit.assert_awaited()
        assert resp.status_code in (302, 303)

    async def test_unknown_webhook_errors_out(self, db, session_service):
        from auth.api.routes.auth.settings import org_webhook_toggle

        tenant = MagicMock(id=uuid.uuid4())
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        with _patch_require_manager(make_user(), tenant, MagicMock()):
            request = _mock_request()
            resp = await org_webhook_toggle(
                request, str(tenant.id), str(uuid.uuid4()), db, session_service
            )
        assert (
            "not+found" in str(resp.headers.get("location", "")).lower()
            or "not%20found" in str(resp.headers.get("location", "")).lower()
        )


# ---------------------------------------------------------------------------
# Route: delete
# ---------------------------------------------------------------------------


class TestDeleteWebhook:
    async def test_deletes_and_commits(self, db, session_service):
        from auth.api.routes.auth.settings import org_webhook_delete

        tenant = MagicMock(id=uuid.uuid4())
        webhook = _make_webhook()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=webhook))
        with _patch_require_manager(make_user(), tenant, MagicMock()):
            request = _mock_request()
            await org_webhook_delete(request, str(tenant.id), str(webhook.id), db, session_service)
        db.delete.assert_awaited_once_with(webhook)
        db.commit.assert_awaited()


# ---------------------------------------------------------------------------
# Route: rotate-secret
# ---------------------------------------------------------------------------


class TestRotateSecret:
    async def test_replaces_secret_and_commits(self, db, session_service):
        from auth.api.routes.auth.settings import org_webhook_rotate_secret

        tenant = MagicMock(id=uuid.uuid4())
        webhook = _make_webhook(secret="old")
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=webhook))
        with _patch_require_manager(make_user(), tenant, MagicMock()):
            request = _mock_request()
            await org_webhook_rotate_secret(
                request, str(tenant.id), str(webhook.id), db, session_service
            )
        assert webhook.secret != "old"
        db.commit.assert_awaited()


# ---------------------------------------------------------------------------
# Route: test (ping)
# ---------------------------------------------------------------------------


class TestWebhookPing:
    async def test_enqueues_delivery(self, db, session_service):
        from auth.api.routes.auth.settings import org_webhook_test

        tenant = MagicMock(id=uuid.uuid4())
        webhook = _make_webhook()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=webhook))

        with (
            _patch_require_manager(make_user(), tenant, MagicMock()),
            patch(f"{MODULE}.webhook_validate_target_url"),
            patch("auth.tasks.webhooks.deliver_webhook") as deliver,
        ):
            request = _mock_request()
            resp = await org_webhook_test(
                request, str(tenant.id), str(webhook.id), db, session_service
            )

        db.add.assert_called_once()
        db.commit.assert_awaited()
        deliver.delay.assert_called_once()
        assert "success" in str(resp.headers.get("location", "")).lower()

    async def test_rejects_unsafe_url(self, db, session_service):
        from auth.api.routes.auth.settings import org_webhook_test
        from auth.services.webhook import WebhookURLError

        tenant = MagicMock(id=uuid.uuid4())
        webhook = _make_webhook()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=webhook))
        with (
            _patch_require_manager(make_user(), tenant, MagicMock()),
            patch(
                f"{MODULE}.webhook_validate_target_url",
                side_effect=WebhookURLError("private"),
            ),
        ):
            request = _mock_request()
            resp = await org_webhook_test(
                request, str(tenant.id), str(webhook.id), db, session_service
            )
        assert "private" in str(resp.headers.get("location", "")).lower()


# ---------------------------------------------------------------------------
# Route: replay
# ---------------------------------------------------------------------------


class TestReplayDelivery:
    async def test_clones_envelope_into_new_delivery(self, db, session_service):
        from auth.api.routes.auth.settings import org_webhook_replay_delivery

        tenant = MagicMock(id=uuid.uuid4())
        webhook = _make_webhook()
        original = _make_delivery(webhook_id=webhook.id, tenant_id=tenant.id)

        # First execute() returns the webhook, second returns the original delivery
        results = [
            make_execute_result(scalar_value=webhook),
            make_execute_result(scalar_value=original),
        ]
        db.execute = AsyncMock(side_effect=results)

        with (
            _patch_require_manager(make_user(), tenant, MagicMock()),
            patch("auth.tasks.webhooks.deliver_webhook") as deliver,
        ):
            request = _mock_request()
            resp = await org_webhook_replay_delivery(
                request,
                str(tenant.id),
                str(webhook.id),
                str(original.id),
                db,
                session_service,
            )

        db.add.assert_called_once()
        db.commit.assert_awaited()
        deliver.delay.assert_called_once()
        assert "success" in str(resp.headers.get("location", "")).lower()

    async def test_missing_delivery_errors(self, db, session_service):
        from auth.api.routes.auth.settings import org_webhook_replay_delivery

        tenant = MagicMock(id=uuid.uuid4())
        webhook = _make_webhook()
        results = [
            make_execute_result(scalar_value=webhook),
            make_execute_result(scalar_value=None),
        ]
        db.execute = AsyncMock(side_effect=results)

        with _patch_require_manager(make_user(), tenant, MagicMock()):
            request = _mock_request()
            resp = await org_webhook_replay_delivery(
                request,
                str(tenant.id),
                str(webhook.id),
                str(uuid.uuid4()),
                db,
                session_service,
            )
        assert (
            "not+found" in str(resp.headers.get("location", "")).lower()
            or "not%20found" in str(resp.headers.get("location", "")).lower()
        )


# Silence unused import warnings for HTTPException used in other test fixtures.
_ = HTTPException
