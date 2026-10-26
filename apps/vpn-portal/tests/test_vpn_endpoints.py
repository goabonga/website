# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the certificate lifecycle endpoints: connect, disconnect and status."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from certs import self_signed_pem
from conftest import authenticated_as
from vpn_portal.auth.models import User
from vpn_portal.core.stepca import CertificateBundle, StepCAError
from vpn_portal.db.models import VPNCertificate
from vpn_portal.services.certificate import certificate_service

BEARER = {"Authorization": "Bearer header.payload.signature"}


@pytest.fixture
def stepca(monkeypatch):
    mock = AsyncMock()

    def bundle(**kwargs):
        now = datetime.now(UTC)
        return CertificateBundle(
            certificate_pem="-----BEGIN CERTIFICATE-----\nCLIENT\n-----END CERTIFICATE-----",
            private_key_pem="-----BEGIN RSA PRIVATE KEY-----\nKEY\n-----END RSA PRIVATE KEY-----",
            ca_certificate_pem=self_signed_pem(),
            serial_number=uuid.uuid4().hex[:12],
            common_name=kwargs["common_name"],
            not_before=now,
            not_after=now + timedelta(minutes=(kwargs["duration_minutes"] or 10)),
        )

    mock.generate_certificate.side_effect = bundle
    monkeypatch.setattr(certificate_service, "stepca", mock)
    monkeypatch.setattr("vpn_portal.core.ovpn.load_ta_key", lambda: "TA-KEY")
    return mock


@pytest.fixture
def db(use_fake_db):
    return use_fake_db


async def add_certificate(db, user: User, minutes: int = 10) -> VPNCertificate:
    now = datetime.now(UTC)
    record = VPNCertificate(
        id=uuid.uuid4(),
        user_id=user.id,
        username=user.name,
        serial_number=uuid.uuid4().hex[:12],
        common_name=f"vpn-{user.id}",
        not_before=now - timedelta(minutes=1),
        not_after=now + timedelta(minutes=minutes),
        scopes=["vpn:connect"],
        assigned_routes=["10.8.0.0/24"],
    )
    db.add(record)
    await db.commit()
    return record


class TestConnect:
    async def test_returns_the_bundle(self, auth_client, db, stepca):
        response = await auth_client.post("/api/v1/vpn/connect")

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {
            "certificate",
            "private_key",
            "ca_certificate",
            "ovpn_config",
            "expires_at",
            "vpn_server",
            "vpn_port",
            "assigned_routes",
        }
        assert body["assigned_routes"] == ["10.8.0.0/24"]
        assert "<tls-auth>\nTA-KEY\n</tls-auth>" in body["ovpn_config"]
        assert len(db.rows("vpn_certificates")) == 1

    async def test_routes_follow_the_scopes(self, auth_client, db, stepca, test_user):
        test_user.scopes.append("vpn:internal")

        with authenticated_as(test_user):
            response = await auth_client.post("/api/v1/vpn/connect")

        assert response.json()["assigned_routes"] == ["10.0.0.0/8", "10.8.0.0/24"]

    async def test_device_name_and_ttl_are_used(self, auth_client, db, stepca):
        response = await auth_client.post(
            "/api/v1/vpn/connect", json={"device_name": "laptop", "certificate_ttl": 600}
        )

        assert response.status_code == 200
        assert db.rows("vpn_certificates")[0].device_name == "laptop"
        assert stepca.generate_certificate.await_args.kwargs["duration_minutes"] == 10

    @pytest.mark.parametrize("ttl", [59, 901])
    async def test_ttl_out_of_range_is_rejected(self, auth_client, db, stepca, ttl):
        response = await auth_client.post("/api/v1/vpn/connect", json={"certificate_ttl": ttl})

        assert response.status_code == 422

    async def test_username_prefers_the_name_claim(self, auth_client, db, stepca):
        await auth_client.post("/api/v1/vpn/connect")

        assert db.rows("vpn_certificates")[0].username == "Test User"

    async def test_failure_is_a_generic_500(self, auth_client, db, stepca):
        stepca.generate_certificate.side_effect = StepCAError("secret detail")

        response = await auth_client.post("/api/v1/vpn/connect")

        assert response.status_code == 500
        assert response.json() == {"detail": "Failed to generate VPN bundle"}
        assert db.rows("vpn_certificates") == []

    async def test_requires_a_token(self, client, db):
        assert (await client.post("/api/v1/vpn/connect")).status_code == 401

    async def test_requires_the_connect_scope(self, client, db):
        with authenticated_as(User(id=uuid.uuid4(), scopes=["openid"])):
            response = await client.post("/api/v1/vpn/connect", headers=BEARER)

        assert response.status_code == 403


class TestDisconnect:
    async def test_revokes_the_active_certificate(self, auth_client, db, stepca, test_user):
        record = await add_certificate(db, test_user)

        response = await auth_client.post("/api/v1/vpn/disconnect")

        assert response.status_code == 200
        assert response.json()["status"] == "disconnected"
        assert response.json()["revoked_at"] is not None
        assert record.is_revoked
        assert record.revocation_reason == "user_requested"
        stepca.revoke_certificate.assert_awaited_once_with(record.serial_number)

    async def test_without_certificate(self, auth_client, db, stepca):
        response = await auth_client.post("/api/v1/vpn/disconnect")

        assert response.json() == {"status": "not_connected", "revoked_at": None}
        stepca.revoke_certificate.assert_not_called()

    async def test_other_users_certificates_are_untouched(self, auth_client, db, stepca):
        other = await add_certificate(db, User(id=uuid.uuid4(), name="Other"))

        response = await auth_client.post("/api/v1/vpn/disconnect")

        assert response.json()["status"] == "not_connected"
        assert not other.is_revoked

    async def test_requires_a_token(self, client, db):
        assert (await client.post("/api/v1/vpn/disconnect")).status_code == 401


class TestStatus:
    async def test_connected(self, auth_client, db, test_user):
        record = await add_certificate(db, test_user)

        response = await auth_client.get("/api/v1/vpn/status")

        assert response.status_code == 200
        body = response.json()
        assert body["connected"] is True
        assert body["certificate_serial"] == record.serial_number
        assert body["common_name"] == record.common_name
        assert body["assigned_routes"] == ["10.8.0.0/24"]

    async def test_not_connected(self, auth_client, db):
        response = await auth_client.get("/api/v1/vpn/status")

        assert response.json() == {
            "connected": False,
            "certificate_serial": None,
            "common_name": None,
            "expires_at": None,
            "assigned_routes": None,
        }

    async def test_expired_certificate_does_not_count(self, auth_client, db, test_user):
        await add_certificate(db, test_user, minutes=-1)

        assert (await auth_client.get("/api/v1/vpn/status")).json()["connected"] is False

    async def test_requires_a_token(self, client, db):
        assert (await client.get("/api/v1/vpn/status")).status_code == 401

    async def test_requires_the_connect_scope(self, client, db):
        with authenticated_as(User(id=uuid.uuid4(), scopes=["openid"])):
            response = await client.get("/api/v1/vpn/status", headers=BEARER)

        assert response.status_code == 403
