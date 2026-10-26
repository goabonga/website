# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.trust — TrustPolicyService (100% mocked)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.db.models.tenant import TenantTrustMode
from auth.services.trust import TrustPolicyService

from tests.conftest import make_user


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def repo():
    return MagicMock()


@pytest.fixture
def service(repo):
    return TrustPolicyService(repository=repo)


def _make_tenant(trust_mode=TenantTrustMode.NONE, is_active=True, trusted_sources=None):
    t = MagicMock()
    t.id = uuid.uuid4()
    t.slug = "test-tenant"
    t.is_active = is_active
    t.trust_mode = trust_mode
    t.display_name = "Test Tenant"
    t.is_platform = False
    t.trusted_sources = trusted_sources or []
    return t


# ── can_user_access_tenant ───────────────────────────────────────────────────


class TestCanUserAccessTenant:
    @pytest.mark.asyncio
    async def test_tenant_not_found(self, db, service, repo):
        repo.find_tenant_with_trusted_sources = AsyncMock(return_value=None)
        user = make_user()
        ok, err = await service.can_user_access_tenant(db, user, str(uuid.uuid4()))
        assert ok is False
        assert "not found" in err

    @pytest.mark.asyncio
    async def test_tenant_inactive(self, db, service, repo):
        tenant = _make_tenant(is_active=False)
        repo.find_tenant_with_trusted_sources = AsyncMock(return_value=tenant)
        user = make_user()
        ok, err = await service.can_user_access_tenant(db, user, tenant.id)
        assert ok is False
        assert "inactive" in err

    @pytest.mark.asyncio
    async def test_none_mode_registered_user(self, db, service, repo):
        tenant = _make_tenant(trust_mode=TenantTrustMode.NONE)
        user = make_user()
        user.registration_tenant_id = tenant.id
        repo.find_tenant_with_trusted_sources = AsyncMock(return_value=tenant)
        ok, err = await service.can_user_access_tenant(db, user, tenant.id)
        assert ok is True

    @pytest.mark.asyncio
    async def test_none_mode_member(self, db, service, repo):
        tenant = _make_tenant(trust_mode=TenantTrustMode.NONE)
        user = make_user()
        user.registration_tenant_id = uuid.uuid4()  # different tenant
        repo.find_tenant_with_trusted_sources = AsyncMock(return_value=tenant)
        repo.is_member = AsyncMock(return_value=True)
        ok, err = await service.can_user_access_tenant(db, user, tenant.id)
        assert ok is True

    @pytest.mark.asyncio
    async def test_none_mode_denied(self, db, service, repo):
        tenant = _make_tenant(trust_mode=TenantTrustMode.NONE)
        user = make_user()
        user.registration_tenant_id = uuid.uuid4()
        repo.find_tenant_with_trusted_sources = AsyncMock(return_value=tenant)
        repo.is_member = AsyncMock(return_value=False)
        ok, err = await service.can_user_access_tenant(db, user, tenant.id)
        assert ok is False

    @pytest.mark.asyncio
    async def test_all_mode(self, db, service, repo):
        tenant = _make_tenant(trust_mode=TenantTrustMode.ALL)
        user = make_user()
        repo.find_tenant_with_trusted_sources = AsyncMock(return_value=tenant)
        ok, err = await service.can_user_access_tenant(db, user, tenant.id)
        assert ok is True
        assert err is None

    @pytest.mark.asyncio
    async def test_members_only_member(self, db, service, repo):
        tenant = _make_tenant(trust_mode=TenantTrustMode.MEMBERS_ONLY)
        user = make_user()
        repo.find_tenant_with_trusted_sources = AsyncMock(return_value=tenant)
        repo.is_member = AsyncMock(return_value=True)
        ok, err = await service.can_user_access_tenant(db, user, tenant.id)
        assert ok is True

    @pytest.mark.asyncio
    async def test_members_only_denied(self, db, service, repo):
        tenant = _make_tenant(trust_mode=TenantTrustMode.MEMBERS_ONLY)
        user = make_user()
        repo.find_tenant_with_trusted_sources = AsyncMock(return_value=tenant)
        repo.is_member = AsyncMock(return_value=False)
        ok, err = await service.can_user_access_tenant(db, user, tenant.id)
        assert ok is False

    @pytest.mark.asyncio
    async def test_specific_mode_trusted(self, db, service, repo):
        source = MagicMock()
        source.trusted_tenant_id = uuid.uuid4()
        tenant = _make_tenant(
            trust_mode=TenantTrustMode.SPECIFIC,
            trusted_sources=[source],
        )
        user = make_user()
        user.registration_tenant_id = source.trusted_tenant_id
        repo.find_tenant_with_trusted_sources = AsyncMock(return_value=tenant)
        ok, err = await service.can_user_access_tenant(db, user, tenant.id)
        assert ok is True

    @pytest.mark.asyncio
    async def test_specific_mode_member(self, db, service, repo):
        tenant = _make_tenant(trust_mode=TenantTrustMode.SPECIFIC)
        user = make_user()
        user.registration_tenant_id = uuid.uuid4()
        repo.find_tenant_with_trusted_sources = AsyncMock(return_value=tenant)
        repo.is_member = AsyncMock(return_value=True)
        ok, err = await service.can_user_access_tenant(db, user, tenant.id)
        assert ok is True

    @pytest.mark.asyncio
    async def test_specific_mode_denied(self, db, service, repo):
        tenant = _make_tenant(trust_mode=TenantTrustMode.SPECIFIC)
        user = make_user()
        user.registration_tenant_id = uuid.uuid4()
        repo.find_tenant_with_trusted_sources = AsyncMock(return_value=tenant)
        repo.is_member = AsyncMock(return_value=False)
        ok, err = await service.can_user_access_tenant(db, user, tenant.id)
        assert ok is False

    @pytest.mark.asyncio
    async def test_string_tenant_id(self, db, service, repo):
        tenant = _make_tenant(trust_mode=TenantTrustMode.ALL)
        user = make_user()
        repo.find_tenant_with_trusted_sources = AsyncMock(return_value=tenant)
        ok, err = await service.can_user_access_tenant(db, user, str(uuid.uuid4()))
        assert ok is True

    @pytest.mark.asyncio
    async def test_unknown_trust_mode(self, db, service, repo):
        tenant = _make_tenant()
        tenant.trust_mode = "unknown_mode"
        user = make_user()
        repo.find_tenant_with_trusted_sources = AsyncMock(return_value=tenant)
        ok, err = await service.can_user_access_tenant(db, user, tenant.id)
        assert ok is False
        assert "Configuration error" in err


# ── _is_from_trusted_source ──────────────────────────────────────────────────


class TestIsFromTrustedSource:
    def test_user_registration_none(self, service):
        assert service._is_from_trusted_source(None, []) is False

    def test_match(self, service):
        tid = uuid.uuid4()
        source = MagicMock()
        source.trusted_tenant_id = tid
        assert service._is_from_trusted_source(tid, [source]) is True

    def test_no_match(self, service):
        source = MagicMock()
        source.trusted_tenant_id = uuid.uuid4()
        assert service._is_from_trusted_source(uuid.uuid4(), [source]) is False


# ── get_tenant_trust_config ──────────────────────────────────────────────────


class TestGetTenantTrustConfig:
    @pytest.mark.asyncio
    async def test_not_found(self, db, service, repo):
        repo.find_tenant_with_trusted_sources_and_tenants = AsyncMock(return_value=None)
        result = await service.get_tenant_trust_config(db, uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_found_with_sources(self, db, service, repo):
        source = MagicMock()
        source.id = uuid.uuid4()
        source.trusted_tenant_id = uuid.uuid4()
        source.trusted_tenant = MagicMock()
        source.trusted_tenant.display_name = "Trusted Co"
        source.trusted_tenant.slug = "trusted"
        source.trusted_tenant.is_platform = False
        source.description = "Test"

        tenant = _make_tenant(trusted_sources=[source])
        tenant.trust_mode = TenantTrustMode.SPECIFIC
        repo.find_tenant_with_trusted_sources_and_tenants = AsyncMock(return_value=tenant)

        result = await service.get_tenant_trust_config(db, tenant.id)
        assert result is not None
        assert result["trust_mode"] == "specific"
        assert len(result["trusted_sources"]) == 1
        assert result["trusted_sources"][0]["trusted_tenant_name"] == "Trusted Co"

    @pytest.mark.asyncio
    async def test_source_without_tenant(self, db, service, repo):
        source = MagicMock()
        source.id = uuid.uuid4()
        source.trusted_tenant_id = None
        source.trusted_tenant = None
        source.description = None

        tenant = _make_tenant(trusted_sources=[source])
        repo.find_tenant_with_trusted_sources_and_tenants = AsyncMock(return_value=tenant)

        result = await service.get_tenant_trust_config(db, tenant.id)
        assert result["trusted_sources"][0]["trusted_tenant_name"] == "Unknown"


# ── update_trust_mode ────────────────────────────────────────────────────────


class TestUpdateTrustMode:
    @pytest.mark.asyncio
    async def test_success(self, db, service, repo):
        tenant = _make_tenant()
        repo.find_tenant = AsyncMock(return_value=tenant)
        result = await service.update_trust_mode(db, tenant.id, TenantTrustMode.ALL)
        assert result is True
        assert tenant.trust_mode == TenantTrustMode.ALL
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_found(self, db, service, repo):
        repo.find_tenant = AsyncMock(return_value=None)
        result = await service.update_trust_mode(db, uuid.uuid4(), TenantTrustMode.ALL)
        assert result is False


# ── add_trusted_source ───────────────────────────────────────────────────────


class TestAddTrustedSource:
    @pytest.mark.asyncio
    async def test_success(self, db, service, repo):
        repo.find_trusted_source = AsyncMock(return_value=None)
        repo.add = AsyncMock()
        result = await service.add_trusted_source(db, uuid.uuid4(), uuid.uuid4(), "desc")
        assert result is not None
        repo.add.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_already_exists(self, db, service, repo):
        repo.find_trusted_source = AsyncMock(return_value=MagicMock())
        result = await service.add_trusted_source(db, uuid.uuid4(), uuid.uuid4())
        assert result is None


# ── remove_trusted_source ────────────────────────────────────────────────────


class TestRemoveTrustedSource:
    @pytest.mark.asyncio
    async def test_success(self, db, service, repo):
        source = MagicMock()
        repo.find_trusted_source_scoped = AsyncMock(return_value=source)
        repo.delete = AsyncMock()
        result = await service.remove_trusted_source(db, uuid.uuid4(), uuid.uuid4())
        assert result is True
        repo.delete.assert_awaited_once_with(db, source)

    @pytest.mark.asyncio
    async def test_not_found(self, db, service, repo):
        repo.find_trusted_source_scoped = AsyncMock(return_value=None)
        result = await service.remove_trusted_source(db, uuid.uuid4(), uuid.uuid4())
        assert result is False


# ── get_available_tenants_for_trust ──────────────────────────────────────────


class TestGetAvailableTenantsForTrust:
    @pytest.mark.asyncio
    async def test_returns_tenants(self, db, service, repo):
        t1 = MagicMock()
        t1.id = uuid.uuid4()
        t1.slug = "t1"
        t1.display_name = "Tenant 1"
        t1.is_platform = False

        repo.list_trusted_tenant_ids = AsyncMock(return_value=[])
        repo.list_available_tenants = AsyncMock(return_value=[t1])
        result = await service.get_available_tenants_for_trust(db, uuid.uuid4())
        assert len(result) == 1
        assert result[0]["slug"] == "t1"

    @pytest.mark.asyncio
    async def test_excludes_trusted_and_self(self, db, service, repo):
        trusted_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        repo.list_trusted_tenant_ids = AsyncMock(return_value=[trusted_id, None])
        repo.list_available_tenants = AsyncMock(return_value=[])

        result = await service.get_available_tenants_for_trust(db, tenant_id)
        assert result == []

        # Verify list_available_tenants was called with both trusted_id and tenant_id
        called_args = repo.list_available_tenants.await_args
        excluded = called_args.args[1]
        assert trusted_id in excluded
        assert tenant_id in excluded
        assert None not in excluded  # None filtered out


# ── get_platform_tenant ──────────────────────────────────────────────────────


class TestGetPlatformTenant:
    @pytest.mark.asyncio
    async def test_found(self, db, service, repo):
        tenant = _make_tenant()
        repo.find_platform_tenant = AsyncMock(return_value=tenant)
        result = await service.get_platform_tenant(db)
        assert result is tenant

    @pytest.mark.asyncio
    async def test_not_found(self, db, service, repo):
        repo.find_platform_tenant = AsyncMock(return_value=None)
        result = await service.get_platform_tenant(db)
        assert result is None


# ── is_platform_trusted ──────────────────────────────────────────────────────


class TestIsPlatformTrusted:
    @pytest.mark.asyncio
    async def test_no_platform_tenant(self, db, service, repo):
        service.get_platform_tenant = AsyncMock(return_value=None)
        result = await service.is_platform_trusted(db, uuid.uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_platform_trusted(self, db, service, repo):
        platform = _make_tenant()
        service.get_platform_tenant = AsyncMock(return_value=platform)
        repo.platform_source_exists = AsyncMock(return_value=True)
        result = await service.is_platform_trusted(db, uuid.uuid4())
        assert result is True

    @pytest.mark.asyncio
    async def test_platform_not_trusted(self, db, service, repo):
        platform = _make_tenant()
        service.get_platform_tenant = AsyncMock(return_value=platform)
        repo.platform_source_exists = AsyncMock(return_value=False)
        result = await service.is_platform_trusted(db, uuid.uuid4())
        assert result is False
