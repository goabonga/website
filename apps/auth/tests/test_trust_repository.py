# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.repositories.trust — TrustRepository (100% mocked)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.db.repositories.trust import TrustRepository

from tests.conftest import make_execute_result


def make_list_result(rows: list) -> MagicMock:
    """Build a Result mock where ``.scalars().all()`` returns ``rows``."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    result.scalars.return_value = scalars
    return result


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def repo():
    return TrustRepository()


# ── find_tenant_with_trusted_sources ─────────────────────────────────────────


class TestFindTenantWithTrustedSources:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        tenant = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))

        result = await repo.find_tenant_with_trusted_sources(db, uuid.uuid4())
        assert result is tenant

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_tenant_with_trusted_sources(db, uuid.uuid4())
        assert result is None


# ── find_tenant_with_trusted_sources_and_tenants ─────────────────────────────


class TestFindTenantWithTrustedSourcesAndTenants:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        tenant = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))

        result = await repo.find_tenant_with_trusted_sources_and_tenants(db, uuid.uuid4())
        assert result is tenant

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_tenant_with_trusted_sources_and_tenants(db, uuid.uuid4())
        assert result is None


# ── find_tenant ──────────────────────────────────────────────────────────────


class TestFindTenant:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        tenant = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))

        result = await repo.find_tenant(db, uuid.uuid4())
        assert result is tenant

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_tenant(db, uuid.uuid4())
        assert result is None


# ── find_platform_tenant ─────────────────────────────────────────────────────


class TestFindPlatformTenant:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        tenant = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))

        result = await repo.find_platform_tenant(db)
        assert result is tenant

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_platform_tenant(db)
        assert result is None


# ── list_available_tenants ───────────────────────────────────────────────────


class TestListAvailableTenants:
    @pytest.mark.asyncio
    async def test_returns_list(self, db, repo):
        t1, t2 = MagicMock(), MagicMock()
        db.execute = AsyncMock(return_value=make_list_result([t1, t2]))

        result = await repo.list_available_tenants(db, {uuid.uuid4()})
        assert result == [t1, t2]

    @pytest.mark.asyncio
    async def test_empty(self, db, repo):
        db.execute = AsyncMock(return_value=make_list_result([]))

        result = await repo.list_available_tenants(db, set())
        assert result == []


# ── is_member ────────────────────────────────────────────────────────────────


class TestIsMember:
    @pytest.mark.asyncio
    async def test_member(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=uuid.uuid4()))

        result = await repo.is_member(db, uuid.uuid4(), uuid.uuid4())
        assert result is True

    @pytest.mark.asyncio
    async def test_not_member(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.is_member(db, uuid.uuid4(), uuid.uuid4())
        assert result is False


# ── find_trusted_source ──────────────────────────────────────────────────────


class TestFindTrustedSource:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        source = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=source))

        result = await repo.find_trusted_source(db, uuid.uuid4(), uuid.uuid4())
        assert result is source

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_trusted_source(db, uuid.uuid4(), uuid.uuid4())
        assert result is None


# ── find_trusted_source_scoped ───────────────────────────────────────────────


class TestFindTrustedSourceScoped:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        source = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=source))

        result = await repo.find_trusted_source_scoped(db, uuid.uuid4(), uuid.uuid4())
        assert result is source

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_trusted_source_scoped(db, uuid.uuid4(), uuid.uuid4())
        assert result is None


# ── list_trusted_tenant_ids ──────────────────────────────────────────────────


class TestListTrustedTenantIds:
    @pytest.mark.asyncio
    async def test_returns_ids(self, db, repo):
        id1, id2 = uuid.uuid4(), uuid.uuid4()
        db.execute = AsyncMock(return_value=make_list_result([id1, id2, None]))

        result = await repo.list_trusted_tenant_ids(db, uuid.uuid4())
        assert result == [id1, id2, None]

    @pytest.mark.asyncio
    async def test_empty(self, db, repo):
        db.execute = AsyncMock(return_value=make_list_result([]))

        result = await repo.list_trusted_tenant_ids(db, uuid.uuid4())
        assert result == []


# ── platform_source_exists ───────────────────────────────────────────────────


class TestPlatformSourceExists:
    @pytest.mark.asyncio
    async def test_exists(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=uuid.uuid4()))

        result = await repo.platform_source_exists(db, uuid.uuid4(), uuid.uuid4())
        assert result is True

    @pytest.mark.asyncio
    async def test_not_exists(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.platform_source_exists(db, uuid.uuid4(), uuid.uuid4())
        assert result is False


# ── add / delete ─────────────────────────────────────────────────────────────


class TestAdd:
    @pytest.mark.asyncio
    async def test_adds_and_flushes(self, db, repo):
        instance = MagicMock()

        await repo.add(db, instance)

        db.add.assert_called_once_with(instance)
        db.flush.assert_awaited_once()


class TestDelete:
    @pytest.mark.asyncio
    async def test_deletes_and_flushes(self, db, repo):
        instance = MagicMock()
        db.delete = AsyncMock()

        await repo.delete(db, instance)

        db.delete.assert_awaited_once_with(instance)
        db.flush.assert_awaited_once()
