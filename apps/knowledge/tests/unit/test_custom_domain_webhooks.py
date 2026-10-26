# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the receiver of the custom-domain service webhooks."""

import hashlib
import hmac
import json
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from knowledge.main import app
from knowledge.models.enums import CustomDomainStatus
from knowledge.routes import custom_domain_webhooks as webhooks
from knowledge.routes.custom_domain_webhooks import SignatureError, apply_event, verify_signature

SECRET = "a-webhook-secret-of-at-least-32-characters"
DOMAIN_ID = "6c1a2b3c-0000-4000-8000-000000000001"
ORG_ID = "11111111-1111-1111-1111-111111111111"


def _header(body: bytes, secret: str = SECRET, timestamp: int | None = None) -> str:
    stamp = int(time.time()) if timestamp is None else timestamp
    digest = hmac.new(secret.encode(), str(stamp).encode() + b"." + body, hashlib.sha256)
    return f"t={stamp},v1={digest.hexdigest()}"


class TestVerifySignature:
    def test_valid_signature(self):
        body = b'{"id": "1"}'
        stamp = 1_800_000_000
        assert (
            verify_signature(SECRET, body, _header(body, timestamp=stamp), 300, now=stamp) == stamp
        )

    @pytest.mark.parametrize("header", [None, "", "garbage", "t=abc,v1=00", "v1=00", "t=1"])
    def test_missing_or_malformed_header(self, header):
        with pytest.raises(SignatureError):
            verify_signature(SECRET, b"{}", header, 300)

    def test_wrong_secret(self):
        body = b"{}"
        with pytest.raises(SignatureError, match="Invalid"):
            verify_signature(SECRET, body, _header(body, secret="another-secret"), 300)

    def test_altered_body(self):
        header = _header(b'{"status": "pending"}')
        with pytest.raises(SignatureError, match="Invalid"):
            verify_signature(SECRET, b'{"status": "active"}', header, 300)

    def test_old_delivery_is_a_replay(self):
        body = b"{}"
        header = _header(body, timestamp=1_000)
        with pytest.raises(SignatureError, match="tolerance"):
            verify_signature(SECRET, body, header, 300, now=1_000 + 301)

    def test_delivery_from_the_future_is_refused_too(self):
        body = b"{}"
        header = _header(body, timestamp=10_000)
        with pytest.raises(SignatureError, match="tolerance"):
            verify_signature(SECRET, body, header, 300, now=10_000 - 301)

    def test_tolerance_is_configurable(self):
        body = b"{}"
        header = _header(body, timestamp=1_000)
        assert verify_signature(SECRET, body, header, 600, now=1_500) == 1_000

    def test_rotated_secret_either_signature_matches(self):
        body = b"{}"
        stamp = 5_000
        old = _header(body, secret="the-previous-secret", timestamp=stamp).split(",")[1]
        new = _header(body, timestamp=stamp).split(",")[1]
        assert verify_signature(SECRET, body, f"t={stamp},{old},{new}", 300, now=stamp) == stamp


def _organization(service_id=DOMAIN_ID, **overrides):
    organization = MagicMock()
    organization.id = ORG_ID
    organization.custom_domain = "docs.example.test"
    organization.custom_domain_service_id = service_id
    organization.custom_domain_verified_at = None
    organization.custom_domain_ssl_at = None
    for key, value in overrides.items():
        setattr(organization, key, value)
    return organization


def _db(*found):
    """A session answering the successive lookups with the given workspaces (or None)."""
    db = MagicMock()
    results = []
    for organization in found:
        result = MagicMock()
        result.scalar_one_or_none.return_value = organization
        results.append(result)
    db.execute = AsyncMock(side_effect=results)
    return db


def _event(name="domain.active", status="active", error=None, deliver_id="d-1", **snapshot):
    return {
        "id": deliver_id,
        "event": name,
        "created_at": "2026-03-01T12:00:00+00:00",
        "domain": {
            "id": DOMAIN_ID,
            "domain": "docs.example.test",
            "status": status,
            "client_id": "knowledge",
            "owner_id": ORG_ID,
            "owner_type": "organization",
            "error": error,
            **snapshot,
        },
        "data": {},
    }


class TestApplyEvent:
    async def test_active(self):
        organization = _organization()
        outcome = await apply_event(_db(organization), _event())
        assert outcome == "updated"
        assert organization.custom_domain_status == CustomDomainStatus.ACTIVE
        assert organization.custom_domain_ssl_at == datetime(2026, 3, 1, 12, tzinfo=UTC)

    async def test_status_changed(self):
        organization = _organization()
        await apply_event(
            _db(organization), _event("domain.status_changed", status="dns_verifying")
        )
        assert organization.custom_domain_status == CustomDomainStatus.DNS_VERIFYING

    async def test_failed_with_reason(self):
        organization = _organization()
        await apply_event(
            _db(organization), _event("domain.failed", status="failed", error="CNAME not found")
        )
        assert organization.custom_domain_status == CustomDomainStatus.FAILED
        assert organization.custom_domain_error == "CNAME not found"

    async def test_the_status_is_the_snapshot_so_order_does_not_matter(self):
        organization = _organization()
        db = _db(organization, organization)
        await apply_event(db, _event("domain.active", status="active", deliver_id="2"))
        # a delayed older notification carries the snapshot taken when it was delivered
        await apply_event(db, _event("domain.status_changed", status="active", deliver_id="1"))
        assert organization.custom_domain_status == CustomDomainStatus.ACTIVE

    async def test_deprovisioning_is_not_recorded(self):
        organization = _organization(custom_domain_status=CustomDomainStatus.ACTIVE)
        outcome = await apply_event(
            _db(organization), _event("domain.status_changed", status="deprovisioning")
        )
        assert outcome == "ignored"
        assert organization.custom_domain_status == CustomDomainStatus.ACTIVE

    async def test_deleted_clears_the_workspace(self):
        organization = _organization()
        outcome = await apply_event(
            _db(organization), _event("domain.deleted", status="deprovisioning")
        )
        assert outcome == "cleared"
        assert organization.custom_domain is None
        assert organization.custom_domain_service_id is None

    async def test_deleted_of_a_domain_registered_again_is_ignored(self):
        organization = _organization(service_id="another-id")
        outcome = await apply_event(_db(organization), _event("domain.deleted"))
        assert outcome == "ignored"
        assert organization.custom_domain == "docs.example.test"

    async def test_unknown_workspace(self):
        assert await apply_event(_db(None, None), _event()) == "unknown"

    async def test_found_by_name_and_owner_when_the_id_was_not_recorded(self):
        organization = _organization(service_id=None)
        outcome = await apply_event(_db(None, organization), _event())
        assert outcome == "updated"
        assert organization.custom_domain_service_id == DOMAIN_ID

    async def test_snapshot_without_name_or_owner_cannot_be_matched(self):
        event = _event()
        event["domain"].update(domain="", owner_id="")
        assert await apply_event(_db(None), event) == "unknown"

    @pytest.mark.parametrize("name", ["step_started", "domain.something_new", None])
    async def test_other_events_are_ignored(self, name):
        event = _event()
        event["event"] = name
        assert await apply_event(_db(), event) == "ignored"

    async def test_snapshot_that_is_not_an_object(self):
        event = _event()
        event["domain"] = "nope"
        assert await apply_event(_db(), event) == "ignored"

    async def test_bad_date_falls_back_to_now(self):
        organization = _organization()
        event = _event()
        event["created_at"] = "yesterday-ish"
        await apply_event(_db(organization), event)
        assert organization.custom_domain_checked_at is not None


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@contextmanager
def _receiver(secret=SECRET, processed=False, outcome="updated", commit_error=None):
    settings = MagicMock(
        custom_domain_webhook_secret=secret,
        custom_domain_webhook_tolerance=300,
        custom_domain_event_ttl=600,
    )
    session = MagicMock()
    session.commit = AsyncMock(side_effect=commit_error)
    session.rollback = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    with (
        patch.object(webhooks, "get_settings", return_value=settings),
        patch.object(webhooks, "async_session_factory", return_value=session),
        patch.object(webhooks, "apply_event", new=AsyncMock(return_value=outcome)) as apply,
        patch.object(
            webhooks.event_dedupe, "already_processed", new=AsyncMock(return_value=processed)
        ) as seen,
        patch.object(webhooks.event_dedupe, "mark_processed", new=AsyncMock()) as mark,
    ):
        yield apply, seen, mark


async def _post(client, event=None, body=None, header=None, secret=SECRET, headers=None):
    raw = body if body is not None else json.dumps(event or _event()).encode()
    sent = {webhooks.SIGNATURE_HEADER: header or _header(raw, secret)}
    sent.update(headers or {})
    return await client.post("/webhooks/custom-domain", content=raw, headers=sent)


class TestRoute:
    async def test_refused_without_secret(self, client):
        with _receiver(secret="") as (apply, _seen, _mark):
            response = await _post(client)
        assert response.status_code == 503
        apply.assert_not_called()

    async def test_bad_signature(self, client):
        with _receiver() as (apply, _seen, _mark):
            response = await _post(client, secret="another-secret")
        assert response.status_code == 401
        apply.assert_not_called()

    async def test_missing_signature(self, client):
        with _receiver() as (apply, _seen, _mark):
            response = await client.post("/webhooks/custom-domain", content=b"{}")
        assert response.status_code == 401
        apply.assert_not_called()

    async def test_replayed_old_request(self, client):
        body = json.dumps(_event()).encode()
        with _receiver() as (apply, _seen, _mark):
            response = await _post(client, body=body, header=_header(body, timestamp=1_000))
        assert response.status_code == 401
        apply.assert_not_called()

    async def test_payload_that_is_not_json(self, client):
        with _receiver():
            response = await _post(client, body=b"not json")
        assert response.status_code == 400

    async def test_payload_that_is_not_an_object(self, client):
        with _receiver():
            response = await _post(client, body=b"[1, 2]")
        assert response.status_code == 400

    async def test_payload_without_delivery_id(self, client):
        event = _event()
        del event["id"]
        with _receiver():
            response = await _post(client, event)
        assert response.status_code == 400

    async def test_delivery_id_may_come_from_the_header(self, client):
        event = _event()
        del event["id"]
        with _receiver() as (_apply, seen, _mark):
            response = await _post(client, event, headers={webhooks.DELIVERY_HEADER: "from-header"})
        assert response.status_code == 200
        seen.assert_awaited_once_with("custom-domain", "from-header")

    async def test_accepted_event_is_applied_then_recorded(self, client):
        with _receiver() as (apply, seen, mark):
            response = await _post(client)
        assert response.status_code == 200
        assert response.json() == {"status": "updated"}
        apply.assert_awaited_once()
        seen.assert_awaited_once_with("custom-domain", "d-1")
        mark.assert_awaited_once_with("custom-domain", "d-1", 600)

    async def test_delivery_seen_before_is_not_applied_again(self, client):
        with _receiver(processed=True) as (apply, _seen, mark):
            response = await _post(client)
        assert response.status_code == 200
        assert response.json() == {"status": "duplicate"}
        apply.assert_not_called()
        mark.assert_not_called()

    async def test_failure_is_retryable_because_it_is_not_recorded(self, client):
        with _receiver(commit_error=RuntimeError("db down")) as (_apply, _seen, mark):
            response = await _post(client)
        assert response.status_code == 500
        mark.assert_not_called()
