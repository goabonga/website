# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.pairwise -- PairwiseSubjectService."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.services.pairwise import PairwiseSubjectService

from tests.conftest import make_execute_result, make_oauth2_client


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def service():
    # Reset cached platform tenant between tests
    PairwiseSubjectService._platform_tenant_id = None
    return PairwiseSubjectService()


def _make_scalar_one_result(value):
    """Build a mock result with scalar_one() support."""
    result = MagicMock()
    result.scalar_one.return_value = value
    result.scalar_one_or_none.return_value = value
    return result


# ── get_or_create_sub ────────────────────────────────────────────────────────


class TestGetOrCreateSub:
    @pytest.mark.asyncio
    async def test_creates_new_record(self, db, service):
        sub_value = uuid.uuid4()
        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()

        # First call: INSERT ... ON CONFLICT DO NOTHING
        insert_result = MagicMock()
        # Second call: SELECT to get the sub_value
        select_result = _make_scalar_one_result(sub_value)

        db.execute = AsyncMock(side_effect=[insert_result, select_result])

        result = await service.get_or_create_sub(db, user_id, tenant_id)

        assert result == str(sub_value)
        assert db.execute.call_count == 2
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_same_sub_for_same_pair(self, db, service):
        sub_value = uuid.uuid4()
        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()

        insert_result = MagicMock()
        select_result = _make_scalar_one_result(sub_value)

        # Both calls return the same sub_value (second insert is a no-op)
        db.execute = AsyncMock(
            side_effect=[
                insert_result,
                select_result,
                insert_result,
                select_result,
            ]
        )

        result1 = await service.get_or_create_sub(db, user_id, tenant_id)
        result2 = await service.get_or_create_sub(db, user_id, tenant_id)

        assert result1 == result2 == str(sub_value)

    @pytest.mark.asyncio
    async def test_returns_different_sub_for_different_tenants(self, db, service):
        user_id = uuid.uuid4()
        tenant_a = uuid.uuid4()
        tenant_b = uuid.uuid4()
        sub_a = uuid.uuid4()
        sub_b = uuid.uuid4()

        insert_result = MagicMock()

        db.execute = AsyncMock(
            side_effect=[
                insert_result,
                _make_scalar_one_result(sub_a),
                insert_result,
                _make_scalar_one_result(sub_b),
            ]
        )

        result_a = await service.get_or_create_sub(db, user_id, tenant_a)
        result_b = await service.get_or_create_sub(db, user_id, tenant_b)

        assert result_a == str(sub_a)
        assert result_b == str(sub_b)
        assert result_a != result_b


# ── resolve_user_id ──────────────────────────────────────────────────────────


class TestResolveUserId:
    @pytest.mark.asyncio
    async def test_returns_correct_user_id(self, db, service):
        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        sub_value = uuid.uuid4()

        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=user_id))

        result = await service.resolve_user_id(db, str(sub_value), tenant_id)
        assert result == user_id

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_sub(self, db, service):
        tenant_id = uuid.uuid4()
        sub_value = uuid.uuid4()

        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await service.resolve_user_id(db, str(sub_value), tenant_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_invalid_uuid(self, db, service):
        tenant_id = uuid.uuid4()

        result = await service.resolve_user_id(db, "not-a-uuid", tenant_id)
        assert result is None
        db.execute.assert_not_awaited()


# ── get_sub_for_client ───────────────────────────────────────────────────────


class TestGetSubForClient:
    @pytest.mark.asyncio
    async def test_with_tenant_id_set(self, db, service):
        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        sub_value = uuid.uuid4()

        client = make_oauth2_client()
        client.tenant_id = tenant_id

        insert_result = MagicMock()
        select_result = _make_scalar_one_result(sub_value)
        db.execute = AsyncMock(side_effect=[insert_result, select_result])

        result = await service.get_sub_for_client(db, user_id, client)
        assert result == str(sub_value)

    @pytest.mark.asyncio
    async def test_with_null_tenant_id_uses_platform(self, db, service):
        user_id = uuid.uuid4()
        platform_tenant_id = uuid.uuid4()
        sub_value = uuid.uuid4()

        client = make_oauth2_client()
        client.tenant_id = None

        # First execute: platform tenant lookup
        platform_result = make_execute_result(scalar_value=platform_tenant_id)
        # Second execute: INSERT ON CONFLICT
        insert_result = MagicMock()
        # Third execute: SELECT sub_value
        select_result = _make_scalar_one_result(sub_value)

        db.execute = AsyncMock(side_effect=[platform_result, insert_result, select_result])

        result = await service.get_sub_for_client(db, user_id, client)
        assert result == str(sub_value)
        # Platform tenant should be cached now
        assert PairwiseSubjectService._platform_tenant_id == platform_tenant_id


# ── resolve_user_id_for_client ───────────────────────────────────────────────


class TestResolveUserIdForClient:
    @pytest.mark.asyncio
    async def test_with_tenant_id_set(self, db, service):
        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        sub_value = uuid.uuid4()

        client = make_oauth2_client()
        client.tenant_id = tenant_id

        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=user_id))

        result = await service.resolve_user_id_for_client(db, str(sub_value), client)
        assert result == user_id

    @pytest.mark.asyncio
    async def test_with_null_tenant_id_uses_platform(self, db, service):
        user_id = uuid.uuid4()
        platform_tenant_id = uuid.uuid4()
        sub_value = uuid.uuid4()

        client = make_oauth2_client()
        client.tenant_id = None

        # First: platform tenant lookup, second: resolve
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=platform_tenant_id),
                make_execute_result(scalar_value=user_id),
            ]
        )

        result = await service.resolve_user_id_for_client(db, str(sub_value), client)
        assert result == user_id


# ── get_all_subs_for_user ────────────────────────────────────────────────────


class TestGetAllSubsForUser:
    @pytest.mark.asyncio
    async def test_returns_list(self, db, service):
        user_id = uuid.uuid4()
        mock_subs = [MagicMock(), MagicMock()]

        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=mock_subs))

        result = await service.get_all_subs_for_user(db, user_id)
        assert result == mock_subs
        assert len(result) == 2


# ── delete_subs_for_tenant ───────────────────────────────────────────────────


class TestDeleteSubsForTenant:
    @pytest.mark.asyncio
    async def test_returns_count(self, db, service):
        tenant_id = uuid.uuid4()

        delete_result = MagicMock()
        delete_result.rowcount = 5
        db.execute = AsyncMock(return_value=delete_result)

        count = await service.delete_subs_for_tenant(db, tenant_id)
        assert count == 5


# ── _get_platform_tenant_id ─────────────────────────────────────────────────


class TestGetPlatformTenantId:
    @pytest.mark.asyncio
    async def test_caches_result(self, db, service):
        platform_id = uuid.uuid4()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=platform_id))

        result1 = await service._get_platform_tenant_id(db)
        result2 = await service._get_platform_tenant_id(db)

        assert result1 == result2 == platform_id
        # Should only query once due to caching
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_if_no_platform_tenant(self, db, service):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        with pytest.raises(RuntimeError, match="No platform tenant found"):
            await service._get_platform_tenant_id(db)


class TestGetOrCreateSubRaceLoss:
    @pytest.mark.asyncio
    async def test_missing_row_after_insert_raises(self, db, service):
        service._repo.find_by_user_and_tenant = AsyncMock(side_effect=[None, None])
        service._repo.add = AsyncMock()

        with pytest.raises(RuntimeError, match="Pairwise subject not found after insert"):
            await service.get_or_create_sub(db, uuid.uuid4(), uuid.uuid4())
