# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.tenant_role — TenantRoleService (repo mocked)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.services.tenant_role import TenantRoleService


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def repo():
    """Mock TenantRoleRepository with all methods pre-stubbed as AsyncMocks."""
    r = MagicMock()
    r.find_by_id = AsyncMock()
    r.find_by_name_in_tenant = AsyncMock()
    r.list_roles_for_tenant = AsyncMock()
    r.find_default_role = AsyncMock()
    r.max_display_order = AsyncMock()
    r.count_members_for_role = AsyncMock()
    r.list_active_scope_names = AsyncMock(return_value=set())
    r.add = AsyncMock()
    r.stage = AsyncMock()
    r.delete = AsyncMock()
    r.flush = AsyncMock()
    r.clear_default_flag = AsyncMock()
    return r


@pytest.fixture
def service(repo):
    return TenantRoleService(repository=repo)


# ── create_default_roles ─────────────────────────────────────────────────────


class TestCreateDefaultRoles:
    @pytest.mark.asyncio
    async def test_creates_roles(self, db, service, repo):
        tenant = MagicMock()
        tenant.id = uuid.uuid4()
        with patch("auth.services.tenant_role.TenantCustomRole"):
            roles = await service.create_default_roles(db, tenant)
        # DEFAULT_TENANT_ROLES has 3 entries (owner, admin, member)
        assert len(roles) == 3
        assert repo.stage.await_count == 3
        repo.flush.assert_awaited_once_with(db)


# ── get_tenant_roles ─────────────────────────────────────────────────────────


class TestGetTenantRoles:
    @pytest.mark.asyncio
    async def test_returns_roles(self, db, service, repo):
        roles = [MagicMock(), MagicMock()]
        repo.list_roles_for_tenant.return_value = roles

        result = await service.get_tenant_roles(db, uuid.uuid4())
        assert result == roles
        repo.list_roles_for_tenant.assert_awaited_once()


# ── get_role_by_id ───────────────────────────────────────────────────────────


class TestGetRoleById:
    @pytest.mark.asyncio
    async def test_found(self, db, service, repo):
        role = MagicMock()
        repo.find_by_id.return_value = role
        result = await service.get_role_by_id(db, uuid.uuid4())
        assert result is role

    @pytest.mark.asyncio
    async def test_not_found(self, db, service, repo):
        repo.find_by_id.return_value = None
        result = await service.get_role_by_id(db, uuid.uuid4())
        assert result is None


# ── get_role_by_name ─────────────────────────────────────────────────────────


class TestGetRoleByName:
    @pytest.mark.asyncio
    async def test_found(self, db, service, repo):
        role = MagicMock()
        repo.find_by_name_in_tenant.return_value = role
        result = await service.get_role_by_name(db, uuid.uuid4(), "admin")
        assert result is role


# ── get_owner_role ───────────────────────────────────────────────────────────


class TestGetOwnerRole:
    @pytest.mark.asyncio
    async def test_delegates(self, db, service, repo):
        role = MagicMock()
        repo.find_by_name_in_tenant.return_value = role
        result = await service.get_owner_role(db, uuid.uuid4())
        assert result is role
        # Called with "owner"
        args, _ = repo.find_by_name_in_tenant.call_args
        assert args[2] == "owner"


# ── resolve_default_registration_role ────────────────────────────────────────


class TestResolveDefaultRegistrationRole:
    @pytest.mark.asyncio
    async def test_returns_flagged_role(self, db, service, repo):
        flagged = MagicMock()
        repo.find_default_role.return_value = flagged
        result = await service.resolve_default_registration_role(db, uuid.uuid4())
        assert result is flagged
        repo.find_by_name_in_tenant.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_to_member(self, db, service, repo):
        member_role = MagicMock()
        repo.find_default_role.return_value = None
        repo.find_by_name_in_tenant.return_value = member_role
        result = await service.resolve_default_registration_role(db, uuid.uuid4())
        assert result is member_role
        args, _ = repo.find_by_name_in_tenant.call_args
        assert args[2] == "member"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_fallback(self, db, service, repo):
        repo.find_default_role.return_value = None
        repo.find_by_name_in_tenant.return_value = None
        result = await service.resolve_default_registration_role(db, uuid.uuid4())
        assert result is None


# ── set_default_role ─────────────────────────────────────────────────────────


class TestSetDefaultRole:
    @pytest.mark.asyncio
    async def test_flips_target_on(self, db, service, repo):
        tid = uuid.uuid4()
        target = MagicMock()
        target.id = uuid.uuid4()
        target.tenant_id = tid
        target.is_default = False

        repo.find_by_id.return_value = target

        result = await service.set_default_role(db, tid, target.id)
        assert result is target
        assert target.is_default is True
        repo.clear_default_flag.assert_awaited_once_with(db, tid, except_role_id=target.id)
        repo.flush.assert_awaited_once_with(db)

    @pytest.mark.asyncio
    async def test_refuses_cross_tenant(self, db, service, repo):
        target = MagicMock()
        target.tenant_id = uuid.uuid4()
        repo.find_by_id.return_value = target

        result = await service.set_default_role(db, uuid.uuid4(), uuid.uuid4())
        assert result is None
        repo.clear_default_flag.assert_not_called()

    @pytest.mark.asyncio
    async def test_role_not_found(self, db, service, repo):
        repo.find_by_id.return_value = None
        result = await service.set_default_role(db, uuid.uuid4(), uuid.uuid4())
        assert result is None


class TestClearDefaultRole:
    @pytest.mark.asyncio
    async def test_clears(self, db, service, repo):
        await service.clear_default_role(db, uuid.uuid4())
        repo.clear_default_flag.assert_awaited_once()
        repo.flush.assert_awaited_once_with(db)


# ── create_role ──────────────────────────────────────────────────────────────


class TestCreateRole:
    @pytest.mark.asyncio
    async def test_success(self, db, service, repo):
        tid = uuid.uuid4()
        service._validate_scopes = AsyncMock()
        repo.find_by_name_in_tenant.return_value = None
        repo.max_display_order.return_value = 0

        with patch("auth.services.tenant_role.TenantCustomRole") as MockRole:
            mock_instance = MagicMock()
            MockRole.return_value = mock_instance
            result = await service.create_role(
                db, tid, "editor", "Editor", ["members:read"], "An editor role"
            )
        assert result is mock_instance
        repo.add.assert_awaited_once_with(db, mock_instance)

    @pytest.mark.asyncio
    async def test_empty_name_raises(self, db, service):
        service._validate_scopes = AsyncMock()
        with pytest.raises(ValueError, match="empty"):
            await service.create_role(db, uuid.uuid4(), "  ", "Editor", ["members:read"])

    @pytest.mark.asyncio
    async def test_duplicate_name_raises(self, db, service, repo):
        service._validate_scopes = AsyncMock()
        repo.find_by_name_in_tenant.return_value = MagicMock()
        with pytest.raises(ValueError, match="already exists"):
            await service.create_role(db, uuid.uuid4(), "editor", "Editor", ["members:read"])


# ── update_role ──────────────────────────────────────────────────────────────


class TestUpdateRole:
    @pytest.mark.asyncio
    async def test_update_display_name(self, db, service, repo):
        role = MagicMock()
        role.is_system = False
        await service.update_role(db, role, display_name="New Name")
        assert role.display_name == "New Name"
        repo.flush.assert_awaited_once_with(db)

    @pytest.mark.asyncio
    async def test_update_scopes(self, db, service):
        role = MagicMock()
        role.is_system = False
        service._validate_scopes = AsyncMock()
        await service.update_role(db, role, scopes=["members:*"])
        assert role.scopes == ["members:*"]

    @pytest.mark.asyncio
    async def test_update_description(self, db, service):
        role = MagicMock()
        role.is_system = False
        await service.update_role(db, role, description="Updated")
        assert role.description == "Updated"

    @pytest.mark.asyncio
    async def test_system_role_scope_change_raises(self, db, service):
        role = MagicMock()
        role.is_system = True
        with pytest.raises(ValueError, match="system roles"):
            await service.update_role(db, role, scopes=["members:read"])


# ── delete_role ──────────────────────────────────────────────────────────────


class TestDeleteRole:
    @pytest.mark.asyncio
    async def test_success(self, db, service, repo):
        role = MagicMock()
        role.is_system = False
        repo.count_members_for_role.return_value = 0
        await service.delete_role(db, role)
        repo.delete.assert_awaited_once_with(db, role)

    @pytest.mark.asyncio
    async def test_system_role_raises(self, db, service):
        role = MagicMock()
        role.is_system = True
        with pytest.raises(ValueError, match="system roles"):
            await service.delete_role(db, role)

    @pytest.mark.asyncio
    async def test_has_members_raises(self, db, service, repo):
        role = MagicMock()
        role.is_system = False
        repo.count_members_for_role.return_value = 3
        with pytest.raises(ValueError, match="3 assigned member"):
            await service.delete_role(db, role)


# ── get_role_member_count ────────────────────────────────────────────────────


class TestGetRoleMemberCount:
    @pytest.mark.asyncio
    async def test_count(self, db, service, repo):
        repo.count_members_for_role.return_value = 5
        result = await service.get_role_member_count(db, MagicMock())
        assert result == 5

    @pytest.mark.asyncio
    async def test_zero_count(self, db, service, repo):
        repo.count_members_for_role.return_value = 0
        result = await service.get_role_member_count(db, MagicMock())
        assert result == 0


# ── assign_role ──────────────────────────────────────────────────────────────


class TestAssignRole:
    @pytest.mark.asyncio
    async def test_success(self, db, service, repo):
        tid = uuid.uuid4()
        member = MagicMock()
        member.tenant_id = tid
        role = MagicMock()
        role.tenant_id = tid
        await service.assign_role(db, member, role)
        assert member.role_id == role.id
        repo.flush.assert_awaited_once_with(db)

    @pytest.mark.asyncio
    async def test_different_tenant_raises(self, db, service):
        member = MagicMock()
        member.tenant_id = uuid.uuid4()
        role = MagicMock()
        role.tenant_id = uuid.uuid4()
        with pytest.raises(ValueError, match="same tenant"):
            await service.assign_role(db, member, role)


# ── get_available_scopes ─────────────────────────────────────────────────────


class TestGetAvailableScopes:
    def test_returns_copy(self, service):
        scopes = service.get_available_scopes()
        assert "*" in scopes
        assert isinstance(scopes, dict)


# ── _validate_scopes ─────────────────────────────────────────────────────────


class TestValidateScopes:
    @pytest.mark.asyncio
    async def test_valid_tenant_scopes(self, db, service, repo):
        repo.list_active_scope_names.return_value = set()
        await service._validate_scopes(db, ["*", "members:read"])  # Should not raise

    @pytest.mark.asyncio
    async def test_invalid_scope_raises(self, db, service, repo):
        repo.list_active_scope_names.return_value = set()
        with pytest.raises(ValueError, match="Invalid scope"):
            await service._validate_scopes(db, ["nonexistent:scope"])

    @pytest.mark.asyncio
    async def test_db_scope_accepted(self, db, service, repo):
        repo.list_active_scope_names.return_value = {"custom:db_scope"}
        # Should not raise
        await service._validate_scopes(db, ["custom:db_scope"])


# ── check_member_scope / is_owner / is_admin_or_owner ────────────────────────


class TestScopeHelpers:
    def test_check_member_scope(self, service):
        member = MagicMock()
        member.has_scope.return_value = True
        assert service.check_member_scope(member, "members:read") is True

    def test_is_owner(self, service):
        member = MagicMock()
        member.has_scope.return_value = True
        assert service.is_owner(member) is True

    def test_is_admin_or_owner(self, service):
        member = MagicMock()
        member.has_scope.return_value = True
        assert service.is_admin_or_owner(member) is True


# ── default repo wiring ──────────────────────────────────────────────────────


class TestDefaultRepoWiring:
    def test_default_repo_instantiated(self):
        """Service should create its own repo when none is provided."""
        s = TenantRoleService()
        assert s._repo is not None


class TestGetAvailableScopesTenantFiltering:
    def test_no_tenant_returns_every_tenant_scope(self, service):
        from auth.services.tenant_role import TENANT_SCOPES

        assert service.get_available_scopes() == TENANT_SCOPES

    def test_tenant_filters_the_catalogue(self, service):
        tenant = MagicMock()
        tenant.settings = {"allowed_scopes": ["members:read"]}

        result = service.get_available_scopes(tenant)

        assert set(result) <= {"members:read", "*"}


class TestGetTenantAllowedScopes:
    def test_no_settings_returns_all(self, service):
        from auth.services.tenant_role import TENANT_SCOPES

        tenant = MagicMock()
        tenant.settings = None

        assert service.get_tenant_allowed_scopes(tenant) == TENANT_SCOPES

    def test_absent_key_returns_all(self, service):
        from auth.services.tenant_role import TENANT_SCOPES

        tenant = MagicMock()
        tenant.settings = {"other": 1}

        assert service.get_tenant_allowed_scopes(tenant) == TENANT_SCOPES

    def test_wildcard_is_always_allowed(self, service):
        from auth.services.tenant_role import TENANT_SCOPES

        tenant = MagicMock()
        tenant.settings = {"allowed_scopes": []}

        result = service.get_tenant_allowed_scopes(tenant)

        assert set(result) == ({"*"} & set(TENANT_SCOPES))


class TestValidateScopesWithTenant:
    @pytest.mark.asyncio
    async def test_tenant_restricts_the_valid_set(self, db, repo, service):
        tenant = MagicMock()
        tenant.settings = {"allowed_scopes": ["members:read"]}
        repo.list_active_scope_names = AsyncMock(return_value=[])

        await service._validate_scopes(db, ["members:read"], tenant)

        with pytest.raises(ValueError):
            await service._validate_scopes(db, ["members:write"], tenant)
