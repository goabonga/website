# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the admin API: list active sessions and revoke a certificate."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from conftest import authenticated_as
from vpn_portal.core.stepca import StepCAError
from vpn_portal.db.models import VPNCertificate, VPNConnection
from vpn_portal.services.certificate import certificate_service

BEARER = {"Authorization": "Bearer header.payload.signature"}


@pytest.fixture
def db(use_fake_db):
    return use_fake_db


@pytest.fixture
def stepca(monkeypatch):
    mock = AsyncMock()
    monkeypatch.setattr(certificate_service, "stepca", mock)
    return mock


async def add_certificate(db, serial, *, minutes=10, revoked=False, age=0) -> VPNCertificate:
    now = datetime.now(UTC)
    certificate = VPNCertificate(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        username=f"user-{serial}",
        serial_number=serial,
        common_name=f"vpn-{serial}",
        not_before=now - timedelta(minutes=20),
        not_after=now + timedelta(minutes=minutes),
        device_name="laptop",
        scopes=["vpn:connect"],
        assigned_routes=["10.8.0.0/24"],
        revoked_at=now if revoked else None,
        created_at=now - timedelta(minutes=age),
    )
    db.add(certificate)
    await db.commit()
    return certificate


async def add_connection(db, certificate, *, age=1, assigned_ip="10.8.0.2") -> VPNConnection:
    connection = VPNConnection(
        id=uuid.uuid4(),
        certificate_id=certificate.id,
        connected_at=datetime.now(UTC) - timedelta(minutes=age),
        assigned_ip=assigned_ip,
        client_ip="203.0.113.7",
    )
    db.add(connection)
    await db.commit()
    return connection


class TestListSessions:
    async def test_empty(self, admin_client, db):
        response = await admin_client.get("/api/v1/admin/sessions")

        assert response.status_code == 200
        assert response.json() == {"sessions": [], "total": 0, "page": 1, "per_page": 50}

    async def test_lists_active_certificates_only(self, admin_client, db):
        await add_certificate(db, "active")
        await add_certificate(db, "revoked", revoked=True)
        await add_certificate(db, "expired", minutes=-1)

        body = (await admin_client.get("/api/v1/admin/sessions")).json()

        assert body["total"] == 1
        assert [s["certificate_serial"] for s in body["sessions"]] == ["active"]

    async def test_session_fields(self, admin_client, db):
        certificate = await add_certificate(db, "active")
        await add_connection(db, certificate, assigned_ip="10.8.0.9")

        (session,) = (await admin_client.get("/api/v1/admin/sessions")).json()["sessions"]

        assert session["id"] == str(certificate.id)
        assert session["user_id"] == str(certificate.user_id)
        assert session["username"] == "user-active"
        assert session["device_name"] == "laptop"
        assert session["assigned_ip"] == "10.8.0.9"
        assert session["scopes"] == ["vpn:connect"]
        assert session["routes"] == ["10.8.0.0/24"]

    async def test_uses_the_latest_connection(self, admin_client, db):
        certificate = await add_certificate(db, "active")
        await add_connection(db, certificate, age=10, assigned_ip="10.8.0.2")
        await add_connection(db, certificate, age=1, assigned_ip="10.8.0.3")

        (session,) = (await admin_client.get("/api/v1/admin/sessions")).json()["sessions"]

        assert session["assigned_ip"] == "10.8.0.3"

    async def test_without_connection_falls_back_to_issuance(self, admin_client, db):
        certificate = await add_certificate(db, "active")

        (session,) = (await admin_client.get("/api/v1/admin/sessions")).json()["sessions"]

        assert session["assigned_ip"] == "N/A"
        assert session["connected_at"] == certificate.created_at.isoformat().replace("+00:00", "Z")

    async def test_pagination(self, admin_client, db):
        for index in range(5):
            await add_certificate(db, f"s{index}", age=index)

        first = (await admin_client.get("/api/v1/admin/sessions?per_page=2")).json()
        third = (await admin_client.get("/api/v1/admin/sessions?per_page=2&page=3")).json()

        assert first["total"] == 5
        assert [s["certificate_serial"] for s in first["sessions"]] == ["s0", "s1"]
        assert (first["page"], first["per_page"]) == (1, 2)
        assert [s["certificate_serial"] for s in third["sessions"]] == ["s4"]

    @pytest.mark.parametrize("query", ["page=0", "per_page=0", "per_page=101"])
    async def test_invalid_pagination_is_rejected(self, admin_client, db, query):
        assert (await admin_client.get(f"/api/v1/admin/sessions?{query}")).status_code == 422

    async def test_requires_a_token(self, client, db):
        assert (await client.get("/api/v1/admin/sessions")).status_code == 401

    async def test_requires_the_admin_scope(self, auth_client, db):
        response = await auth_client.get("/api/v1/admin/sessions")

        assert response.status_code == 403
        assert "vpn:admin" in response.json()["detail"]

    async def test_wildcard_scope_is_accepted(self, client, db, test_user):
        test_user.scopes = ["vpn:*"]
        with authenticated_as(test_user):
            response = await client.get("/api/v1/admin/sessions", headers=BEARER)

        assert response.status_code == 200


class TestRevokeSession:
    async def test_revokes_the_certificate(self, admin_client, db, stepca):
        certificate = await add_certificate(db, "active")

        response = await admin_client.delete("/api/v1/admin/sessions/active")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "revoked"
        assert body["serial_number"] == "active"
        assert body["revoked_at"] is not None
        assert certificate.is_revoked
        assert certificate.revocation_reason == "admin_revoked"
        stepca.revoke_certificate.assert_awaited_once_with("active")

    async def test_revoked_session_disappears_from_the_list(self, admin_client, db, stepca):
        await add_certificate(db, "active")
        await admin_client.delete("/api/v1/admin/sessions/active")

        assert (await admin_client.get("/api/v1/admin/sessions")).json()["total"] == 0

    async def test_unknown_serial_is_404(self, admin_client, db, stepca):
        response = await admin_client.delete("/api/v1/admin/sessions/nope")

        assert response.status_code == 404
        assert "nope" in response.json()["detail"]
        stepca.revoke_certificate.assert_not_called()

    async def test_ca_outage_still_revokes_locally(self, admin_client, db, stepca):
        certificate = await add_certificate(db, "active")
        stepca.revoke_certificate.side_effect = StepCAError("down")

        response = await admin_client.delete("/api/v1/admin/sessions/active")

        assert response.status_code == 200
        assert certificate.is_revoked

    async def test_requires_a_token(self, client, db):
        assert (await client.delete("/api/v1/admin/sessions/active")).status_code == 401

    async def test_requires_the_admin_scope(self, auth_client, db, stepca):
        await add_certificate(db, "active")

        response = await auth_client.delete("/api/v1/admin/sessions/active")

        assert response.status_code == 403
        stepca.revoke_certificate.assert_not_called()
