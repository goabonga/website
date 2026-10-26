# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.repositories.issuer — IssuerRepository (100% mocked)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.db.repositories.issuer import IssuerRepository


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


class TestFindActiveTenant:
    @pytest.mark.asyncio
    async def test_delegates_to_tenant_repository(self, db):
        """IssuerRepository delegates to TenantRepository.find_active_by_id."""
        tenant = MagicMock()
        tenant_repo = MagicMock()
        tenant_repo.find_active_by_id = AsyncMock(return_value=tenant)

        repo = IssuerRepository(tenant_repository=tenant_repo)
        tid = uuid.uuid4()
        result = await repo.find_active_tenant(db, tid)

        assert result is tenant
        tenant_repo.find_active_by_id.assert_awaited_once_with(db, tid)

    @pytest.mark.asyncio
    async def test_returns_none_when_tenant_repo_returns_none(self, db):
        tenant_repo = MagicMock()
        tenant_repo.find_active_by_id = AsyncMock(return_value=None)

        repo = IssuerRepository(tenant_repository=tenant_repo)
        result = await repo.find_active_tenant(db, uuid.uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_default_constructor_uses_tenant_repository(self, db):
        """No argument -> uses the real TenantRepository under the hood."""
        repo = IssuerRepository()
        # We don't actually hit the DB; we just check the attribute exists.
        assert repo._tenants is not None
