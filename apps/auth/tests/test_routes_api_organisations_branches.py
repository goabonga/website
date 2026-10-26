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

ORG_MEMBERS = "auth.api.routes.api.organisations.members"
ME_MEMBERS = "auth.api.routes.api.me.organisations.members"
ORG_TRUST = "auth.api.routes.api.organisations.trust"
ME_TRUST = "auth.api.routes.api.me.organisations.trust"
ORG_IDPS = "auth.api.routes.api.organisations.idps"
ME_IDPS = "auth.api.routes.api.me.organisations.idps"
ORG_ROLES = "auth.api.routes.api.organisations.roles"
ORG_ROOT = "auth.api.routes.api.organisations"


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


@pytest.mark.parametrize("module", [ORG_MEMBERS, ME_MEMBERS])
class TestAddMemberWithExplicitRole:
    def _body(self, role_id):
        from auth.api.schemas.api.organisations.schemas import AddMemberRequest

        return AddMemberRequest(user_id=uuid.uuid4(), role_id=role_id)

    @pytest.mark.asyncio
    async def test_role_from_another_org_is_rejected(self, module):
        import importlib

        mod = importlib.import_module(module)
        tenant = _tenant()
        foreign_role = MagicMock()
        foreign_role.tenant_id = uuid.uuid4()

        with (
            patch(
                f"{module}.require_org_membership",
                AsyncMock(return_value=(_user(), tenant, MagicMock())),
            ),
            patch(f"{module}._tenant_service.get_member", AsyncMock(return_value=None)),
            patch(
                f"{module}.tenant_role_service.get_role_by_id",
                AsyncMock(return_value=foreign_role),
            ),
            pytest.raises(HTTPException) as exc,
        ):
            await mod.add_member(
                tenant.id, self._body(uuid.uuid4()), MagicMock(), AsyncMock(), _user()
            )

        assert exc.value.status_code == 400
        assert "Role not found" in exc.value.detail

    @pytest.mark.asyncio
    async def test_unknown_role_is_rejected(self, module):
        import importlib

        mod = importlib.import_module(module)
        tenant = _tenant()

        with (
            patch(
                f"{module}.require_org_membership",
                AsyncMock(return_value=(_user(), tenant, MagicMock())),
            ),
            patch(f"{module}._tenant_service.get_member", AsyncMock(return_value=None)),
            patch(f"{module}.tenant_role_service.get_role_by_id", AsyncMock(return_value=None)),
            pytest.raises(HTTPException) as exc,
        ):
            await mod.add_member(
                tenant.id, self._body(uuid.uuid4()), MagicMock(), AsyncMock(), _user()
            )

        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_valid_role_is_assigned(self, module):
        import importlib

        mod = importlib.import_module(module)
        tenant = _tenant()
        role = MagicMock()
        role.tenant_id = tenant.id
        role.id = uuid.uuid4()
        member = _member(tenant.id, uuid.uuid4())

        with (
            patch(
                f"{module}.require_org_membership",
                AsyncMock(return_value=(_user(), tenant, MagicMock())),
            ),
            patch(f"{module}._tenant_service.get_member", AsyncMock(return_value=None)),
            patch(f"{module}.tenant_role_service.get_role_by_id", AsyncMock(return_value=role)),
            patch(f"{module}._tenant_service.add_member", AsyncMock()),
            patch(f"{module}._tenant_service.get_member_by_id", AsyncMock(return_value=member)),
        ):
            result = await mod.add_member(
                tenant.id, self._body(role.id), MagicMock(), AsyncMock(), _user()
            )

        assert result.role_name == "owner"

    @pytest.mark.asyncio
    async def test_reload_miss_keeps_the_staged_member(self, module):
        import importlib

        mod = importlib.import_module(module)
        tenant = _tenant()
        role = MagicMock()
        role.tenant_id = tenant.id
        role.id = uuid.uuid4()

        with (
            patch(
                f"{module}.require_org_membership",
                AsyncMock(return_value=(_user(), tenant, MagicMock())),
            ),
            patch(f"{module}._tenant_service.get_member", AsyncMock(return_value=None)),
            patch(f"{module}.tenant_role_service.get_role_by_id", AsyncMock(return_value=role)),
            patch(f"{module}._tenant_service.add_member", _stamping_add_member()),
            patch(f"{module}._tenant_service.get_member_by_id", AsyncMock(return_value=None)),
        ):
            result = await mod.add_member(
                tenant.id, self._body(role.id), MagicMock(), AsyncMock(), _user()
            )

        assert result is not None


@pytest.mark.parametrize("module", [ORG_MEMBERS, ME_MEMBERS])
class TestUpdateMemberReloadMiss:
    @pytest.mark.asyncio
    async def test_reload_miss_keeps_the_updated_member(self, module):
        import importlib

        from auth.api.schemas.api.organisations.schemas import UpdateMemberRequest

        mod = importlib.import_module(module)
        tenant = _tenant()
        target_user_id = uuid.uuid4()
        member = _member(tenant.id, target_user_id)
        role = MagicMock()
        role.tenant_id = tenant.id
        role.id = uuid.uuid4()

        with (
            patch(
                f"{module}.require_org_membership",
                AsyncMock(return_value=(_user(), tenant, MagicMock())),
            ),
            patch(f"{module}._tenant_service.get_member", AsyncMock(return_value=member)),
            patch(f"{module}.tenant_role_service.get_role_by_id", AsyncMock(return_value=role)),
            patch(f"{module}.tenant_role_service.assign_role", AsyncMock()),
            patch(f"{module}._tenant_service.get_member_by_id", AsyncMock(return_value=None)),
        ):
            result = await mod.update_member(
                tenant.id,
                target_user_id,
                UpdateMemberRequest(role_id=role.id),
                MagicMock(),
                AsyncMock(),
                _user(),
            )

        assert result.user_id == target_user_id


# ---------------------------------------------------------------------------
# trust — organisation lookups that come back empty
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module", [ORG_TRUST, ME_TRUST])
class TestTrustMissingOrganisation:
    @pytest.mark.asyncio
    async def test_update_mode_on_unknown_org(self, module):
        import importlib

        from auth.api.schemas.api.organisations.schemas import UpdateTrustModeRequest

        mod = importlib.import_module(module)
        org_id = uuid.uuid4()
        trust_service = AsyncMock()
        trust_service.update_trust_mode = AsyncMock(return_value=False)

        with (
            patch(
                f"{module}.require_org_membership",
                AsyncMock(return_value=(_user(), _tenant(), MagicMock())),
            ),
            pytest.raises(HTTPException) as exc,
        ):
            await mod.update_trust_mode(
                org_id,
                UpdateTrustModeRequest(mode="all"),
                MagicMock(),
                AsyncMock(),
                _user(),
                trust_service,
            )

        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_config_disappears_after_mode_update(self, module):
        import importlib

        from auth.api.schemas.api.organisations.schemas import UpdateTrustModeRequest

        mod = importlib.import_module(module)
        trust_service = AsyncMock()
        trust_service.update_trust_mode = AsyncMock(return_value=True)
        trust_service.get_tenant_trust_config = AsyncMock(return_value=None)

        with (
            patch(
                f"{module}.require_org_membership",
                AsyncMock(return_value=(_user(), _tenant(), MagicMock())),
            ),
            pytest.raises(HTTPException) as exc,
        ):
            await mod.update_trust_mode(
                uuid.uuid4(),
                UpdateTrustModeRequest(mode="all"),
                MagicMock(),
                AsyncMock(),
                _user(),
                trust_service,
            )

        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_config_disappears_after_adding_a_source(self, module):
        import importlib

        from auth.api.schemas.api.organisations.schemas import AddTrustedSourceRequest

        mod = importlib.import_module(module)
        trust_service = AsyncMock()
        trust_service.add_trusted_source = AsyncMock(return_value=True)
        trust_service.get_tenant_trust_config = AsyncMock(return_value=None)

        with (
            patch(
                f"{module}.require_org_membership",
                AsyncMock(return_value=(_user(), _tenant(), MagicMock())),
            ),
            pytest.raises(HTTPException) as exc,
        ):
            await mod.add_trusted_source(
                uuid.uuid4(),
                AddTrustedSourceRequest(source_tenant_id=uuid.uuid4()),
                MagicMock(),
                AsyncMock(),
                _user(),
                trust_service,
            )

        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# IdP creation without a client secret
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("module", "handler"),
    [(ORG_IDPS, "create_org_idp"), (ME_IDPS, "create_my_org_idp")],
)
class TestCreateIdpWithoutSecret:
    @pytest.mark.asyncio
    async def test_no_secret_leaves_the_column_null(self, module, handler):
        import importlib

        from auth.api.schemas.api.organisations.schemas import CreateIdPRequest

        mod = importlib.import_module(module)
        tenant = _tenant()

        body = CreateIdPRequest(
            name="Google",
            provider_type="google",
            client_id="client-id",
            client_secret=None,
        )

        staged = {}

        async def _add_idp(_db, idp):
            staged["idp"] = idp
            idp.id = uuid.uuid4()
            idp.created_at = datetime.now(UTC)
            idp.updated_at = datetime.now(UTC)

        with (
            patch(
                f"{module}.require_org_membership",
                AsyncMock(return_value=(_user(), tenant, MagicMock())),
            ),
            patch(f"{module}._tenant_service.add_idp", AsyncMock(side_effect=_add_idp)),
            patch(f"{module}.encrypt_value") as encrypt,
        ):
            await getattr(mod, handler)(tenant.id, body, MagicMock(), AsyncMock(), _user())

        encrypt.assert_not_called()
        assert staged["idp"].client_secret_encrypted is None


# ---------------------------------------------------------------------------
# Role update: is_default left unchanged
# ---------------------------------------------------------------------------


class TestUpdateRoleDefaultFlagUnchanged:
    @pytest.mark.asyncio
    async def test_clearing_a_non_default_role_is_a_no_op(self):
        from auth.api.routes.api.organisations.roles import update_role
        from auth.api.schemas.api.organisations.schemas import UpdateRoleRequest

        tenant = _tenant()
        role = MagicMock()
        role.id = uuid.uuid4()
        role.tenant_id = tenant.id
        role.name = "viewer"
        role.display_name = "Viewer"
        role.description = None
        role.scopes = ["members:read"]
        role.is_default = False
        role.is_system = False
        role.created_at = datetime.now(UTC)
        role.updated_at = datetime.now(UTC)

        with (
            patch(
                f"{ORG_ROLES}.require_org_membership",
                AsyncMock(return_value=(_user(), tenant, MagicMock())),
            ),
            patch(f"{ORG_ROLES}.tenant_role_service.get_role_by_id", AsyncMock(return_value=role)),
            patch(f"{ORG_ROLES}.tenant_role_service.update_role", AsyncMock(return_value=role)),
            patch(f"{ORG_ROLES}.tenant_role_service.set_default_role", AsyncMock()) as set_default,
            patch(
                f"{ORG_ROLES}.tenant_role_service.clear_default_role", AsyncMock()
            ) as clear_default,
        ):
            await update_role(
                tenant.id,
                role.id,
                UpdateRoleRequest(is_default=False),
                MagicMock(),
                AsyncMock(),
                _user(),
            )

        set_default.assert_not_awaited()
        clear_default.assert_not_awaited()


# ---------------------------------------------------------------------------
# get_organisation as a non-admin
# ---------------------------------------------------------------------------


class TestGetOrganisationNonAdmin:
    @pytest.mark.asyncio
    async def test_inactive_org_is_a_404(self):
        from auth.api.routes.api.organisations import get_organisation

        request = MagicMock()
        request.state = MagicMock()
        request.state.auth_scopes = []

        with (
            patch(f"{ORG_ROOT}.token_has_scope", return_value=False),
            patch(f"{ORG_ROOT}._tenant_service.get_active_by_id", AsyncMock(return_value=None)),
            pytest.raises(HTTPException) as exc,
        ):
            await get_organisation(uuid.uuid4(), request, AsyncMock(), _user())

        assert exc.value.status_code == 404


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
WEBHOOKS = "auth.api.routes.api.organisations.webhooks"


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


class TestSanitizeEvents:
    def test_blank_and_duplicate_values_are_dropped(self):
        from auth.api.routes.api.organisations.webhooks import _sanitize_events

        assert _sanitize_events(["", "   ", "*", "*"]) == ["*"]

    def test_unknown_wildcard_prefix_is_dropped(self):
        from auth.api.routes.api.organisations.webhooks import _sanitize_events

        assert _sanitize_events(["nosuchgroup.*"]) == []

    def test_known_group_wildcard_is_kept(self):
        from auth.api.routes.api.organisations.webhooks import _sanitize_events
        from auth.db.models.tenant import WebhookEvent

        prefix = next(iter(WebhookEvent)).value.split(".")[0]

        assert _sanitize_events([f"{prefix}.*"]) == [f"{prefix}.*"]


class TestUpdateWebhookValidation:
    def _webhook(self):
        webhook = MagicMock()
        webhook.id = uuid.uuid4()
        webhook.url = "https://hooks.example.com/a"
        webhook.events = ["*"]
        return webhook

    @pytest.mark.asyncio
    async def test_empty_event_list_is_a_400(self):
        from auth.api.routes.api.organisations.webhooks import update_org_webhook
        from auth.api.schemas.api.organisations.schemas import UpdateWebhookRequest

        with (
            patch(f"{WEBHOOKS}.require_org_membership", AsyncMock()),
            patch(f"{WEBHOOKS}._get_org_webhook", AsyncMock(return_value=self._webhook())),
            pytest.raises(HTTPException) as exc,
        ):
            await update_org_webhook(
                uuid.uuid4(),
                uuid.uuid4(),
                UpdateWebhookRequest(events=["not-an-event"]),
                MagicMock(),
                AsyncMock(),
                _user(),
            )

        assert exc.value.status_code == 400
        assert "at least one recognised event" in exc.value.detail

    @pytest.mark.asyncio
    async def test_unsafe_url_is_a_400(self):
        from auth.api.routes.api.organisations.webhooks import update_org_webhook
        from auth.api.schemas.api.organisations.schemas import UpdateWebhookRequest
        from auth.services.webhook import WebhookURLError

        with (
            patch(f"{WEBHOOKS}.require_org_membership", AsyncMock()),
            patch(f"{WEBHOOKS}._get_org_webhook", AsyncMock(return_value=self._webhook())),
            patch(
                f"{WEBHOOKS}.validate_target_url",
                side_effect=WebhookURLError("private address"),
            ),
            pytest.raises(HTTPException) as exc,
        ):
            await update_org_webhook(
                uuid.uuid4(),
                uuid.uuid4(),
                UpdateWebhookRequest(url="http://127.0.0.1/hook"),
                MagicMock(),
                AsyncMock(),
                _user(),
            )

        assert exc.value.status_code == 400
        assert exc.value.detail == "private address"

    @pytest.mark.asyncio
    async def test_explicit_nulls_are_ignored(self):
        from auth.api.routes.api.organisations.webhooks import update_org_webhook
        from auth.api.schemas.api.organisations.schemas import UpdateWebhookRequest

        webhook = self._webhook()
        webhook.name = "Original"

        with (
            patch(f"{WEBHOOKS}.require_org_membership", AsyncMock()),
            patch(f"{WEBHOOKS}._get_org_webhook", AsyncMock(return_value=webhook)),
            patch(f"{WEBHOOKS}.webhook_service.save", AsyncMock()),
            patch(f"{WEBHOOKS}._webhook_to_response", return_value="response"),
        ):
            result = await update_org_webhook(
                uuid.uuid4(),
                uuid.uuid4(),
                UpdateWebhookRequest(name=None),
                MagicMock(),
                AsyncMock(),
                _user(),
            )

        assert result == "response"
        assert webhook.name == "Original"


class TestTestWebhookUnsafeUrl:
    @pytest.mark.asyncio
    async def test_unsafe_url_is_a_400(self):
        from auth.api.routes.api.organisations.webhooks import test_org_webhook
        from auth.services.webhook import WebhookURLError

        webhook = MagicMock()
        webhook.url = "http://127.0.0.1/hook"

        with (
            patch(f"{WEBHOOKS}.require_org_membership", AsyncMock()),
            patch(f"{WEBHOOKS}._get_org_webhook", AsyncMock(return_value=webhook)),
            patch(
                f"{WEBHOOKS}.validate_target_url",
                side_effect=WebhookURLError("private address"),
            ),
            pytest.raises(HTTPException) as exc,
        ):
            await test_org_webhook(uuid.uuid4(), uuid.uuid4(), MagicMock(), AsyncMock(), _user())

        assert exc.value.status_code == 400


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
