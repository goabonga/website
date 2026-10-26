# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for TenantService: CRUD operations with mock DB."""

from unittest.mock import AsyncMock, MagicMock

from knowledge.models.enums import PlanType
from knowledge.schemas.tenant import TenantCreate
from knowledge.services.tenants import TenantService

# ============================================================
# create
# ============================================================


class TestCreate:
    async def test_creates_tenant(self, mock_db):
        service = TenantService(mock_db)
        data = TenantCreate(name="My Org", slug="my-org")
        await service.create(data)

        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once()

        added = mock_db.add.call_args[0][0]
        assert added.name == "My Org"
        assert added.slug == "my-org"
        assert added.plan == PlanType.FREE
        assert added.settings == {}


# ============================================================
# get_by_id
# ============================================================


class TestGetById:
    async def test_found(self, mock_db, make_result, tenant_id):
        tenant = MagicMock()
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=tenant))
        service = TenantService(mock_db)
        result = await service.get_by_id(tenant_id)
        assert result is tenant

    async def test_not_found(self, mock_db, tenant_id):
        service = TenantService(mock_db)
        result = await service.get_by_id(tenant_id)
        assert result is None


# ============================================================
# get_by_slug
# ============================================================


class TestGetBySlug:
    async def test_found(self, mock_db, make_result):
        tenant = MagicMock()
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=tenant))
        service = TenantService(mock_db)
        result = await service.get_by_slug("my-org")
        assert result is tenant

    async def test_not_found(self, mock_db):
        service = TenantService(mock_db)
        result = await service.get_by_slug("nonexistent")
        assert result is None


# ============================================================
# list
# ============================================================


class TestList:
    async def test_returns_tenants(self, mock_db, make_result):
        t1 = MagicMock()
        t2 = MagicMock()
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[t1, t2]))
        service = TenantService(mock_db)
        result = await service.list()
        assert len(result) == 2
        assert result[0] is t1
        assert result[1] is t2

    async def test_returns_empty(self, mock_db):
        service = TenantService(mock_db)
        result = await service.list()
        assert result == []

    async def test_with_offset_limit(self, mock_db, make_result):
        t1 = MagicMock()
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[t1]))
        service = TenantService(mock_db)
        result = await service.list(offset=10, limit=5)
        assert len(result) == 1


# ============================================================
# update_plan
# ============================================================


class TestUpdatePlan:
    async def test_found_and_updated(self, mock_db, make_result, tenant_id):
        tenant = MagicMock()
        tenant.plan = PlanType.FREE
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=tenant))
        service = TenantService(mock_db)
        result = await service.update_plan(tenant_id, PlanType.PRO)

        assert result is tenant
        assert tenant.plan == PlanType.PRO
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once()

    async def test_not_found_returns_none(self, mock_db, tenant_id):
        service = TenantService(mock_db)
        result = await service.update_plan(tenant_id, PlanType.PRO)
        assert result is None


# ============================================================
# deactivate
# ============================================================


class TestDeactivate:
    async def test_found_and_deactivated(self, mock_db, make_result, tenant_id):
        tenant = MagicMock()
        tenant.is_active = True
        mock_db.execute = AsyncMock(return_value=make_result(scalar_one_or_none=tenant))
        service = TenantService(mock_db)
        result = await service.deactivate(tenant_id)

        assert result is True
        assert tenant.is_active is False
        mock_db.flush.assert_called_once()

    async def test_not_found_returns_false(self, mock_db, tenant_id):
        service = TenantService(mock_db)
        result = await service.deactivate(tenant_id)
        assert result is False
