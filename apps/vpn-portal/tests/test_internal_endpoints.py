# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the internal API used by the OpenVPN hook scripts."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from conftest import authenticated_as
from vpn_portal.auth.models import User
from vpn_portal.db.models import VPNCertificate

BEARER = {"Authorization": "Bearer header.payload.signature"}
CLIENT = {"common_name": "vpn-alice-1", "client_ip": "203.0.113.7"}


@pytest.fixture
def db(use_fake_db):
    return use_fake_db


async def add_certificate(db, *, minutes=10, revoked=False) -> VPNCertificate:
    now = datetime.now(UTC)
    certificate = VPNCertificate(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        username="alice",
        serial_number="serial-1",
        common_name="vpn-alice-1",
        not_before=now - timedelta(minutes=1),
        not_after=now + timedelta(minutes=minutes),
        scopes=["vpn:connect"],
        assigned_routes=["10.8.0.0/24", "10.0.0.0/8"],
        revoked_at=now if revoked else None,
    )
    db.add(certificate)
    await db.commit()
    return certificate


class TestValidate:
    async def test_valid_certificate_returns_its_routes(self, server_client, db):
        await add_certificate(db)

        response = await server_client.post("/api/v1/internal/validate", json=CLIENT)

        assert response.status_code == 200
        assert response.json() == {
            "valid": True,
            "reason": None,
            "routes": ["10.8.0.0/24", "10.0.0.0/8"],
        }

    async def test_unknown_certificate(self, server_client, db):
        response = await server_client.post("/api/v1/internal/validate", json=CLIENT)

        assert response.json() == {"valid": False, "reason": "Certificate not found", "routes": []}

    async def test_revoked_certificate(self, server_client, db):
        await add_certificate(db, revoked=True)

        response = await server_client.post("/api/v1/internal/validate", json=CLIENT)

        assert response.json() == {"valid": False, "reason": "Certificate revoked", "routes": []}

    async def test_expired_certificate(self, server_client, db):
        await add_certificate(db, minutes=-1)

        response = await server_client.post("/api/v1/internal/validate", json=CLIENT)

        assert response.json() == {"valid": False, "reason": "Certificate expired", "routes": []}

    async def test_assigned_ip_is_optional_and_client_ip_required(self, server_client, db):
        response = await server_client.post(
            "/api/v1/internal/validate", json={"common_name": "vpn-alice-1"}
        )

        assert response.status_code == 422


class TestConnect:
    PAYLOAD = CLIENT | {"assigned_ip": "10.8.0.2"}

    async def test_records_the_connection(self, server_client, db):
        await add_certificate(db)

        response = await server_client.post("/api/v1/internal/connect", json=self.PAYLOAD)

        assert response.json() == {"status": "connected"}
        (connection,) = db.rows("vpn_connections")
        assert connection.assigned_ip == "10.8.0.2"
        assert connection.client_ip == "203.0.113.7"

    async def test_unknown_certificate(self, server_client, db):
        response = await server_client.post("/api/v1/internal/connect", json=self.PAYLOAD)

        assert response.status_code == 200
        assert response.json() == {"status": "certificate_not_found"}
        assert db.rows("vpn_connections") == []

    async def test_assigned_ip_is_required(self, server_client, db):
        response = await server_client.post("/api/v1/internal/connect", json=CLIENT)

        assert response.status_code == 422


class TestDisconnect:
    async def test_records_the_disconnection(self, server_client, db):
        await add_certificate(db)
        await server_client.post(
            "/api/v1/internal/connect", json=CLIENT | {"assigned_ip": "10.8.0.2"}
        )

        response = await server_client.post(
            "/api/v1/internal/disconnect",
            json={"common_name": "vpn-alice-1", "bytes_received": 10, "bytes_sent": 20},
        )

        assert response.json() == {"status": "disconnected"}
        (connection,) = db.rows("vpn_connections")
        assert not connection.is_active
        assert (connection.bytes_received, connection.bytes_sent) == (10, 20)

    async def test_without_an_active_connection(self, server_client, db):
        await add_certificate(db)

        response = await server_client.post(
            "/api/v1/internal/disconnect", json={"common_name": "vpn-alice-1"}
        )

        assert response.json() == {"status": "connection_not_found"}

    async def test_unknown_certificate(self, server_client, db):
        response = await server_client.post(
            "/api/v1/internal/disconnect", json={"common_name": "ghost"}
        )

        assert response.json() == {"status": "connection_not_found"}


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("validate", CLIENT),
        ("connect", CLIENT | {"assigned_ip": "10.8.0.2"}),
        ("disconnect", {"common_name": "vpn-alice-1"}),
    ],
)
class TestAccessControl:
    async def test_requires_a_token(self, client, db, path, payload):
        response = await client.post(f"/api/v1/internal/{path}", json=payload)

        assert response.status_code == 401

    async def test_a_regular_user_is_refused(self, client, db, path, payload, test_user):
        with authenticated_as(test_user):
            response = await client.post(f"/api/v1/internal/{path}", json=payload, headers=BEARER)

        assert response.status_code == 403
        assert "vpn:server" in response.json()["detail"]

    async def test_wildcard_scope_is_accepted(self, client, db, path, payload):
        with authenticated_as(User(id="ops", scopes=["vpn:*"], is_machine_client=True)):
            response = await client.post(f"/api/v1/internal/{path}", json=payload, headers=BEARER)

        assert response.status_code == 200
