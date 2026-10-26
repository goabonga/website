# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for knowledge/auth/jwt.py — 100% coverage with only mocks."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# We need to patch get_settings BEFORE importing jwt module, or use patch on the module attribute.


class TestJWTValidationError:
    """Test the JWTValidationError exception class."""

    def test_jwt_validation_error_is_exception(self):
        from knowledge.auth.jwt import JWTValidationError

        err = JWTValidationError("test error")
        assert isinstance(err, Exception)
        assert str(err) == "test error"


class TestJWTValidator:
    """Test JWTValidator with all external deps mocked."""

    def _make_validator(self, issuer="https://auth.example.com"):
        """Create a JWTValidator with mocked settings."""
        with patch("knowledge.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = issuer
            mock_settings.oauth2_client_id = "client-id"
            mock_settings.oauth2_client_secret = "client-secret"
            from knowledge.auth.jwt import JWTValidator

            v = JWTValidator()
        return v

    # ------------------------------------------------------------------
    # __init__
    # ------------------------------------------------------------------
    def test_init(self):
        with patch("knowledge.auth.jwt.settings") as mock_settings:
            mock_settings.oauth2_issuer = "https://auth.example.com"
            from knowledge.auth.jwt import JWTValidator

            v = JWTValidator()
        assert v.issuer == "https://auth.example.com"
        assert v._jwks_client is None
        assert v._http_client is None

    # ------------------------------------------------------------------
    # jwks_client property
    # ------------------------------------------------------------------
    def test_jwks_client_creates_once(self):
        v = self._make_validator()
        with patch("knowledge.auth.jwt.PyJWKClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            client1 = v.jwks_client
            client2 = v.jwks_client
        assert client1 is client2
        mock_cls.assert_called_once()

    def test_jwks_client_uri(self):
        v = self._make_validator(issuer="https://auth.example.com")
        with patch("knowledge.auth.jwt.PyJWKClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            _ = v.jwks_client
        mock_cls.assert_called_once_with(
            "https://auth.example.com/.well-known/jwks.json",
            cache_keys=True,
            lifespan=3600,
        )

    # ------------------------------------------------------------------
    # get_http_client
    # ------------------------------------------------------------------
    async def test_get_http_client_creates_new(self):
        v = self._make_validator()
        v._http_client = None
        with patch("knowledge.auth.jwt.httpx.AsyncClient") as mock_ac:
            mock_instance = MagicMock()
            mock_ac.return_value = mock_instance
            client = await v.get_http_client()
        assert client is mock_instance
        mock_ac.assert_called_once_with(timeout=10.0)

    async def test_get_http_client_reuses_open(self):
        v = self._make_validator()
        existing = MagicMock()
        existing.is_closed = False
        v._http_client = existing
        client = await v.get_http_client()
        assert client is existing

    async def test_get_http_client_recreates_closed(self):
        v = self._make_validator()
        closed_client = MagicMock()
        closed_client.is_closed = True
        v._http_client = closed_client
        with patch("knowledge.auth.jwt.httpx.AsyncClient") as mock_ac:
            new_client = MagicMock()
            mock_ac.return_value = new_client
            client = await v.get_http_client()
        assert client is new_client

    # ------------------------------------------------------------------
    # validate_token
    # ------------------------------------------------------------------
    def test_validate_token_no_issuer(self):
        from knowledge.auth.jwt import JWTValidationError

        v = self._make_validator(issuer="")
        with pytest.raises(JWTValidationError, match="OAuth2 issuer not configured"):
            v.validate_token("some-token")

    def test_validate_token_success(self):
        v = self._make_validator()
        mock_signing_key = MagicMock()
        mock_signing_key.key = "the-key"

        mock_jwks = MagicMock()
        mock_jwks.get_signing_key_from_jwt.return_value = mock_signing_key
        v._jwks_client = mock_jwks

        with patch("knowledge.auth.jwt.jwt.decode") as mock_decode:
            mock_decode.return_value = {"sub": "123", "exp": 9999, "iat": 1000}
            result = v.validate_token("my-token")

        assert result == {"sub": "123", "exp": 9999, "iat": 1000}
        mock_decode.assert_called_once_with(
            "my-token",
            "the-key",
            algorithms=["RS256", "ES256"],
            issuer=v.issuer,
            options={
                "verify_aud": False,
                "verify_exp": True,
                "verify_iat": True,
                "verify_iss": True,
                "require": ["sub", "exp", "iat"],
            },
        )

    def test_validate_token_expired(self):
        import jwt as _jwt

        from knowledge.auth.jwt import JWTValidationError

        v = self._make_validator()
        mock_jwks = MagicMock()
        mock_jwks.get_signing_key_from_jwt.return_value = MagicMock(key="k")
        v._jwks_client = mock_jwks

        with patch("knowledge.auth.jwt.jwt.decode", side_effect=_jwt.ExpiredSignatureError):
            with pytest.raises(JWTValidationError, match="Token has expired"):
                v.validate_token("tok")

    def test_validate_token_invalid_issuer(self):
        import jwt as _jwt

        from knowledge.auth.jwt import JWTValidationError

        v = self._make_validator()
        mock_jwks = MagicMock()
        mock_jwks.get_signing_key_from_jwt.return_value = MagicMock(key="k")
        v._jwks_client = mock_jwks

        with patch("knowledge.auth.jwt.jwt.decode", side_effect=_jwt.InvalidIssuerError):
            with pytest.raises(JWTValidationError, match="Invalid token issuer"):
                v.validate_token("tok")

    def test_validate_token_invalid_token(self):
        import jwt as _jwt

        from knowledge.auth.jwt import JWTValidationError

        v = self._make_validator()
        mock_jwks = MagicMock()
        mock_jwks.get_signing_key_from_jwt.return_value = MagicMock(key="k")
        v._jwks_client = mock_jwks

        with (
            patch(
                "knowledge.auth.jwt.jwt.decode",
                side_effect=_jwt.InvalidTokenError("bad format"),
            ),
            pytest.raises(JWTValidationError, match="Invalid token"),
        ):
            v.validate_token("tok")

    def test_validate_token_generic_exception(self):
        from knowledge.auth.jwt import JWTValidationError

        v = self._make_validator()
        mock_jwks = MagicMock()
        mock_jwks.get_signing_key_from_jwt.side_effect = RuntimeError("boom")
        v._jwks_client = mock_jwks

        with pytest.raises(JWTValidationError, match="Token validation failed"):
            v.validate_token("tok")

    # ------------------------------------------------------------------
    # introspect_token
    # ------------------------------------------------------------------
    async def test_introspect_no_issuer(self):
        v = self._make_validator(issuer="")
        result = await v.introspect_token("tok")
        assert result is False

    async def test_introspect_no_client_credentials(self):
        v = self._make_validator()
        with patch("knowledge.auth.jwt.settings") as mock_s:
            mock_s.oauth2_client_id = ""
            mock_s.oauth2_client_secret = ""
            result = await v.introspect_token("tok")
        assert result is True

    async def test_introspect_no_client_id_only(self):
        v = self._make_validator()
        with patch("knowledge.auth.jwt.settings") as mock_s:
            mock_s.oauth2_client_id = "id"
            mock_s.oauth2_client_secret = ""
            result = await v.introspect_token("tok")
        assert result is True

    async def test_introspect_active(self):
        v = self._make_validator()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"active": True}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        v._http_client = mock_client
        mock_client.is_closed = False

        with patch("knowledge.auth.jwt.settings") as mock_s:
            mock_s.oauth2_client_id = "cid"
            mock_s.oauth2_client_secret = "csecret"
            mock_s.oauth2_issuer = v.issuer
            result = await v.introspect_token("tok")
        assert result is True

    async def test_introspect_inactive(self):
        v = self._make_validator()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"active": False}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        v._http_client = mock_client
        mock_client.is_closed = False

        with patch("knowledge.auth.jwt.settings") as mock_s:
            mock_s.oauth2_client_id = "cid"
            mock_s.oauth2_client_secret = "csecret"
            result = await v.introspect_token("tok")
        assert result is False

    async def test_introspect_non_200(self):
        v = self._make_validator()
        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        v._http_client = mock_client
        mock_client.is_closed = False

        with patch("knowledge.auth.jwt.settings") as mock_s:
            mock_s.oauth2_client_id = "cid"
            mock_s.oauth2_client_secret = "csecret"
            result = await v.introspect_token("tok")
        assert result is True

    async def test_introspect_exception(self):
        v = self._make_validator()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=RuntimeError("network"))
        v._http_client = mock_client
        mock_client.is_closed = False

        with patch("knowledge.auth.jwt.settings") as mock_s:
            mock_s.oauth2_client_id = "cid"
            mock_s.oauth2_client_secret = "csecret"
            result = await v.introspect_token("tok")
        assert result is True

    # ------------------------------------------------------------------
    # fetch_userinfo
    # ------------------------------------------------------------------
    async def test_fetch_userinfo_no_issuer(self):
        v = self._make_validator(issuer="")
        result = await v.fetch_userinfo("tok")
        assert result == {}

    async def test_fetch_userinfo_success(self):
        v = self._make_validator()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"name": "John", "email": "john@example.com"}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        v._http_client = mock_client
        mock_client.is_closed = False

        result = await v.fetch_userinfo("tok")
        assert result == {"name": "John", "email": "john@example.com"}

    async def test_fetch_userinfo_non_200(self):
        v = self._make_validator()
        mock_response = MagicMock()
        mock_response.status_code = 401

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        v._http_client = mock_client
        mock_client.is_closed = False

        result = await v.fetch_userinfo("tok")
        assert result == {}

    async def test_fetch_userinfo_exception(self):
        v = self._make_validator()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=RuntimeError("fail"))
        v._http_client = mock_client
        mock_client.is_closed = False

        result = await v.fetch_userinfo("tok")
        assert result == {}

    # ------------------------------------------------------------------
    # validate_token_with_introspection
    # ------------------------------------------------------------------
    async def test_validate_with_introspection_basic(self):
        v = self._make_validator()
        v.validate_token = MagicMock(return_value={"sub": "123"})
        v.introspect_token = AsyncMock(return_value=True)

        result = await v.validate_token_with_introspection("tok")
        assert result == {"sub": "123"}
        v.introspect_token.assert_awaited_once_with("tok")

    async def test_validate_with_introspection_revoked(self):
        from knowledge.auth.jwt import JWTValidationError

        v = self._make_validator()
        v.validate_token = MagicMock(return_value={"sub": "123"})
        v.introspect_token = AsyncMock(return_value=False)

        with pytest.raises(JWTValidationError, match="Token has been revoked"):
            await v.validate_token_with_introspection("tok")

    async def test_validate_with_introspection_skip_revocation(self):
        v = self._make_validator()
        v.validate_token = MagicMock(return_value={"sub": "123"})
        v.introspect_token = AsyncMock()

        result = await v.validate_token_with_introspection("tok", check_revocation=False)
        assert result == {"sub": "123"}
        v.introspect_token.assert_not_awaited()

    async def test_validate_with_introspection_fetch_userinfo(self):
        v = self._make_validator()
        v.validate_token = MagicMock(return_value={"sub": "123"})
        v.introspect_token = AsyncMock(return_value=True)
        v.fetch_userinfo = AsyncMock(return_value={"email": "u@e.com"})

        result = await v.validate_token_with_introspection(
            "tok", check_revocation=True, fetch_userinfo=True
        )
        assert result == {"sub": "123", "email": "u@e.com"}
        v.fetch_userinfo.assert_awaited_once_with("tok")

    async def test_validate_with_introspection_no_fetch_userinfo(self):
        v = self._make_validator()
        v.validate_token = MagicMock(return_value={"sub": "123"})
        v.introspect_token = AsyncMock(return_value=True)
        v.fetch_userinfo = AsyncMock()

        result = await v.validate_token_with_introspection(
            "tok", check_revocation=True, fetch_userinfo=False
        )
        assert result == {"sub": "123"}
        v.fetch_userinfo.assert_not_awaited()

    # ------------------------------------------------------------------
    # close
    # ------------------------------------------------------------------
    async def test_close_open_client(self):
        v = self._make_validator()
        mock_client = AsyncMock()
        mock_client.is_closed = False
        v._http_client = mock_client

        await v.close()
        mock_client.aclose.assert_awaited_once()

    async def test_close_already_closed(self):
        v = self._make_validator()
        mock_client = AsyncMock()
        mock_client.is_closed = True
        v._http_client = mock_client

        await v.close()
        mock_client.aclose.assert_not_awaited()

    async def test_close_no_client(self):
        v = self._make_validator()
        v._http_client = None
        # Should not raise
        await v.close()


class TestGetJWTValidator:
    """Test the singleton factory."""

    def test_get_jwt_validator_creates_singleton(self):
        import knowledge.auth.jwt as jwt_mod

        jwt_mod._jwt_validator = None
        with patch("knowledge.auth.jwt.settings") as mock_s:
            mock_s.oauth2_issuer = "https://auth.example.com"
            v1 = jwt_mod.get_jwt_validator()
            v2 = jwt_mod.get_jwt_validator()
        assert v1 is v2
        # Cleanup
        jwt_mod._jwt_validator = None

    def test_get_jwt_validator_returns_existing(self):
        import knowledge.auth.jwt as jwt_mod

        sentinel = MagicMock()
        jwt_mod._jwt_validator = sentinel
        assert jwt_mod.get_jwt_validator() is sentinel
        # Cleanup
        jwt_mod._jwt_validator = None
