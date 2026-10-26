# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the introspection paths of reachy_mini_api/auth/dependencies.py."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException
from reachy_mini_api.auth.dependencies import (
    _is_jwt_token,
    get_auth_context,
    require_scopes,
)
from reachy_mini_api.auth.introspection import TokenRevokedError

# ---------------------------------------------------------------------------
# _is_jwt_token
# ---------------------------------------------------------------------------


class TestIsJwtToken:
    def test_three_non_empty_parts_returns_true(self):
        assert _is_jwt_token("header.payload.signature") is True

    def test_real_jwt_format_returns_true(self):
        assert _is_jwt_token("eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.sig") is True

    def test_opaque_token_returns_false(self):
        assert _is_jwt_token("ory_pat_abc123def456") is False

    def test_two_parts_returns_false(self):
        assert _is_jwt_token("header.payload") is False

    def test_four_parts_returns_false(self):
        assert _is_jwt_token("a.b.c.d") is False

    def test_empty_part_returns_false(self):
        assert _is_jwt_token("header..signature") is False

    def test_plain_string_returns_false(self):
        assert _is_jwt_token("simple-token") is False

    def test_empty_string_returns_false(self):
        assert _is_jwt_token("") is False


def _claims(scope="resource:read", **extra):
    return {"sub": str(uuid4()), "scope": scope, **extra}


@pytest.fixture
def introspection():
    """Patch the introspection client used by the dependencies."""
    with patch("reachy_mini_api.auth.dependencies.introspection_client") as mock:
        mock.validate_token_with_introspection = AsyncMock(return_value=_claims())
        mock.validate_opaque_token = AsyncMock(return_value=_claims())
        yield mock


class TestGetAuthContext:
    async def test_jwt_goes_through_signature_and_revocation_check(self, introspection):
        ctx = await get_auth_context(request=MagicMock(), token="a.b.c")
        introspection.validate_token_with_introspection.assert_awaited_once_with("a.b.c")
        introspection.validate_opaque_token.assert_not_awaited()
        assert ctx.scopes == ["resource:read"]

    async def test_opaque_token_uses_introspection_only(self, introspection):
        ctx = await get_auth_context(request=MagicMock(), token="ory_pat_abc123")
        introspection.validate_opaque_token.assert_awaited_once_with("ory_pat_abc123")
        introspection.validate_token_with_introspection.assert_not_awaited()
        assert ctx.scopes == ["resource:read"]

    async def test_revoked_jwt_raises_401(self, introspection):
        introspection.validate_token_with_introspection.side_effect = TokenRevokedError("revoked")
        with pytest.raises(HTTPException) as exc_info:
            await get_auth_context(request=MagicMock(), token="a.b.c")
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Token has been revoked"

    async def test_revoked_opaque_token_raises_401(self, introspection):
        introspection.validate_opaque_token.side_effect = TokenRevokedError("inactive")
        with pytest.raises(HTTPException) as exc_info:
            await get_auth_context(request=MagicMock(), token="ory_pat_revoked")
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Token has been revoked"

    async def test_invalid_jwt_raises_401(self, introspection):
        introspection.validate_token_with_introspection.side_effect = jwt.InvalidTokenError("bad")
        with pytest.raises(HTTPException) as exc_info:
            await get_auth_context(request=MagicMock(), token="a.b.c")
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid token"

    async def test_client_id_falls_back_to_settings(self, introspection):
        request = MagicMock()
        with patch("reachy_mini_api.auth.dependencies.settings") as mock_settings:
            mock_settings.oauth2_client_id = "configured-client"
            await get_auth_context(request=request, token="a.b.c")
        assert request.state.client_id == "configured-client"


class TestRequireScopes:
    async def test_jwt_with_scope(self, introspection):
        ctx = await require_scopes("resource:read")(request=MagicMock(), token="a.b.c")
        assert ctx.has_scope("resource:read")
        introspection.validate_token_with_introspection.assert_awaited_once_with("a.b.c")

    async def test_opaque_token_with_scope(self, introspection):
        claims = _claims(scope="resource:read resource:write", client_id="svc")
        introspection.validate_opaque_token.return_value = claims
        ctx = await require_scopes("resource:read")(request=MagicMock(), token="ory_pat_abc")
        assert ctx.scopes == ["resource:read", "resource:write"]
        introspection.validate_opaque_token.assert_awaited_once_with("ory_pat_abc")

    async def test_opaque_token_without_scope_raises_403(self, introspection):
        introspection.validate_opaque_token.return_value = _claims(scope="openid")
        with pytest.raises(HTTPException) as exc_info:
            await require_scopes("resource:read")(request=MagicMock(), token="ory_pat_abc")
        assert exc_info.value.status_code == 403

    @pytest.mark.parametrize("token", ["a.b.c", "ory_pat_revoked"])
    async def test_revoked_raises_401(self, introspection, token):
        introspection.validate_token_with_introspection.side_effect = TokenRevokedError("x")
        introspection.validate_opaque_token.side_effect = TokenRevokedError("x")
        with pytest.raises(HTTPException) as exc_info:
            await require_scopes("resource:read")(request=MagicMock(), token=token)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Token has been revoked"

    async def test_introspection_failure_raises_401(self, introspection):
        introspection.validate_opaque_token.side_effect = Exception("introspection failed")
        with pytest.raises(HTTPException) as exc_info:
            await require_scopes("resource:read")(request=MagicMock(), token="ory_pat_bad")
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid token"
