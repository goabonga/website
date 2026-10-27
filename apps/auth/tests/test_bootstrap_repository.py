# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.repositories.bootstrap — reads and fix-ups of the bootstrap."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.db.models.tenant import TenantMember
from auth.db.repositories.bootstrap import BootstrapRepository

from tests.conftest import make_execute_result


@pytest.fixture
def repo():
    return BootstrapRepository()


class TestReads:
    @pytest.mark.parametrize(
        ("method", "args"),
        [
            ("find_platform_tenant", ()),
            ("find_tenant_by_slug", ("main",)),
            ("find_branding", (uuid.uuid4(),)),
            ("find_role", (uuid.uuid4(), "member")),
            ("find_client", ("swagger-ui",)),
        ],
    )
    async def test_found_and_missing(self, repo, db, method, args):
        row = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=row))
        assert await getattr(repo, method)(db, *args) is row
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))
        assert await getattr(repo, method)(db, *args) is None


class TestWrites:
    async def test_add_stages_and_flushes(self, repo, db):
        row = MagicMock()
        await repo.add(db, row)
        db.add.assert_called_once_with(row)
        db.flush.assert_awaited_once()

    async def test_register_orphan_users_counts_the_rows(self, repo, db):
        db.execute = AsyncMock(return_value=MagicMock(rowcount=3))
        assert await repo.register_orphan_users(db, uuid.uuid4()) == 3

    async def test_trust_counts_the_rows(self, repo, db):
        db.execute = AsyncMock(return_value=MagicMock(rowcount=None))
        assert await repo.trust_platform_in_open_sources(db, uuid.uuid4()) == 0

    async def test_missing_members_are_added_with_the_role(self, repo, db):
        users = [uuid.uuid4(), uuid.uuid4()]
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=users))
        tenant_id, role_id = uuid.uuid4(), uuid.uuid4()
        assert await repo.add_missing_members(db, tenant_id, role_id) == 2
        members = [call.args[0] for call in db.add.call_args_list]
        assert all(isinstance(m, TenantMember) for m in members)
        assert {m.user_id for m in members} == set(users)
        assert {(m.tenant_id, m.role_id) for m in members} == {(tenant_id, role_id)}
        db.flush.assert_awaited_once()

    async def test_nobody_to_add(self, repo, db):
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=[]))
        assert await repo.add_missing_members(db, uuid.uuid4(), uuid.uuid4()) == 0
        db.add.assert_not_called()
