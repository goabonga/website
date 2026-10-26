# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.webhook pure helpers (no DB, no HTTP)."""

import hashlib
import hmac
from unittest.mock import patch

import pytest
from auth.services.webhook import (
    WebhookURLError,
    build_envelope,
    build_request_headers,
    compute_matching_patterns,
    generate_secret,
    serialize_body,
    sign_body,
    validate_target_url,
)

# ── compute_matching_patterns ────────────────────────────────────────────────


class TestMatchingPatterns:
    def test_top_level_event(self):
        assert set(compute_matching_patterns("login.success")) == {
            "login.success",
            "login.*",
            "*",
        }

    def test_nested_event(self):
        assert set(compute_matching_patterns("mfa.challenge.failed")) == {
            "mfa.challenge.failed",
            "mfa.challenge.*",
            "mfa.*",
            "*",
        }

    def test_single_token_event(self):
        # ``logout`` has no dot; only exact + global wildcard match.
        assert set(compute_matching_patterns("logout")) == {"logout", "*"}


# ── sign_body ────────────────────────────────────────────────────────────────


class TestSignBody:
    def test_header_format(self):
        header = sign_body("secret", b"{}", 1700000000)
        assert header.startswith("t=1700000000,v1=")

    def test_deterministic(self):
        assert sign_body("secret", b"{}", 1) == sign_body("secret", b"{}", 1)

    def test_different_timestamp_changes_signature(self):
        a = sign_body("secret", b"{}", 1)
        b = sign_body("secret", b"{}", 2)
        assert a != b

    def test_different_body_changes_signature(self):
        a = sign_body("secret", b'{"a":1}', 1)
        b = sign_body("secret", b'{"a":2}', 1)
        assert a != b

    def test_matches_manual_hmac(self):
        body = b'{"k":"v"}'
        ts = 1700000000
        expected = hmac.new(b"secret", f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
        assert sign_body("secret", body, ts) == f"t={ts},v1={expected}"


# ── validate_target_url ──────────────────────────────────────────────────────


class TestValidateTargetURL:
    def test_rejects_non_http_scheme(self):
        with pytest.raises(WebhookURLError, match="scheme"):
            validate_target_url("ftp://example.com/x")

    def test_rejects_missing_host(self):
        with pytest.raises(WebhookURLError):
            validate_target_url("https:///path")

    def test_rejects_loopback(self):
        with patch("auth.services.webhook.settings") as s:
            s.webhook_allow_private_networks = False
            with patch("auth.services.webhook.socket.getaddrinfo") as gai:
                gai.return_value = [(0, 0, 0, "", ("127.0.0.1", 0))]
                with pytest.raises(WebhookURLError, match="private"):
                    validate_target_url("https://localhost/x")

    def test_rejects_rfc1918(self):
        with patch("auth.services.webhook.settings") as s:
            s.webhook_allow_private_networks = False
            with patch("auth.services.webhook.socket.getaddrinfo") as gai:
                gai.return_value = [(0, 0, 0, "", ("10.0.0.5", 0))]
                with pytest.raises(WebhookURLError):
                    validate_target_url("https://internal/x")

    def test_allows_private_with_override(self):
        with patch("auth.services.webhook.settings") as s:
            s.webhook_allow_private_networks = True
            validate_target_url("http://localhost:3000/x")

    def test_accepts_public(self):
        with patch("auth.services.webhook.settings") as s:
            s.webhook_allow_private_networks = False
            with patch("auth.services.webhook.socket.getaddrinfo") as gai:
                gai.return_value = [(0, 0, 0, "", ("93.184.216.34", 0))]
                validate_target_url("https://example.com/hook")

    def test_wraps_dns_failure(self):
        with patch("auth.services.webhook.settings") as s:
            s.webhook_allow_private_networks = False
            with patch("auth.services.webhook.socket.getaddrinfo") as gai:
                import socket as _s

                gai.side_effect = _s.gaierror("nope")
                with pytest.raises(WebhookURLError, match="DNS"):
                    validate_target_url("https://does-not-exist.example")


# ── generate_secret ──────────────────────────────────────────────────────────


class TestGenerateSecret:
    def test_returns_urlsafe_string(self):
        secret = generate_secret()
        assert isinstance(secret, str)
        # 48 bytes base64url-encoded: ~64 characters.
        assert 40 <= len(secret) <= 100

    def test_unique_per_call(self):
        assert generate_secret() != generate_secret()


# ── build_envelope ───────────────────────────────────────────────────────────


class TestBuildEnvelope:
    def test_contains_expected_keys(self):
        import uuid

        delivery_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        env = build_envelope(
            event="user.created",
            tenant_id=tenant_id,
            data={"user_id": "u1"},
            delivery_id=delivery_id,
        )
        assert env["id"] == str(delivery_id)
        assert env["event"] == "user.created"
        assert env["tenant_id"] == str(tenant_id)
        assert env["data"] == {"user_id": "u1"}
        assert "created_at" in env


# ── build_request_headers ────────────────────────────────────────────────────


class TestBuildRequestHeaders:
    def _webhook(self, *, secret="secret", headers=None):
        import uuid
        from types import SimpleNamespace

        return SimpleNamespace(
            id=uuid.uuid4(),
            secret=secret,
            headers=headers or {},
        )

    def test_standard_headers_present(self):
        import uuid

        w = self._webhook()
        delivery_id = uuid.uuid4()
        headers = build_request_headers(
            webhook=w,
            delivery_id=delivery_id,
            event="user.created",
            attempt=1,
            body=b"{}",
            timestamp=42,
        )
        assert headers["Content-Type"] == "application/json"
        assert headers["X-Webhook-Id"] == str(w.id)
        assert headers["X-Webhook-Event"] == "user.created"
        assert headers["X-Webhook-Delivery"] == str(delivery_id)
        assert headers["X-Webhook-Attempt"] == "1"
        assert headers["X-Webhook-Timestamp"] == "42"
        assert headers["X-Webhook-Signature"].startswith("t=42,v1=")

    def test_custom_headers_merged(self):
        import uuid

        w = self._webhook(headers={"X-Custom": "abc"})
        headers = build_request_headers(
            webhook=w,
            delivery_id=uuid.uuid4(),
            event="e",
            attempt=1,
            body=b"{}",
            timestamp=1,
        )
        assert headers["X-Custom"] == "abc"

    def test_custom_headers_cannot_override_reserved(self):
        import uuid

        w = self._webhook(headers={"X-Webhook-Signature": "fake"})
        headers = build_request_headers(
            webhook=w,
            delivery_id=uuid.uuid4(),
            event="e",
            attempt=1,
            body=b"{}",
            timestamp=1,
        )
        assert headers["X-Webhook-Signature"] != "fake"


# ── serialize_body ───────────────────────────────────────────────────────────


class TestSerializeBody:
    def test_canonical_ordering(self):
        assert serialize_body({"b": 2, "a": 1}) == b'{"a":1,"b":2}'

    def test_returns_bytes(self):
        assert isinstance(serialize_body({"a": 1}), bytes)


# ── _is_private_ip ───────────────────────────────────────────────────────────


class TestIsPrivateIp:
    def test_unparseable_address_is_treated_as_private(self):
        """A hostname the resolver hands back that is not an IP fails closed."""
        from auth.services.webhook import _is_private_ip

        assert _is_private_ip("not-an-ip") is True

    def test_public_address(self):
        from auth.services.webhook import _is_private_ip

        assert _is_private_ip("93.184.216.34") is False


# ── WebhookService read helpers ──────────────────────────────────────────────


@pytest.fixture
def service():
    from auth.services.webhook import WebhookService

    return WebhookService()


@pytest.fixture
def db():
    from unittest.mock import AsyncMock, MagicMock

    session = AsyncMock()
    session.add = MagicMock()
    return session


class TestFindMatchingWebhooks:
    @pytest.mark.asyncio
    async def test_expands_event_into_patterns(self, db, service):
        import uuid
        from unittest.mock import AsyncMock

        hooks = [object(), object()]
        service._repository.list_matching_subscribed = AsyncMock(return_value=hooks)
        tenant_id = uuid.uuid4()

        result = await service.find_matching_webhooks(db, tenant_id=tenant_id, event="user.created")

        assert result == hooks
        service._repository.list_matching_subscribed.assert_awaited_once_with(
            db, tenant_id, compute_matching_patterns("user.created")
        )


class TestListAllForTenant:
    @pytest.mark.asyncio
    async def test_delegates_to_repository(self, db, service):
        import uuid
        from unittest.mock import AsyncMock

        hooks = [object()]
        service._repository.list_all_by_tenant = AsyncMock(return_value=hooks)
        tenant_id = uuid.uuid4()

        assert await service.list_all_for_tenant(db, tenant_id=tenant_id) == hooks
        service._repository.list_all_by_tenant.assert_awaited_once_with(db, tenant_id)


class TestListRecentDeliveries:
    @pytest.mark.asyncio
    async def test_delegates_to_repository(self, db, service):
        import uuid
        from unittest.mock import AsyncMock

        deliveries = [object()]
        service._repository.list_recent_deliveries = AsyncMock(return_value=deliveries)
        webhook_id = uuid.uuid4()

        result = await service.list_recent_deliveries(db, webhook_id=webhook_id, limit=5)

        assert result == deliveries
        service._repository.list_recent_deliveries.assert_awaited_once_with(db, webhook_id, limit=5)


# ── WebhookService.dispatch ──────────────────────────────────────────────────


def _make_hook(url="https://hooks.example.com/a"):
    from unittest.mock import MagicMock

    hook = MagicMock()
    hook.id = __import__("uuid").uuid4()
    hook.url = url
    return hook


class TestDispatch:
    @pytest.mark.asyncio
    async def test_no_matching_webhooks_does_no_work(self, db, service):
        import uuid
        from unittest.mock import AsyncMock

        service.find_matching_webhooks = AsyncMock(return_value=[])

        result = await service.dispatch(db, tenant_id=uuid.uuid4(), event="user.created", data={})

        assert result == []
        db.flush.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_stages_deliveries_and_enqueues_tasks(self, db, service):
        import uuid
        from unittest.mock import AsyncMock, MagicMock, patch

        hooks = [_make_hook(), _make_hook("https://hooks.example.com/b")]
        service.find_matching_webhooks = AsyncMock(return_value=hooks)
        service._repository.stage = AsyncMock()

        deliver = MagicMock()
        with (
            patch("auth.services.webhook.validate_target_url"),
            patch.dict(
                "sys.modules",
                {"auth.tasks.webhooks": MagicMock(deliver_webhook=deliver)},
            ),
        ):
            result = await service.dispatch(
                db, tenant_id=uuid.uuid4(), event="user.created", data={"id": "1"}
            )

        assert len(result) == 2
        assert service._repository.stage.await_count == 2
        db.flush.assert_awaited_once()
        assert deliver.delay.call_count == 2

    @pytest.mark.asyncio
    async def test_unsafe_url_is_skipped(self, db, service):
        import uuid
        from unittest.mock import AsyncMock, MagicMock, patch

        from auth.services.webhook import WebhookURLError

        good, bad = _make_hook(), _make_hook("http://127.0.0.1/hook")
        service.find_matching_webhooks = AsyncMock(return_value=[bad, good])
        service._repository.stage = AsyncMock()

        deliver = MagicMock()

        def _validate(url):
            if "127.0.0.1" in url:
                raise WebhookURLError("private address")

        with (
            patch("auth.services.webhook.validate_target_url", side_effect=_validate),
            patch.dict(
                "sys.modules",
                {"auth.tasks.webhooks": MagicMock(deliver_webhook=deliver)},
            ),
        ):
            result = await service.dispatch(
                db, tenant_id=uuid.uuid4(), event="user.created", data={}
            )

        assert len(result) == 1
        service._repository.stage.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_all_urls_unsafe_returns_empty(self, db, service):
        import uuid
        from unittest.mock import AsyncMock, patch

        from auth.services.webhook import WebhookURLError

        service.find_matching_webhooks = AsyncMock(return_value=[_make_hook()])
        service._repository.stage = AsyncMock()

        with patch(
            "auth.services.webhook.validate_target_url",
            side_effect=WebhookURLError("private address"),
        ):
            result = await service.dispatch(
                db, tenant_id=uuid.uuid4(), event="user.created", data={}
            )

        assert result == []
        db.flush.assert_not_awaited()


# ── safe_dispatch ────────────────────────────────────────────────────────────


class TestSafeDispatch:
    @pytest.mark.asyncio
    async def test_none_tenant_is_a_no_op(self, db):
        from unittest.mock import AsyncMock, patch

        from auth.services.webhook import safe_dispatch

        with patch("auth.services.webhook.webhook_service.dispatch", AsyncMock()) as dispatch:
            await safe_dispatch(db, tenant_id=None, event="user.created", data={})

        dispatch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unparseable_tenant_string_is_a_no_op(self, db):
        from unittest.mock import AsyncMock, patch

        from auth.services.webhook import safe_dispatch

        with patch("auth.services.webhook.webhook_service.dispatch", AsyncMock()) as dispatch:
            await safe_dispatch(db, tenant_id="not-a-uuid", event="user.created", data={})

        dispatch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_tenant_string_is_parsed(self, db):
        import uuid
        from unittest.mock import AsyncMock, patch

        from auth.services.webhook import safe_dispatch

        tenant_id = uuid.uuid4()
        with patch("auth.services.webhook.webhook_service.dispatch", AsyncMock()) as dispatch:
            await safe_dispatch(db, tenant_id=str(tenant_id), event="user.created", data={})

        dispatch.assert_awaited_once_with(db, tenant_id=tenant_id, event="user.created", data={})

    @pytest.mark.asyncio
    async def test_enum_event_uses_its_value(self, db):
        import uuid
        from unittest.mock import AsyncMock, patch

        from auth.db.models.tenant import WebhookEvent
        from auth.services.webhook import safe_dispatch

        tenant_id = uuid.uuid4()
        with patch("auth.services.webhook.webhook_service.dispatch", AsyncMock()) as dispatch:
            await safe_dispatch(db, tenant_id=tenant_id, event=WebhookEvent.MEMBER_ADDED, data={})

        assert dispatch.await_args.kwargs["event"] == WebhookEvent.MEMBER_ADDED.value

    @pytest.mark.asyncio
    async def test_dispatch_failure_is_swallowed(self, db):
        import uuid
        from unittest.mock import AsyncMock, patch

        from auth.services.webhook import safe_dispatch

        with patch(
            "auth.services.webhook.webhook_service.dispatch",
            AsyncMock(side_effect=RuntimeError("boom")),
        ):
            await safe_dispatch(db, tenant_id=uuid.uuid4(), event="user.created", data={})
