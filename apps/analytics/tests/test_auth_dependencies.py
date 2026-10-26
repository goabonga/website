# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for analytics.auth.dependencies module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from analytics.auth.jwt import TokenRevokedError
from analytics.auth.models import User
from analytics.auth.token_exchange import TokenExchangeError
from fastapi import HTTPException
from fastapi.security import OAuth2AuthorizationCodeBearer


class TestNoAuth:
    """Tests for _no_auth function."""

    async def test_no_auth_returns_none(self):
        from analytics.auth.dependencies import _no_auth

        result = await _no_auth()
        assert result is None


class TestGetOAuth2Scheme:
    """Tests for _get_oauth2_scheme function."""

    def test_returns_no_auth_when_issuer_empty(self):
        with patch("analytics.auth.dependencies.settings") as mock_settings:
            mock_settings.oauth2_issuer = ""
            from analytics.auth.dependencies import _get_oauth2_scheme, _no_auth

            result = _get_oauth2_scheme()
            assert result is _no_auth

    def test_returns_oauth2_scheme_when_issuer_set(self):
        with patch("analytics.auth.dependencies.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            from analytics.auth.dependencies import _get_oauth2_scheme

            result = _get_oauth2_scheme()
            assert isinstance(result, OAuth2AuthorizationCodeBearer)

    def test_returns_oauth2_scheme_strips_trailing_slash(self):
        with patch("analytics.auth.dependencies.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com/"
            from analytics.auth.dependencies import _get_oauth2_scheme

            result = _get_oauth2_scheme()
            assert isinstance(result, OAuth2AuthorizationCodeBearer)


class TestGetCurrentUser:
    """Tests for get_current_user dependency."""

    async def test_no_token_raises_401(self):
        from analytics.auth.dependencies import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token=None)
        assert exc_info.value.status_code == 401
        assert "Missing authorization token" in exc_info.value.detail

    async def test_no_oauth2_issuer_raises_503(self):
        with patch("analytics.auth.dependencies.settings") as mock_settings:
            mock_settings.oauth2_issuer = ""
            from analytics.auth.dependencies import get_current_user

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(token="some-token")
            assert exc_info.value.status_code == 503
            assert "OAuth2 not configured" in exc_info.value.detail

    async def test_valid_token_returns_user(self):
        with patch("analytics.auth.dependencies.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            with patch("analytics.auth.dependencies.jwt_validator") as mock_validator:
                mock_validator.validate_token_with_introspection = AsyncMock(
                    return_value={
                        "sub": "550e8400-e29b-41d4-a716-446655440000",
                        "email": "user@example.com",
                        "name": "Test User",
                        "scope": "openid profile",
                    }
                )
                from analytics.auth.dependencies import get_current_user

                result = await get_current_user(token="valid-token")
                assert isinstance(result, User)
                assert result.email == "user@example.com"
                assert result.name == "Test User"

    async def test_token_revoked_raises_401(self):
        with patch("analytics.auth.dependencies.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            with patch("analytics.auth.dependencies.jwt_validator") as mock_validator:
                mock_validator.validate_token_with_introspection = AsyncMock(
                    side_effect=TokenRevokedError("Token has been revoked")
                )
                from analytics.auth.dependencies import get_current_user

                with pytest.raises(HTTPException) as exc_info:
                    await get_current_user(token="revoked-token")
                assert exc_info.value.status_code == 401
                assert "Token has been revoked" in exc_info.value.detail
                assert 'error="invalid_token"' in exc_info.value.headers["WWW-Authenticate"]

    async def test_other_exception_raises_401(self):
        with patch("analytics.auth.dependencies.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            with patch("analytics.auth.dependencies.jwt_validator") as mock_validator:
                mock_validator.validate_token_with_introspection = AsyncMock(
                    side_effect=Exception("Something went wrong")
                )
                from analytics.auth.dependencies import get_current_user

                with pytest.raises(HTTPException) as exc_info:
                    await get_current_user(token="bad-token")
                assert exc_info.value.status_code == 401
                assert "Invalid token" in exc_info.value.detail


class TestRequireScopes:
    """Tests for require_scopes dependency factory."""

    def test_returns_callable(self):
        from analytics.auth.dependencies import require_scopes

        dep = require_scopes("analytics:read")
        assert callable(dep)

    async def test_no_oauth2_issuer_raises_503(self):
        with patch("analytics.auth.dependencies.settings") as mock_settings:
            mock_settings.oauth2_issuer = ""
            from analytics.auth.dependencies import require_scopes

            dep = require_scopes("analytics:read")
            mock_request = MagicMock()
            with pytest.raises(HTTPException) as exc_info:
                await dep(request=mock_request, token="some-token")
            assert exc_info.value.status_code == 503
            assert "OAuth2 not configured" in exc_info.value.detail

    async def test_no_token_raises_401(self):
        with patch("analytics.auth.dependencies.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            from analytics.auth.dependencies import require_scopes

            dep = require_scopes("analytics:read")
            mock_request = MagicMock()
            with pytest.raises(HTTPException) as exc_info:
                await dep(request=mock_request, token=None)
            assert exc_info.value.status_code == 401
            assert "Missing authorization token" in exc_info.value.detail

    # --- Token exchange path ---

    async def test_token_exchange_success(self):
        """Test require_scopes with token exchange configured and scopes: success."""
        with patch("analytics.auth.dependencies.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            with patch("analytics.auth.dependencies.token_exchange_client") as mock_tex:
                mock_tex.is_configured = True
                mock_tex.validate_token_scopes = AsyncMock(
                    return_value={"scope": "analytics:read analytics:write"}
                )
                with patch("analytics.auth.dependencies.jwt_validator") as mock_validator:
                    mock_validator.validate_token_with_introspection = AsyncMock(
                        return_value={
                            "sub": "550e8400-e29b-41d4-a716-446655440000",
                            "email": "user@example.com",
                            "name": "Test User",
                        }
                    )
                    from analytics.auth.dependencies import require_scopes

                    dep = require_scopes("analytics:read")
                    mock_request = MagicMock()
                    result = await dep(request=mock_request, token="valid-token")
                    assert isinstance(result, User)
                    assert "analytics:read" in result.scopes
                    assert "analytics:write" in result.scopes
                    assert result.email == "user@example.com"
                    assert result.name == "Test User"

    async def test_token_exchange_invalid_grant_raises_401(self):
        """Test require_scopes token exchange with invalid_grant error."""
        with patch("analytics.auth.dependencies.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            with patch("analytics.auth.dependencies.token_exchange_client") as mock_tex:
                mock_tex.is_configured = True
                mock_tex.validate_token_scopes = AsyncMock(
                    side_effect=TokenExchangeError(
                        "invalid_grant: Token expired", error_code="invalid_grant"
                    )
                )
                from analytics.auth.dependencies import require_scopes

                dep = require_scopes("analytics:read")
                mock_request = MagicMock()
                with pytest.raises(HTTPException) as exc_info:
                    await dep(request=mock_request, token="expired-token")
                assert exc_info.value.status_code == 401
                assert "Invalid or expired token" in exc_info.value.detail

    async def test_token_exchange_insufficient_scope_raises_403(self):
        """Test require_scopes token exchange with insufficient_scope error."""
        with patch("analytics.auth.dependencies.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            with patch("analytics.auth.dependencies.token_exchange_client") as mock_tex:
                mock_tex.is_configured = True
                mock_tex.validate_token_scopes = AsyncMock(
                    side_effect=TokenExchangeError(
                        "insufficient_scope: Missing scopes",
                        error_code="insufficient_scope",
                    )
                )
                from analytics.auth.dependencies import require_scopes

                dep = require_scopes("analytics:read")
                mock_request = MagicMock()
                with pytest.raises(HTTPException) as exc_info:
                    await dep(request=mock_request, token="valid-but-no-scope")
                assert exc_info.value.status_code == 403
                assert "Insufficient scopes" in exc_info.value.detail
                assert "analytics:read" in exc_info.value.detail

    async def test_token_exchange_other_error_raises_401(self):
        """Test require_scopes token exchange with other error code."""
        with patch("analytics.auth.dependencies.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            with patch("analytics.auth.dependencies.token_exchange_client") as mock_tex:
                mock_tex.is_configured = True
                mock_tex.validate_token_scopes = AsyncMock(
                    side_effect=TokenExchangeError(
                        "server_error: Internal error",
                        error_code="server_error",
                    )
                )
                from analytics.auth.dependencies import require_scopes

                dep = require_scopes("analytics:read")
                mock_request = MagicMock()
                with pytest.raises(HTTPException) as exc_info:
                    await dep(request=mock_request, token="some-token")
                assert exc_info.value.status_code == 401
                assert "server_error: Internal error" in exc_info.value.detail

    async def test_token_exchange_with_original_validation_failure_fallback(self):
        """Test require_scopes with token exchange success but original validation fails."""
        with patch("analytics.auth.dependencies.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            with patch("analytics.auth.dependencies.token_exchange_client") as mock_tex:
                mock_tex.is_configured = True
                mock_tex.validate_token_scopes = AsyncMock(return_value={"scope": "analytics:read"})
                with patch("analytics.auth.dependencies.jwt_validator") as mock_validator:
                    mock_validator.validate_token_with_introspection = AsyncMock(
                        side_effect=Exception("Token validation failed")
                    )
                    from analytics.auth.dependencies import require_scopes

                    dep = require_scopes("analytics:read")
                    mock_request = MagicMock()
                    result = await dep(request=mock_request, token="valid-token")
                    assert isinstance(result, User)
                    assert result.id == ""
                    assert result.email is None
                    assert result.name is None
                    assert "analytics:read" in result.scopes

    # --- Without token exchange (fallback path) ---

    async def test_without_token_exchange_valid_token_has_scopes(self):
        """Test require_scopes without token exchange: valid token with required scopes."""
        with patch("analytics.auth.dependencies.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            with patch("analytics.auth.dependencies.token_exchange_client") as mock_tex:
                mock_tex.is_configured = False
                with patch("analytics.auth.dependencies.jwt_validator") as mock_validator:
                    mock_validator.validate_token_with_introspection = AsyncMock(
                        return_value={
                            "sub": "550e8400-e29b-41d4-a716-446655440000",
                            "email": "user@example.com",
                            "name": "Test User",
                            "scope": "analytics:read analytics:write",
                        }
                    )
                    from analytics.auth.dependencies import require_scopes

                    dep = require_scopes("analytics:read")
                    mock_request = MagicMock()
                    result = await dep(request=mock_request, token="valid-token")
                    assert isinstance(result, User)
                    assert result.email == "user@example.com"

    async def test_without_token_exchange_missing_scopes_raises_403(self):
        """Test require_scopes without token exchange: valid token but missing scopes."""
        with patch("analytics.auth.dependencies.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            with patch("analytics.auth.dependencies.token_exchange_client") as mock_tex:
                mock_tex.is_configured = False
                with patch("analytics.auth.dependencies.jwt_validator") as mock_validator:
                    mock_validator.validate_token_with_introspection = AsyncMock(
                        return_value={
                            "sub": "550e8400-e29b-41d4-a716-446655440000",
                            "email": "user@example.com",
                            "name": "Test User",
                            "scope": "openid profile",
                        }
                    )
                    from analytics.auth.dependencies import require_scopes

                    dep = require_scopes("analytics:read")
                    mock_request = MagicMock()
                    with pytest.raises(HTTPException) as exc_info:
                        await dep(request=mock_request, token="valid-token")
                    assert exc_info.value.status_code == 403
                    assert "Insufficient scopes" in exc_info.value.detail
                    assert "analytics:read" in exc_info.value.detail

    async def test_without_token_exchange_token_revoked_raises_401(self):
        """Test require_scopes without token exchange: TokenRevokedError raises 401."""
        with patch("analytics.auth.dependencies.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            with patch("analytics.auth.dependencies.token_exchange_client") as mock_tex:
                mock_tex.is_configured = False
                with patch("analytics.auth.dependencies.jwt_validator") as mock_validator:
                    mock_validator.validate_token_with_introspection = AsyncMock(
                        side_effect=TokenRevokedError("Token has been revoked")
                    )
                    from analytics.auth.dependencies import require_scopes

                    dep = require_scopes("analytics:read")
                    mock_request = MagicMock()
                    with pytest.raises(HTTPException) as exc_info:
                        await dep(request=mock_request, token="revoked-token")
                    assert exc_info.value.status_code == 401
                    assert "Token has been revoked" in exc_info.value.detail

    async def test_without_token_exchange_other_exception_raises_401(self):
        """Test require_scopes without token exchange: other exception raises 401."""
        with patch("analytics.auth.dependencies.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            with patch("analytics.auth.dependencies.token_exchange_client") as mock_tex:
                mock_tex.is_configured = False
                with patch("analytics.auth.dependencies.jwt_validator") as mock_validator:
                    mock_validator.validate_token_with_introspection = AsyncMock(
                        side_effect=Exception("Unexpected error")
                    )
                    from analytics.auth.dependencies import require_scopes

                    dep = require_scopes("analytics:read")
                    mock_request = MagicMock()
                    with pytest.raises(HTTPException) as exc_info:
                        await dep(request=mock_request, token="bad-token")
                    assert exc_info.value.status_code == 401
                    assert "Invalid token" in exc_info.value.detail

    async def test_token_exchange_not_used_when_no_scopes(self):
        """Test require_scopes skips token exchange when no scopes required (empty scopes_list)."""
        with patch("analytics.auth.dependencies.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            with patch("analytics.auth.dependencies.token_exchange_client") as mock_tex:
                mock_tex.is_configured = True
                with patch("analytics.auth.dependencies.jwt_validator") as mock_validator:
                    mock_validator.validate_token_with_introspection = AsyncMock(
                        return_value={
                            "sub": "550e8400-e29b-41d4-a716-446655440000",
                            "email": "user@example.com",
                            "name": "Test User",
                            "scope": "",
                        }
                    )
                    from analytics.auth.dependencies import require_scopes

                    dep = require_scopes()  # No scopes required
                    mock_request = MagicMock()
                    result = await dep(request=mock_request, token="valid-token")
                    assert isinstance(result, User)
                    # Token exchange should not have been called
                    mock_tex.validate_token_scopes.assert_not_called()
