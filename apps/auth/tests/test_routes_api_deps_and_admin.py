# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the remaining branches of the API v1 route modules."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

DEPS = "auth.api.routes.api.deps"


def _admin():
    admin = MagicMock()
    admin.id = uuid.uuid4()
    return admin


# ---------------------------------------------------------------------------
# auth.api.routes.__init__
# ---------------------------------------------------------------------------


class TestRootRedirect:
    @pytest.mark.asyncio
    async def test_redirects_to_settings(self):
        from auth.api.routes import root_redirect

        result = await root_redirect()

        assert result.status_code == 302
        assert result.headers["location"] == "/auth/settings"


# ---------------------------------------------------------------------------
# auth.api.routes.api.deps.get_current_user_bearer
# ---------------------------------------------------------------------------


def _request():
    request = MagicMock()
    request.state = MagicMock()
    return request


class TestGetCurrentUserBearerRejections:
    @pytest.mark.asyncio
    async def test_invalid_pat_is_a_401(self):
        from auth.api.routes.api.deps import get_current_user_bearer
        from auth.services.pat import PAT_PREFIX

        with (
            patch(f"{DEPS}.validate_pat_token", AsyncMock(return_value=None)),
            pytest.raises(HTTPException) as exc,
        ):
            await get_current_user_bearer(_request(), AsyncMock(), f"{PAT_PREFIX}bad")

        assert exc.value.status_code == 401
        assert "personal access token" in exc.value.detail

    @pytest.mark.asyncio
    async def test_pat_for_inactive_user_is_a_401(self):
        from auth.api.routes.api.deps import get_current_user_bearer
        from auth.services.pat import PAT_PREFIX

        pat_auth = MagicMock()
        pat_auth.user_id = str(uuid.uuid4())
        pat_auth.scopes = ["users:read"]

        with (
            patch(f"{DEPS}.validate_pat_token", AsyncMock(return_value=pat_auth)),
            patch(f"{DEPS}._user_service.get_by_id", AsyncMock(return_value=None)),
            pytest.raises(HTTPException) as exc,
        ):
            await get_current_user_bearer(_request(), AsyncMock(), f"{PAT_PREFIX}good")

        assert exc.value.status_code == 401
        assert "User not found or inactive" in exc.value.detail

    @pytest.mark.asyncio
    async def test_invalid_bearer_is_a_401(self):
        from auth.api.routes.api.deps import get_current_user_bearer

        with (
            patch(f"{DEPS}.validate_bearer_token", AsyncMock(return_value=None)),
            pytest.raises(HTTPException) as exc,
        ):
            await get_current_user_bearer(_request(), AsyncMock(), "not.a.pat")

        assert exc.value.status_code == 401
        assert "access token" in exc.value.detail

    @pytest.mark.asyncio
    async def test_bearer_without_subject_is_a_401(self):
        from auth.api.routes.api.deps import get_current_user_bearer

        bearer = MagicMock()
        bearer.subject = None

        with (
            patch(f"{DEPS}.validate_bearer_token", AsyncMock(return_value=bearer)),
            pytest.raises(HTTPException) as exc,
        ):
            await get_current_user_bearer(_request(), AsyncMock(), "not.a.pat")

        assert exc.value.status_code == 401
        assert "no associated user" in exc.value.detail

    @pytest.mark.asyncio
    async def test_bearer_for_inactive_user_is_a_401(self):
        from auth.api.routes.api.deps import get_current_user_bearer

        bearer = MagicMock()
        bearer.subject = str(uuid.uuid4())
        bearer.scopes = ["users:read"]
        inactive = MagicMock()
        inactive.is_active = False

        with (
            patch(f"{DEPS}.validate_bearer_token", AsyncMock(return_value=bearer)),
            patch(f"{DEPS}._user_service.get_by_id", AsyncMock(return_value=inactive)),
            pytest.raises(HTTPException) as exc,
        ):
            await get_current_user_bearer(_request(), AsyncMock(), "not.a.pat")

        assert exc.value.status_code == 401


class TestGetOrgMemberCount:
    @pytest.mark.asyncio
    async def test_delegates_to_tenant_service(self):
        from auth.api.routes.api.deps import get_org_member_count

        db = AsyncMock()
        org_id = uuid.uuid4()

        with patch(f"{DEPS}._tenant_service.count_members", AsyncMock(return_value=7)) as count:
            assert await get_org_member_count(db, org_id) == 7

        count.assert_awaited_once_with(db, org_id)


class TestRequireOrgMembership:
    """The organisation guard of the REST API always checks a scope, there is no default."""

    @staticmethod
    def _membership(*scopes):
        from auth.db.models.tenant import TenantCustomRole, TenantMember

        return TenantMember(custom_role=TenantCustomRole(name="custom", scopes=list(scopes)))

    async def _call(self, membership, required_scope):
        from auth.api.routes.api.deps import require_org_membership

        user, tenant = MagicMock(), MagicMock()
        with (
            patch(f"{DEPS}._tenant_service.get_active_by_id", AsyncMock(return_value=tenant)),
            patch(f"{DEPS}._tenant_service.get_member", AsyncMock(return_value=membership)),
        ):
            return await require_org_membership(
                uuid.uuid4(), MagicMock(), AsyncMock(), user, required_scope=required_scope
            ), (user, tenant)

    def test_the_scope_is_a_required_parameter(self):
        import inspect

        from auth.api.routes.api.deps import require_org_membership

        parameter = inspect.signature(require_org_membership).parameters["required_scope"]
        assert parameter.default is inspect.Parameter.empty

    @pytest.mark.parametrize(
        ("held", "required"),
        [
            (("members:read",), "members:remove"),
            (("settings:read",), "settings:write"),
            (("idp:read",), "idp:delete"),
            ((), "branding:read"),
        ],
    )
    async def test_a_member_without_the_exact_scope_gets_403(self, held, required):
        with pytest.raises(HTTPException) as exc:
            await self._call(self._membership(*held), required)
        assert exc.value.status_code == 403
        assert required in exc.value.detail

    @pytest.mark.parametrize(
        ("held", "required"),
        [
            (("settings:write",), "settings:write"),
            (("idp:*",), "idp:delete"),
            (("*",), "roles:delete"),
        ],
    )
    async def test_a_member_holding_the_scope_or_a_wildcard_passes(self, held, required):
        (result, (user, tenant)) = await self._call(self._membership(*held), required)
        assert result[0] is user
        assert result[1] is tenant


# ---------------------------------------------------------------------------
# auth.api.routes.api.pats
# ---------------------------------------------------------------------------


def _make_pat():
    pat = MagicMock()
    pat.id = uuid.uuid4()
    pat.user_id = uuid.uuid4()
    pat.name = "CI token"
    pat.description = None
    pat.token_suffix = "abcd"
    pat.scopes = ["pats:read"]
    pat.tenant_id = None
    pat.target_client_id = None
    pat.expires_at = None
    pat.last_used_at = None
    pat.revoked_at = None
    pat.revocation_reason = None
    pat.created_at = datetime.now(UTC)
    return pat


class TestPrimaryEmailHelper:
    def test_none_user(self):
        from auth.api.routes.api.pats import _primary_email

        assert _primary_email(None) is None

    def test_no_primary_email(self):
        from auth.api.routes.api.pats import _primary_email

        user = MagicMock()
        secondary = MagicMock()
        secondary.is_primary = False
        user.emails = [secondary]

        assert _primary_email(user) is None

    def test_primary_email_found(self):
        from auth.api.routes.api.pats import _primary_email

        user = MagicMock()
        primary = MagicMock()
        primary.is_primary = True
        primary.email = "a@example.com"
        user.emails = [primary]

        assert _primary_email(user) == "a@example.com"


class TestListPats:
    @pytest.mark.asyncio
    async def test_pagination_offset_is_computed(self):
        from auth.api.routes.api.pats import list_pats

        pat_service = AsyncMock()
        pat_service.list_all_tokens = AsyncMock(return_value=([_make_pat()], 1))
        db = AsyncMock()

        result = await list_pats(
            db, _admin(), pat_service, page=3, page_size=10, include_revoked=True
        )

        assert result.total == 1
        assert result.page == 3
        pat_service.list_all_tokens.assert_awaited_once_with(
            db, include_revoked=True, offset=20, limit=10
        )


class TestRevokePat:
    @pytest.mark.asyncio
    async def test_success_returns_204(self):
        from auth.api.routes.api.pats import revoke_pat

        pat_service = AsyncMock()
        pat_service.revoke_token = AsyncMock(return_value=True)
        db = AsyncMock()

        result = await revoke_pat(uuid.uuid4(), db, _admin(), pat_service)

        assert result.status_code == 204
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_raises_404(self):
        from auth.api.routes.api.pats import revoke_pat

        pat_service = AsyncMock()
        pat_service.revoke_token = AsyncMock(return_value=False)

        with pytest.raises(HTTPException) as exc:
            await revoke_pat(uuid.uuid4(), AsyncMock(), _admin(), pat_service)

        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# auth.api.routes.api.sessions
# ---------------------------------------------------------------------------


class TestPrimaryEmailFromUser:
    def test_none_user(self):
        from auth.api.routes.api.sessions import _primary_email_from_user

        assert _primary_email_from_user(None) is None

    def test_user_without_emails(self):
        from auth.api.routes.api.sessions import _primary_email_from_user

        user = MagicMock()
        user.emails = []

        assert _primary_email_from_user(user) is None

    def test_falls_back_to_first_email(self):
        from auth.api.routes.api.sessions import _primary_email_from_user

        user = MagicMock()
        first = MagicMock()
        first.is_primary = False
        first.email = "first@example.com"
        user.emails = [first]

        assert _primary_email_from_user(user) == "first@example.com"


class TestRevokeSession:
    @pytest.mark.asyncio
    async def test_success_returns_204(self):
        from auth.api.routes.api.sessions import revoke_session

        session = MagicMock()
        session.user_id = uuid.uuid4()
        db = AsyncMock()

        with patch(
            "auth.api.routes.api.sessions._session_service.revoke_session_by_id_admin",
            AsyncMock(return_value=session),
        ):
            result = await revoke_session(uuid.uuid4(), db, _admin())

        assert result.status_code == 204

    @pytest.mark.asyncio
    async def test_missing_raises_404(self):
        from auth.api.routes.api.sessions import revoke_session

        with (
            patch(
                "auth.api.routes.api.sessions._session_service.revoke_session_by_id_admin",
                AsyncMock(return_value=None),
            ),
            pytest.raises(HTTPException) as exc,
        ):
            await revoke_session(uuid.uuid4(), AsyncMock(), _admin())

        assert exc.value.status_code == 404
