# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.repositories.federation — FederationRepository (100% mocked)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.db.repositories.federation import FederationRepository

from tests.conftest import make_execute_result


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def repo():
    return FederationRepository()


# ── list_idps_for_tenant_slug ────────────────────────────────────────────────


class TestListIdpsForTenantSlug:
    @pytest.mark.asyncio
    async def test_returns_providers(self, db, repo):
        idp1, idp2 = MagicMock(), MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=[idp1, idp2]))

        result = await repo.list_idps_for_tenant_slug(db, "tenant-slug")
        assert result == [idp1, idp2]

    @pytest.mark.asyncio
    async def test_empty(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=[]))

        result = await repo.list_idps_for_tenant_slug(db, "tenant-slug")
        assert result == []


# ── find_idp_by_id ───────────────────────────────────────────────────────────


class TestFindIdpById:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        idp = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=idp))

        result = await repo.find_idp_by_id(db, uuid.uuid4())
        assert result is idp

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_idp_by_id(db, "idp-missing")
        assert result is None


# ── list_identities_for_user ─────────────────────────────────────────────────


class TestListIdentitiesForUser:
    @pytest.mark.asyncio
    async def test_returns_identities(self, db, repo):
        rows = [MagicMock(), MagicMock()]
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=rows))

        result = await repo.list_identities_for_user(db, uuid.uuid4())
        assert result == rows

    @pytest.mark.asyncio
    async def test_empty(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=[]))

        result = await repo.list_identities_for_user(db, uuid.uuid4())
        assert result == []


# ── list_identities_for_user_in_tenant ───────────────────────────────────────


class TestListIdentitiesForUserInTenant:
    @pytest.mark.asyncio
    async def test_returns_identities(self, db, repo):
        rows = [MagicMock()]
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=rows))

        result = await repo.list_identities_for_user_in_tenant(db, uuid.uuid4(), uuid.uuid4())
        assert result == rows


# ── find_federated_identity ──────────────────────────────────────────────────


class TestFindFederatedIdentity:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        fed = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=fed))

        result = await repo.find_federated_identity(db, uuid.uuid4(), uuid.uuid4())
        assert result is fed

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_federated_identity(db, uuid.uuid4(), uuid.uuid4())
        assert result is None


# ── find_identity_by_subject ─────────────────────────────────────────────────


class TestFindIdentityBySubject:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        fed = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=fed))

        result = await repo.find_identity_by_subject(db, uuid.uuid4(), "ext-sub-1")
        assert result is fed

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_identity_by_subject(db, uuid.uuid4(), "missing")
        assert result is None


# ── find_user_by_id ──────────────────────────────────────────────────────────


class TestFindUserById:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        user = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=user))

        result = await repo.find_user_by_id(db, uuid.uuid4())
        assert result is user

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_user_by_id(db, uuid.uuid4())
        assert result is None


# ── find_user_by_email ───────────────────────────────────────────────────────


class TestFindUserByEmail:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        user = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=user))

        result = await repo.find_user_by_email(db, "User@Example.COM")
        assert result is user

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_user_by_email(db, "missing@example.com")
        assert result is None


# ── find_tenant_by_slug ──────────────────────────────────────────────────────


class TestFindTenantBySlug:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        tenant = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))

        result = await repo.find_tenant_by_slug(db, "acme")
        assert result is tenant

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_tenant_by_slug(db, "missing")
        assert result is None


# ── find_tenant_membership ───────────────────────────────────────────────────


class TestFindTenantMembership:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        membership = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=membership))

        result = await repo.find_tenant_membership(db, uuid.uuid4(), uuid.uuid4())
        assert result is membership

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_tenant_membership(db, uuid.uuid4(), uuid.uuid4())
        assert result is None


# ── add / delete ─────────────────────────────────────────────────────────────


class TestAdd:
    @pytest.mark.asyncio
    async def test_calls_db_add(self, db, repo):
        fed = MagicMock()

        await repo.add(db, fed)

        db.add.assert_called_once_with(fed)


class TestDelete:
    @pytest.mark.asyncio
    async def test_calls_db_delete(self, db, repo):
        fed = MagicMock()
        db.delete = AsyncMock()

        await repo.delete(db, fed)

        db.delete.assert_awaited_once_with(fed)
