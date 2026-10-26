# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for connection tracking in CertificateService (in-memory database)."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from vpn_portal.db.models import VPNCertificate, VPNConnection
from vpn_portal.services.certificate import CertificateService


@pytest.fixture
def service():
    return CertificateService(stepca=AsyncMock())


async def add_certificate(db, common_name="vpn-alice-1") -> VPNCertificate:
    now = datetime.now(UTC)
    certificate = VPNCertificate(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        username="alice",
        serial_number=f"serial-{common_name}",
        common_name=common_name,
        not_before=now,
        not_after=now + timedelta(minutes=10),
        scopes=[],
        assigned_routes=[],
    )
    db.add(certificate)
    await db.commit()
    return certificate


class TestGetCertificateByCommonName:
    async def test_finds_the_certificate(self, service, fake_db):
        certificate = await add_certificate(fake_db)

        assert await service.get_certificate_by_cn(fake_db, "vpn-alice-1") is certificate

    async def test_unknown_common_name(self, service, fake_db):
        await add_certificate(fake_db)

        assert await service.get_certificate_by_cn(fake_db, "vpn-bob-1") is None


class TestRecordConnection:
    async def test_records_the_connection(self, service, fake_db):
        certificate = await add_certificate(fake_db)

        connection = await service.record_connection(
            fake_db, "vpn-alice-1", "203.0.113.7", "10.8.0.2"
        )

        assert fake_db.rows("vpn_connections") == [connection]
        assert connection.certificate_id == certificate.id
        assert connection.client_ip == "203.0.113.7"
        assert connection.assigned_ip == "10.8.0.2"
        assert connection.is_active
        assert abs((datetime.now(UTC) - connection.connected_at).total_seconds()) < 5

    async def test_unknown_certificate_records_nothing(self, service, fake_db):
        result = await service.record_connection(fake_db, "ghost", "203.0.113.7", "10.8.0.2")

        assert result is None
        assert fake_db.rows("vpn_connections") == []


class TestRecordDisconnection:
    async def connect(self, service, db, common_name="vpn-alice-1"):
        return await service.record_connection(db, common_name, "203.0.113.7", "10.8.0.2")

    async def test_closes_the_active_connection(self, service, fake_db):
        await add_certificate(fake_db)
        connection = await self.connect(service, fake_db)

        result = await service.record_disconnection(
            fake_db, "vpn-alice-1", bytes_received=1000, bytes_sent=2000
        )

        assert result is connection
        assert not connection.is_active
        assert connection.bytes_received == 1000
        assert connection.bytes_sent == 2000
        assert connection.duration_seconds is not None

    async def test_counters_default_to_zero(self, service, fake_db):
        await add_certificate(fake_db)
        connection = await self.connect(service, fake_db)

        await service.record_disconnection(fake_db, "vpn-alice-1")

        assert (connection.bytes_received, connection.bytes_sent) == (0, 0)

    async def test_unknown_certificate(self, service, fake_db):
        assert await service.record_disconnection(fake_db, "ghost") is None

    async def test_no_active_connection(self, service, fake_db):
        await add_certificate(fake_db)

        assert await service.record_disconnection(fake_db, "vpn-alice-1") is None

    async def test_only_the_latest_open_connection_is_closed(self, service, fake_db):
        await add_certificate(fake_db)
        first = await self.connect(service, fake_db)
        first.connected_at -= timedelta(minutes=5)
        second = await self.connect(service, fake_db)

        closed = await service.record_disconnection(fake_db, "vpn-alice-1")

        assert closed is second
        assert first.is_active

    async def test_already_closed_connection_is_not_closed_twice(self, service, fake_db):
        await add_certificate(fake_db)
        await self.connect(service, fake_db)
        await service.record_disconnection(fake_db, "vpn-alice-1")

        assert await service.record_disconnection(fake_db, "vpn-alice-1") is None

    async def test_connections_of_other_certificates_are_untouched(self, service, fake_db):
        await add_certificate(fake_db, "vpn-alice-1")
        await add_certificate(fake_db, "vpn-bob-1")
        bob = await self.connect(service, fake_db, "vpn-bob-1")

        assert await service.record_disconnection(fake_db, "vpn-alice-1") is None
        assert isinstance(bob, VPNConnection)
        assert bob.is_active
