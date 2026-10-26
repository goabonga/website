# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for CertificateService with an in-memory database and a fake Step-CA."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from certs import self_signed_pem
from vpn_portal.core.stepca import CertificateBundle, StepCAError
from vpn_portal.services import certificate as service_module
from vpn_portal.services.certificate import CertificateService, certificate_service

USER_ID = str(uuid.uuid4())


def make_bundle(common_name: str = "vpn-cn", serial: str = "abc123", minutes: int = 10):
    now = datetime.now(UTC)
    return CertificateBundle(
        certificate_pem="-----BEGIN CERTIFICATE-----\nCLIENT\n-----END CERTIFICATE-----",
        private_key_pem="-----BEGIN RSA PRIVATE KEY-----\nKEY\n-----END RSA PRIVATE KEY-----",
        ca_certificate_pem=self_signed_pem(),
        serial_number=serial,
        common_name=common_name,
        not_before=now,
        not_after=now + timedelta(minutes=minutes),
    )


@pytest.fixture
def stepca():
    mock = AsyncMock()
    mock.generate_certificate.side_effect = lambda **kwargs: make_bundle(kwargs["common_name"])
    return mock


@pytest.fixture
def service(stepca):
    return CertificateService(stepca=stepca)


@pytest.fixture(autouse=True)
def ta_key(monkeypatch):
    monkeypatch.setattr("vpn_portal.core.ovpn.load_ta_key", lambda: "TA-KEY")


def test_default_service_uses_the_shared_stepca_client():
    assert certificate_service.stepca is service_module.stepca_client


class TestCommonName:
    def test_format(self, service):
        common_name = service._generate_common_name(USER_ID)

        prefix, _, timestamp = common_name.rpartition("-")
        assert prefix == f"vpn-{USER_ID}"
        assert abs(int(timestamp) - datetime.now(UTC).timestamp()) < 5


class TestRouteResolution:
    def test_defaults_without_scopes(self, service):
        assert service._resolve_routes([]) == ["10.8.0.0/24"]

    def test_unknown_scopes_only_get_default_routes(self, service):
        assert service._resolve_routes(["openid", "profile"]) == ["10.8.0.0/24"]

    def test_scope_adds_its_routes(self, service):
        assert service._resolve_routes(["vpn:internal"]) == ["10.0.0.0/8", "10.8.0.0/24"]

    def test_routes_are_merged_deduplicated_and_sorted(self, service):
        routes = service._resolve_routes(["vpn:production", "vpn:infrastructure", "vpn:connect"])

        assert routes == ["10.200.0.0/16", "10.8.0.0/24", "192.168.0.0/16"]

    def test_wildcard_entry_in_the_mapping(self, service, monkeypatch):
        monkeypatch.setattr(service_module.settings, "scope_routes", {"vpn:*": ["172.16.0.0/12"]})

        assert service._resolve_routes(["vpn:anything"]) == ["10.8.0.0/24", "172.16.0.0/12"]


class TestIssueCertificate:
    async def test_persists_and_returns_the_bundle(self, service, stepca, fake_db):
        record, ovpn_config, bundle = await service.issue_certificate(
            fake_db,
            user_id=USER_ID,
            username="user@example.com",
            scopes=["vpn:connect", "vpn:internal"],
            device_name="laptop",
            duration_minutes=5,
        )

        assert fake_db.rows("vpn_certificates") == [record]
        assert record.user_id == uuid.UUID(USER_ID)
        assert record.username == "user@example.com"
        assert record.serial_number == bundle.serial_number == "abc123"
        assert record.common_name == bundle.common_name
        assert record.device_name == "laptop"
        assert record.scopes == ["vpn:connect", "vpn:internal"]
        assert record.assigned_routes == ["10.0.0.0/8", "10.8.0.0/24"]
        assert record.not_after == bundle.not_after
        assert "<tls-auth>\nTA-KEY\n</tls-auth>" in ovpn_config
        assert bundle.private_key_pem in ovpn_config

    async def test_email_usernames_become_the_san(self, service, stepca, fake_db):
        await service.issue_certificate(fake_db, USER_ID, "user@example.com", ["vpn:connect"])

        kwargs = stepca.generate_certificate.await_args.kwargs
        assert kwargs["san_email"] == "user@example.com"
        assert kwargs["common_name"].startswith(f"vpn-{USER_ID}-")

    async def test_plain_usernames_have_no_san(self, service, stepca, fake_db):
        await service.issue_certificate(fake_db, USER_ID, "alice", ["vpn:connect"])

        assert stepca.generate_certificate.await_args.kwargs["san_email"] is None

    async def test_duration_is_forwarded(self, service, stepca, fake_db):
        await service.issue_certificate(
            fake_db, USER_ID, "alice", ["vpn:connect"], duration_minutes=7
        )

        assert stepca.generate_certificate.await_args.kwargs["duration_minutes"] == 7

    async def test_ca_failure_leaves_nothing_behind(self, service, stepca, fake_db):
        stepca.generate_certificate.side_effect = StepCAError("down")

        with pytest.raises(StepCAError):
            await service.issue_certificate(fake_db, USER_ID, "alice", ["vpn:connect"])

        assert fake_db.rows("vpn_certificates") == []


class TestRevokeCertificate:
    async def issue(self, service, fake_db):
        record, _, _ = await service.issue_certificate(fake_db, USER_ID, "alice", ["vpn:connect"])
        return record

    async def test_marks_the_certificate_revoked(self, service, stepca, fake_db):
        record = await self.issue(service, fake_db)

        revoked = await service.revoke_certificate(fake_db, record.serial_number, reason="admin")

        assert revoked is record
        assert record.is_revoked
        assert record.revocation_reason == "admin"
        stepca.revoke_certificate.assert_awaited_once_with(record.serial_number)

    async def test_default_reason(self, service, fake_db):
        record = await self.issue(service, fake_db)

        await service.revoke_certificate(fake_db, record.serial_number)

        assert record.revocation_reason == "user_requested"

    async def test_unknown_serial_returns_none(self, service, stepca, fake_db):
        assert await service.revoke_certificate(fake_db, "missing") is None
        stepca.revoke_certificate.assert_not_called()

    async def test_ca_failure_does_not_prevent_database_revocation(self, service, stepca, fake_db):
        record = await self.issue(service, fake_db)
        stepca.revoke_certificate.side_effect = StepCAError("ca down")

        revoked = await service.revoke_certificate(fake_db, record.serial_number)

        assert revoked.is_revoked


class TestActiveCertificate:
    async def add(self, db, serial, user_id=USER_ID, minutes=10, revoked=False, age=0):
        from vpn_portal.db.models import VPNCertificate

        now = datetime.now(UTC)
        db.add(
            VPNCertificate(
                id=uuid.uuid4(),
                user_id=uuid.UUID(user_id),
                username="alice",
                serial_number=serial,
                common_name=f"cn-{serial}",
                not_before=now - timedelta(minutes=20),
                not_after=now + timedelta(minutes=minutes),
                scopes=[],
                assigned_routes=[],
                revoked_at=now if revoked else None,
                created_at=now - timedelta(minutes=age),
            )
        )
        await db.commit()

    async def test_returns_the_valid_certificate(self, service, fake_db):
        await self.add(fake_db, "ok")

        found = await service.get_user_active_certificate(fake_db, USER_ID)

        assert found.serial_number == "ok"

    async def test_ignores_revoked_expired_and_foreign_certificates(self, service, fake_db):
        await self.add(fake_db, "revoked", revoked=True)
        await self.add(fake_db, "expired", minutes=-1)
        await self.add(fake_db, "other-user", user_id=str(uuid.uuid4()))

        assert await service.get_user_active_certificate(fake_db, USER_ID) is None

    async def test_returns_the_most_recent_one(self, service, fake_db):
        await self.add(fake_db, "old", age=5)
        await self.add(fake_db, "new", age=1)

        assert (await service.get_user_active_certificate(fake_db, USER_ID)).serial_number == "new"
