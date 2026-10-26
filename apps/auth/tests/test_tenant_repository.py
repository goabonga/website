# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.repositories.tenant — TenantRepository (100% mocked)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.db.repositories.tenant import TenantRepository

from tests.conftest import make_execute_result


def make_list_result(rows: list) -> MagicMock:
    """Build a Result mock where ``.scalars().all()`` returns ``rows``."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    result.scalars.return_value = scalars
    return result


def make_tenant(slug: str = "acme", is_active: bool = True) -> MagicMock:
    """Create a mock Tenant model."""
    t = MagicMock()
    t.id = uuid.uuid4()
    t.slug = slug
    t.display_name = slug.title()
    t.custom_domain = None
    t.is_active = is_active
    return t


def make_tenant_member(tenant_id=None, user_id=None) -> MagicMock:
    """Create a mock TenantMember model."""
    m = MagicMock()
    m.id = uuid.uuid4()
    m.tenant_id = tenant_id or uuid.uuid4()
    m.user_id = user_id or uuid.uuid4()
    return m


def make_idp(tenant_id=None, display_order: int = 0) -> MagicMock:
    """Create a mock IdentityProvider model."""
    idp = MagicMock()
    idp.id = uuid.uuid4()
    idp.tenant_id = tenant_id or uuid.uuid4()
    idp.display_order = display_order
    return idp


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def repo():
    return TenantRepository()


# ── find_by_id ───────────────────────────────────────────────────────────────


class TestFindById:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        tenant = make_tenant()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))

        result = await repo.find_by_id(db, tenant.id)
        assert result is tenant

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_by_id(db, uuid.uuid4())
        assert result is None


# ── find_active_by_id ────────────────────────────────────────────────────────


class TestFindActiveById:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        tenant = make_tenant(is_active=True)
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))

        result = await repo.find_active_by_id(db, tenant.id)
        assert result is tenant

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_active_by_id(db, uuid.uuid4())
        assert result is None


# ── find_by_slug ─────────────────────────────────────────────────────────────


class TestFindBySlug:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        tenant = make_tenant(slug="acme")
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))

        result = await repo.find_by_slug(db, "acme")
        assert result is tenant

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_by_slug(db, "missing")
        assert result is None


# ── list_tenants ─────────────────────────────────────────────────────────────


class TestListTenants:
    @pytest.mark.asyncio
    async def test_returns_items_and_total(self, db, repo):
        tenants = [make_tenant(), make_tenant()]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=2),
                make_list_result(tenants),
            ]
        )

        items, total = await repo.list_tenants(db, page=1, page_size=20)

        assert items == tenants
        assert total == 2
        assert db.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_empty(self, db, repo):
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=0),
                make_list_result([]),
            ]
        )

        items, total = await repo.list_tenants(db)

        assert items == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_with_is_active_filter(self, db, repo):
        tenants = [make_tenant(is_active=True)]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=1),
                make_list_result(tenants),
            ]
        )

        items, total = await repo.list_tenants(db, is_active=True)

        assert items == tenants
        assert total == 1

    @pytest.mark.asyncio
    async def test_with_search(self, db, repo):
        tenants = [make_tenant(slug="acme")]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=1),
                make_list_result(tenants),
            ]
        )

        items, total = await repo.list_tenants(db, search="acme")

        assert items == tenants
        assert total == 1

    @pytest.mark.asyncio
    async def test_with_eager_members_and_idps(self, db, repo):
        tenants = [make_tenant()]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=1),
                make_list_result(tenants),
            ]
        )

        items, total = await repo.list_tenants(db, eager_members=True, eager_idps=True)

        assert items == tenants
        assert total == 1

    @pytest.mark.asyncio
    async def test_all_filters_combined(self, db, repo):
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=0),
                make_list_result([]),
            ]
        )

        items, total = await repo.list_tenants(
            db,
            page=2,
            page_size=5,
            search="foo",
            is_active=False,
            eager_members=True,
            eager_idps=True,
        )

        assert items == []
        assert total == 0


# ── list_members / count_members / find_member / find_member_by_id ──────────


class TestListMembers:
    @pytest.mark.asyncio
    async def test_returns_all(self, db, repo):
        tid = uuid.uuid4()
        members = [make_tenant_member(tenant_id=tid), make_tenant_member(tenant_id=tid)]
        db.execute = AsyncMock(return_value=make_list_result(members))

        result = await repo.list_members(db, tid)
        assert result == members

    @pytest.mark.asyncio
    async def test_with_pagination(self, db, repo):
        tid = uuid.uuid4()
        members = [make_tenant_member(tenant_id=tid)]
        db.execute = AsyncMock(return_value=make_list_result(members))

        result = await repo.list_members(db, tid, page=1, page_size=10)
        assert result == members

    @pytest.mark.asyncio
    async def test_eager_role_disabled(self, db, repo):
        tid = uuid.uuid4()
        db.execute = AsyncMock(return_value=make_list_result([]))

        result = await repo.list_members(db, tid, eager_role=False)
        assert result == []


class TestCountMembers:
    @pytest.mark.asyncio
    async def test_returns_count(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=7))

        result = await repo.count_members(db, uuid.uuid4())
        assert result == 7

    @pytest.mark.asyncio
    async def test_returns_zero_when_none(self, db, repo):
        res = MagicMock()
        res.scalar.return_value = None
        db.execute = AsyncMock(return_value=res)

        result = await repo.count_members(db, uuid.uuid4())
        assert result == 0


class TestFindMember:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        member = make_tenant_member()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=member))

        result = await repo.find_member(db, member.tenant_id, member.user_id)
        assert result is member

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_member(db, uuid.uuid4(), uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_without_eager_role(self, db, repo):
        member = make_tenant_member()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=member))

        result = await repo.find_member(db, member.tenant_id, member.user_id, eager_role=False)
        assert result is member


class TestFindMemberById:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        member = make_tenant_member()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=member))

        result = await repo.find_member_by_id(db, member.id)
        assert result is member

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_member_by_id(db, uuid.uuid4())
        assert result is None


class TestListUserMemberships:
    @pytest.mark.asyncio
    async def test_returns_memberships(self, db, repo):
        uid = uuid.uuid4()
        members = [make_tenant_member(user_id=uid), make_tenant_member(user_id=uid)]
        db.execute = AsyncMock(return_value=make_list_result(members))

        result = await repo.list_user_memberships(db, uid)
        assert result == members

    @pytest.mark.asyncio
    async def test_empty(self, db, repo):
        db.execute = AsyncMock(return_value=make_list_result([]))

        result = await repo.list_user_memberships(db, uuid.uuid4())
        assert result == []


# ── list_idps / count_idps / find_idp ────────────────────────────────────────


class TestListIdps:
    @pytest.mark.asyncio
    async def test_returns_all(self, db, repo):
        tid = uuid.uuid4()
        idps = [make_idp(tenant_id=tid), make_idp(tenant_id=tid, display_order=1)]
        db.execute = AsyncMock(return_value=make_list_result(idps))

        result = await repo.list_idps(db, tid)
        assert result == idps

    @pytest.mark.asyncio
    async def test_with_pagination(self, db, repo):
        tid = uuid.uuid4()
        idps = [make_idp(tenant_id=tid)]
        db.execute = AsyncMock(return_value=make_list_result(idps))

        result = await repo.list_idps(db, tid, page=1, page_size=10)
        assert result == idps

    @pytest.mark.asyncio
    async def test_empty(self, db, repo):
        db.execute = AsyncMock(return_value=make_list_result([]))

        result = await repo.list_idps(db, uuid.uuid4())
        assert result == []


class TestCountIdps:
    @pytest.mark.asyncio
    async def test_returns_count(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=3))

        result = await repo.count_idps(db, uuid.uuid4())
        assert result == 3

    @pytest.mark.asyncio
    async def test_returns_zero_when_none(self, db, repo):
        res = MagicMock()
        res.scalar.return_value = None
        db.execute = AsyncMock(return_value=res)

        result = await repo.count_idps(db, uuid.uuid4())
        assert result == 0


class TestFindIdp:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        idp = make_idp()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=idp))

        result = await repo.find_idp(db, idp.id)
        assert result is idp

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_idp(db, uuid.uuid4())
        assert result is None


# ── add / delete ─────────────────────────────────────────────────────────────


class TestAdd:
    @pytest.mark.asyncio
    async def test_adds_and_flushes(self, db, repo):
        tenant = make_tenant()

        await repo.add(db, tenant)

        db.add.assert_called_once_with(tenant)
        db.flush.assert_awaited_once()


class TestDelete:
    @pytest.mark.asyncio
    async def test_calls_db_delete(self, db, repo):
        tenant = make_tenant()
        db.delete = AsyncMock()

        await repo.delete(db, tenant)

        db.delete.assert_awaited_once_with(tenant)


# ── add_member / add_branding ────────────────────────────────────────────────


class TestAddMember:
    @pytest.mark.asyncio
    async def test_stages_without_flush(self, db, repo):
        member = MagicMock()

        result = await repo.add_member(db, member)

        db.add.assert_called_once_with(member)
        db.flush.assert_not_awaited()
        assert result is member


class TestAddBranding:
    @pytest.mark.asyncio
    async def test_stages_without_flush(self, db, repo):
        branding = MagicMock()

        result = await repo.add_branding(db, branding)

        db.add.assert_called_once_with(branding)
        db.flush.assert_not_awaited()
        assert result is branding


class TestFindSettingsById:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value={"mfa": True}))

        assert await repo.find_settings_by_id(db, uuid.uuid4()) == {"mfa": True}

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        assert await repo.find_settings_by_id(db, uuid.uuid4()) is None


class TestListIdNamePairsWithIds:
    @pytest.mark.asyncio
    async def test_empty_ids_short_circuits(self, db, repo):
        db.execute = AsyncMock()

        assert await repo.list_id_name_pairs(db, ids=[]) == []
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_restricted_to_ids(self, db, repo):
        tid = uuid.uuid4()
        result = MagicMock()
        result.all.return_value = [(tid, "Acme")]
        db.execute = AsyncMock(return_value=result)

        assert await repo.list_id_name_pairs(db, ids={tid}) == [(tid, "Acme")]


class TestListActiveDropdown:
    @pytest.mark.asyncio
    async def test_returns_triples(self, db, repo):
        tid = uuid.uuid4()
        result = MagicMock()
        result.all.return_value = [(tid, "Acme", "acme")]
        db.execute = AsyncMock(return_value=result)

        assert await repo.list_active_dropdown(db) == [(tid, "Acme", "acme")]

    @pytest.mark.asyncio
    async def test_empty(self, db, repo):
        result = MagicMock()
        result.all.return_value = []
        db.execute = AsyncMock(return_value=result)

        assert await repo.list_active_dropdown(db) == []


class TestListUserMembershipsWithCustomRole:
    @pytest.mark.asyncio
    async def test_returns_memberships(self, db, repo):
        members = [make_tenant_member(), make_tenant_member()]
        db.execute = AsyncMock(return_value=make_list_result(members))

        assert await repo.list_user_memberships_with_custom_role(db, uuid.uuid4()) == members

    @pytest.mark.asyncio
    async def test_empty(self, db, repo):
        db.execute = AsyncMock(return_value=make_list_result([]))

        assert await repo.list_user_memberships_with_custom_role(db, uuid.uuid4()) == []


class TestFindIdpScopedWithFederated:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        idp = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=idp))

        assert await repo.find_idp_scoped_with_federated(db, uuid.uuid4(), uuid.uuid4()) is idp

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        assert await repo.find_idp_scoped_with_federated(db, uuid.uuid4(), uuid.uuid4()) is None


class TestFindMemberInTenant:
    @pytest.mark.asyncio
    async def test_eager_role_by_default(self, db, repo):
        member = make_tenant_member()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=member))

        assert await repo.find_member_in_tenant(db, uuid.uuid4(), uuid.uuid4()) is member

    @pytest.mark.asyncio
    async def test_without_eager_role(self, db, repo):
        member = make_tenant_member()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=member))

        result = await repo.find_member_in_tenant(db, uuid.uuid4(), uuid.uuid4(), eager_role=False)
        assert result is member

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        assert await repo.find_member_in_tenant(db, uuid.uuid4(), uuid.uuid4()) is None


class TestEagerLoadedTenantLookups:
    @pytest.mark.asyncio
    async def test_find_by_id_with_branding(self, db, repo):
        tenant = make_tenant()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))

        assert await repo.find_by_id_with_branding(db, uuid.uuid4()) is tenant

    @pytest.mark.asyncio
    async def test_find_by_id_with_branding_missing(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        assert await repo.find_by_id_with_branding(db, uuid.uuid4()) is None

    @pytest.mark.asyncio
    async def test_find_by_slug_with_branding(self, db, repo):
        tenant = make_tenant()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))

        assert await repo.find_by_slug_with_branding(db, "acme") is tenant

    @pytest.mark.asyncio
    async def test_find_by_slug_with_branding_missing(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        assert await repo.find_by_slug_with_branding(db, "nope") is None

    @pytest.mark.asyncio
    async def test_find_by_id_with_templates(self, db, repo):
        tenant = make_tenant()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))

        assert await repo.find_by_id_with_templates(db, uuid.uuid4()) is tenant

    @pytest.mark.asyncio
    async def test_find_by_id_with_templates_missing(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        assert await repo.find_by_id_with_templates(db, uuid.uuid4()) is None

    @pytest.mark.asyncio
    async def test_find_by_slug_with_templates(self, db, repo):
        tenant = make_tenant()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))

        assert await repo.find_by_slug_with_templates(db, "acme") is tenant

    @pytest.mark.asyncio
    async def test_find_by_slug_with_templates_missing(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        assert await repo.find_by_slug_with_templates(db, "nope") is None


class TestFindBranding:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        branding = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=branding))

        assert await repo.find_branding(db, uuid.uuid4()) is branding

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        assert await repo.find_branding(db, uuid.uuid4()) is None


class TestFindCustomRoleScoped:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        role = MagicMock()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=role))

        assert await repo.find_custom_role_scoped(db, uuid.uuid4(), uuid.uuid4()) is role

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        assert await repo.find_custom_role_scoped(db, uuid.uuid4(), uuid.uuid4()) is None


class TestCountMembersForRole:
    @pytest.mark.asyncio
    async def test_returns_count(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=8))

        assert await repo.count_members_for_role(db, uuid.uuid4()) == 8

    @pytest.mark.asyncio
    async def test_none_becomes_zero(self, db, repo):
        result = MagicMock()
        result.scalar.return_value = None
        db.execute = AsyncMock(return_value=result)

        assert await repo.count_members_for_role(db, uuid.uuid4()) == 0


class TestFindPrimaryEmailForUser:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value="a@example.com"))

        assert await repo.find_primary_email_for_user(db, uuid.uuid4()) == "a@example.com"

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        assert await repo.find_primary_email_for_user(db, uuid.uuid4()) is None
