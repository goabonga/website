# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Branch coverage for the organisation-scoped API v1 route modules.

The happy paths are exercised over HTTP in ``tests/api/v1``; these tests call
the handlers directly to reach the error and fallback branches those flows do
not touch.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _user():
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


def _tenant():
    tenant = MagicMock()
    tenant.id = uuid.uuid4()
    tenant.slug = "acme"
    tenant.display_name = "Acme"
    tenant.is_active = True
    tenant.settings = {}
    return tenant


def _stamping_add_member():
    """Stand in for TenantService.add_member(), filling DB-generated columns."""

    async def _add(_db, member):
        member.id = uuid.uuid4()
        member.created_at = datetime.now(UTC)
        member.updated_at = datetime.now(UTC)

    return AsyncMock(side_effect=_add)


def _member(tenant_id, user_id, role_name="owner"):
    member = MagicMock()
    member.id = uuid.uuid4()
    member.tenant_id = tenant_id
    member.user_id = user_id
    member.role_id = uuid.uuid4()
    member.role_name = role_name
    member.role_display_name = role_name.capitalize()
    member.role_scopes = ["*"]
    member.joined_at = datetime.now(UTC)
    member.invited_at = None
    member.invited_by = None
    member.created_at = datetime.now(UTC)
    member.updated_at = datetime.now(UTC)
    member.user_email = None
    member.user_name = None
    member.user = MagicMock()
    member.user.emails = []
    return member


# ---------------------------------------------------------------------------
# add_member — explicit role_id resolution
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# trust — organisation lookups that come back empty
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# IdP creation without a client secret
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Role update: is_default left unchanged
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# get_organisation as a non-admin
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# /me/password
# ---------------------------------------------------------------------------


class TestMePasswordChange:
    def _body(self):
        from auth.api.schemas.api.me.schemas import PasswordChangeRequest

        return PasswordChangeRequest(current_password="OldP@ss1", new_password="NewP@ssw0rd")

    @pytest.mark.asyncio
    async def test_user_without_primary_email_is_a_400(self):
        from auth.api.routes.api.me.password import change_password

        user = _user()
        secondary = MagicMock()
        secondary.is_primary = False
        user.emails = [secondary]

        with pytest.raises(HTTPException) as exc:
            await change_password(self._body(), user, AsyncMock(), AsyncMock(), AsyncMock())

        assert exc.value.status_code == 400
        assert "No primary email" in exc.value.detail

    @pytest.mark.asyncio
    async def test_service_failure_is_a_400(self):
        from auth.api.routes.api.me.password import change_password

        user = _user()
        primary = MagicMock()
        primary.is_primary = True
        primary.email = "u@example.com"
        user.emails = [primary]

        auth_service = AsyncMock()
        auth_service.verify_credentials = AsyncMock(return_value=user)
        password_service = AsyncMock()
        password_service.change_password = AsyncMock(return_value=(False, "too weak"))

        with pytest.raises(HTTPException) as exc:
            await change_password(self._body(), user, AsyncMock(), password_service, auth_service)

        assert exc.value.status_code == 400
        assert exc.value.detail == "too weak"


# ---------------------------------------------------------------------------
# auth.api.routes.api.roles — validation errors that are not name collisions
# ---------------------------------------------------------------------------


ROLES = "auth.api.routes.api.roles"
SCOPES = "auth.api.routes.api.scopes"


class TestRolesValidationErrors:
    @pytest.mark.asyncio
    async def test_create_role_unknown_scope_is_a_400(self):
        from auth.api.routes.api.roles import create_role
        from auth.api.schemas.api.roles.schemas import CreateRoleRequest

        with (
            patch(
                f"{ROLES}._role_service.create_role",
                AsyncMock(side_effect=ValueError("Scope 1234 not found")),
            ),
            pytest.raises(HTTPException) as exc,
        ):
            await create_role(
                CreateRoleRequest(name="editor", description=None, scope_ids=[uuid.uuid4()]),
                AsyncMock(),
                _user(),
            )

        assert exc.value.status_code == 400
        assert "not found" in exc.value.detail

    @pytest.mark.asyncio
    async def test_update_role_unknown_scope_is_a_400(self):
        from auth.api.routes.api.roles import update_role
        from auth.api.schemas.api.roles.schemas import UpdateRoleRequest

        role = MagicMock()
        role.is_system = False

        with (
            patch(f"{ROLES}._role_service.get_by_id", AsyncMock(return_value=role)),
            patch(
                f"{ROLES}._role_service.update_role",
                AsyncMock(side_effect=ValueError("Scope 1234 not found")),
            ),
            pytest.raises(HTTPException) as exc,
        ):
            await update_role(
                uuid.uuid4(),
                UpdateRoleRequest(scope_ids=[uuid.uuid4()]),
                AsyncMock(),
                _user(),
            )

        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_assign_role_to_unknown_user_is_a_404(self):
        from auth.api.routes.api.roles import assign_role_to_user
        from auth.api.schemas.api.roles.schemas import AssignRoleRequest

        with (
            patch(f"{ROLES}._role_service.get_by_id", AsyncMock(return_value=MagicMock())),
            patch(f"{ROLES}._user_service.get_by_id", AsyncMock(return_value=None)),
            pytest.raises(HTTPException) as exc,
        ):
            await assign_role_to_user(
                uuid.uuid4(),
                AssignRoleRequest(user_id=uuid.uuid4()),
                AsyncMock(),
                _user(),
            )

        assert exc.value.status_code == 404
        assert exc.value.detail == "User not found"

    @pytest.mark.asyncio
    async def test_assign_unknown_scope_to_role_is_a_404(self):
        from auth.api.routes.api.roles import assign_scope_to_role

        with (
            patch(f"{ROLES}._role_service.get_by_id", AsyncMock(return_value=MagicMock())),
            patch(f"{ROLES}._role_service._get_scope_by_id", AsyncMock(return_value=None)),
            pytest.raises(HTTPException) as exc,
        ):
            await assign_scope_to_role(uuid.uuid4(), uuid.uuid4(), AsyncMock(), _user())

        assert exc.value.status_code == 404
        assert exc.value.detail == "Scope not found"


# ---------------------------------------------------------------------------
# auth.api.routes.api.scopes — full PATCH
# ---------------------------------------------------------------------------


class TestUpdateScopeAllFields:
    @pytest.mark.asyncio
    async def test_every_field_is_applied(self):
        from auth.api.routes.api.scopes import update_scope
        from auth.api.schemas.api.scopes.schemas import UpdateScopeRequest

        scope = MagicMock()
        scope.id = uuid.uuid4()
        scope.name = "users:read"
        scope.is_active = True
        scope.created_at = datetime.now(UTC)
        scope.updated_at = datetime.now(UTC)

        with (
            patch(f"{SCOPES}._scope_service.get_by_id", AsyncMock(return_value=scope)),
            patch(f"{SCOPES}._scope_service.name_exists", AsyncMock(return_value=False)),
        ):
            await update_scope(
                scope.id,
                UpdateScopeRequest(
                    name="users:list",
                    description="List users",
                    resource="users",
                    action="list",
                    category="identity",
                ),
                AsyncMock(),
                _user(),
            )

        assert scope.name == "users:list"
        assert scope.description == "List users"
        assert scope.resource == "users"
        assert scope.action == "list"
        assert scope.category == "identity"


# ---------------------------------------------------------------------------
# auth.api.routes.api.organisations.webhooks
# ---------------------------------------------------------------------------


class TestUpdateWebhookValidation:
    def _webhook(self):
        webhook = MagicMock()
        webhook.id = uuid.uuid4()
        webhook.url = "https://hooks.example.com/a"
        webhook.events = ["*"]
        return webhook


class TestUpdateScopePartial:
    @pytest.mark.asyncio
    async def test_omitted_fields_are_left_alone(self):
        from auth.api.routes.api.scopes import update_scope
        from auth.api.schemas.api.scopes.schemas import UpdateScopeRequest

        scope = MagicMock()
        scope.id = uuid.uuid4()
        scope.name = "users:read"
        scope.description = "Original"
        scope.resource = "users"
        scope.action = "read"
        scope.category = "identity"
        scope.is_active = True
        scope.created_at = datetime.now(UTC)
        scope.updated_at = datetime.now(UTC)

        with patch(f"{SCOPES}._scope_service.get_by_id", AsyncMock(return_value=scope)):
            await update_scope(scope.id, UpdateScopeRequest(), AsyncMock(), _user())

        assert scope.description == "Original"
        assert scope.resource == "users"
        assert scope.action == "read"
        assert scope.category == "identity"
