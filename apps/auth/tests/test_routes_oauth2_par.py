# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.api.routes.oauth2.par -- Pushed Authorization Request endpoint (RFC 9126)."""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from tests.conftest import make_oauth2_client

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MODULE = "auth.api.routes.oauth2.par"


def _basic_auth(client_id: str, client_secret: str) -> str:
    encoded = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    return f"Basic {encoded}"


# ---------------------------------------------------------------------------
# _parse_basic_auth
# ---------------------------------------------------------------------------


class TestParseBasicAuth:
    def test_none(self):
        from auth.api.routes.oauth2.par import _parse_basic_auth

        assert _parse_basic_auth(None) == (None, None)

    def test_non_basic(self):
        from auth.api.routes.oauth2.par import _parse_basic_auth

        assert _parse_basic_auth("Bearer token") == (None, None)

    def test_valid(self):
        from auth.api.routes.oauth2.par import _parse_basic_auth

        cid, cs = _parse_basic_auth(_basic_auth("c1", "s1"))
        assert cid == "c1"
        assert cs == "s1"

    def test_invalid_encoding(self):
        from auth.api.routes.oauth2.par import _parse_basic_auth

        assert _parse_basic_auth("Basic !!!") == (None, None)


# ---------------------------------------------------------------------------
# _par_error
# ---------------------------------------------------------------------------


class TestParError:
    def test_creates_http_exception(self):
        from auth.api.routes.oauth2.par import _par_error

        exc = _par_error("invalid_request", "Missing param")
        assert isinstance(exc, HTTPException)
        assert exc.status_code == 400
        assert exc.detail["error"] == "invalid_request"
        assert exc.detail["error_description"] == "Missing param"


# ---------------------------------------------------------------------------
# pushed_authorization_request
# ---------------------------------------------------------------------------


class TestPushedAuthorizationRequest:
    @pytest.mark.asyncio
    async def test_no_client_id_raises_400(self):
        from auth.api.routes.oauth2.par import pushed_authorization_request

        with pytest.raises(HTTPException) as exc_info:
            await pushed_authorization_request(
                response_type="code",
                redirect_uri="https://app.example.com/cb",
                db=AsyncMock(),
                oauth2_service=AsyncMock(),
                par_service=AsyncMock(),
                authorization=None,
                client_id=None,
                client_secret=None,
                scope=None,
                state=None,
                code_challenge=None,
                code_challenge_method=None,
                nonce=None,
                prompt=None,
            )
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["error"] == "invalid_request"

    @pytest.mark.asyncio
    async def test_invalid_client_raises_401(self):
        from auth.api.routes.oauth2.par import pushed_authorization_request

        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await pushed_authorization_request(
                response_type="code",
                redirect_uri="https://app.example.com/cb",
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                par_service=AsyncMock(),
                authorization=None,
                client_id="bad",
                client_secret=None,
                scope=None,
                state=None,
                code_challenge=None,
                code_challenge_method=None,
                nonce=None,
                prompt=None,
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_inactive_client_raises_401(self):
        from auth.api.routes.oauth2.par import pushed_authorization_request

        client = make_oauth2_client()
        client.is_active = False
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)

        with pytest.raises(HTTPException) as exc_info:
            await pushed_authorization_request(
                response_type="code",
                redirect_uri="https://app.example.com/cb",
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                par_service=AsyncMock(),
                authorization=None,
                client_id="test_client_id",
                client_secret=None,
                scope=None,
                state=None,
                code_challenge=None,
                code_challenge_method=None,
                nonce=None,
                prompt=None,
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_confidential_client_missing_secret_raises_401(self):
        from auth.api.routes.oauth2.par import pushed_authorization_request

        client = make_oauth2_client(is_confidential=True)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)

        with pytest.raises(HTTPException) as exc_info:
            await pushed_authorization_request(
                response_type="code",
                redirect_uri="https://app.example.com/cb",
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                par_service=AsyncMock(),
                authorization=None,
                client_id="test_client_id",
                client_secret=None,
                scope=None,
                state=None,
                code_challenge=None,
                code_challenge_method=None,
                nonce=None,
                prompt=None,
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_confidential_client_bad_secret_raises_401(self):
        from auth.api.routes.oauth2.par import pushed_authorization_request

        client = make_oauth2_client(is_confidential=True)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.verify_client_secret = MagicMock(return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await pushed_authorization_request(
                response_type="code",
                redirect_uri="https://app.example.com/cb",
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                par_service=AsyncMock(),
                authorization=None,
                client_id="test_client_id",
                client_secret="wrong",
                scope=None,
                state=None,
                code_challenge=None,
                code_challenge_method=None,
                nonce=None,
                prompt=None,
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_unsupported_response_type(self):
        from auth.api.routes.oauth2.par import pushed_authorization_request

        client = make_oauth2_client(is_confidential=False)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)

        with pytest.raises(HTTPException) as exc_info:
            await pushed_authorization_request(
                response_type="token",
                redirect_uri="https://app.example.com/cb",
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                par_service=AsyncMock(),
                authorization=None,
                client_id="test_client_id",
                client_secret=None,
                scope=None,
                state=None,
                code_challenge=None,
                code_challenge_method=None,
                nonce=None,
                prompt=None,
            )
        assert exc_info.value.detail["error"] == "unsupported_response_type"

    @pytest.mark.asyncio
    async def test_redirect_uri_not_registered(self):
        from auth.api.routes.oauth2.par import pushed_authorization_request

        client = make_oauth2_client(is_confidential=False)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_redirect_uri = MagicMock(return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await pushed_authorization_request(
                response_type="code",
                redirect_uri="https://bad.example.com/cb",
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                par_service=AsyncMock(),
                authorization=None,
                client_id="test_client_id",
                client_secret=None,
                scope=None,
                state=None,
                code_challenge=None,
                code_challenge_method=None,
                nonce=None,
                prompt=None,
            )
        assert exc_info.value.detail["error"] == "invalid_request"

    @pytest.mark.asyncio
    async def test_invalid_scopes(self):
        from auth.api.routes.oauth2.par import pushed_authorization_request

        client = make_oauth2_client(is_confidential=False)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_redirect_uri = MagicMock(return_value=True)
        oauth2_svc.validate_scopes = MagicMock(return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await pushed_authorization_request(
                response_type="code",
                redirect_uri="https://app.example.com/callback",
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                par_service=AsyncMock(),
                authorization=None,
                client_id="test_client_id",
                client_secret=None,
                scope="bad_scope",
                state=None,
                code_challenge=None,
                code_challenge_method=None,
                nonce=None,
                prompt=None,
            )
        assert exc_info.value.detail["error"] == "invalid_scope"

    @pytest.mark.asyncio
    async def test_pkce_required_missing_challenge(self):
        from auth.api.routes.oauth2.par import pushed_authorization_request

        client = make_oauth2_client(is_confidential=False, require_pkce=True)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_redirect_uri = MagicMock(return_value=True)
        oauth2_svc.validate_scopes = MagicMock(return_value=True)

        with pytest.raises(HTTPException) as exc_info:
            await pushed_authorization_request(
                response_type="code",
                redirect_uri="https://app.example.com/callback",
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                par_service=AsyncMock(),
                authorization=None,
                client_id="test_client_id",
                client_secret=None,
                scope="openid",
                state=None,
                code_challenge=None,
                code_challenge_method=None,
                nonce=None,
                prompt=None,
            )
        assert exc_info.value.detail["error"] == "invalid_request"
        assert "PKCE" in exc_info.value.detail["error_description"]

    @pytest.mark.asyncio
    @patch(f"{MODULE}.is_valid_code_challenge_method", return_value=False)
    async def test_invalid_code_challenge_method(self, mock_method):
        from auth.api.routes.oauth2.par import pushed_authorization_request

        client = make_oauth2_client(is_confidential=False, require_pkce=False)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_redirect_uri = MagicMock(return_value=True)
        oauth2_svc.validate_scopes = MagicMock(return_value=True)

        with pytest.raises(HTTPException) as exc_info:
            await pushed_authorization_request(
                response_type="code",
                redirect_uri="https://app.example.com/callback",
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                par_service=AsyncMock(),
                authorization=None,
                client_id="test_client_id",
                client_secret=None,
                scope="openid",
                state=None,
                code_challenge="valid_challenge_abc",
                code_challenge_method="plain",
                nonce=None,
                prompt=None,
            )
        assert exc_info.value.detail["error"] == "invalid_request"
        assert "code_challenge_method" in exc_info.value.detail["error_description"]

    @pytest.mark.asyncio
    @patch(f"{MODULE}.is_valid_code_challenge", return_value=False)
    @patch(f"{MODULE}.is_valid_code_challenge_method", return_value=True)
    async def test_invalid_code_challenge_format(self, mock_method, mock_challenge):
        from auth.api.routes.oauth2.par import pushed_authorization_request

        client = make_oauth2_client(is_confidential=False, require_pkce=False)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_redirect_uri = MagicMock(return_value=True)
        oauth2_svc.validate_scopes = MagicMock(return_value=True)

        with pytest.raises(HTTPException) as exc_info:
            await pushed_authorization_request(
                response_type="code",
                redirect_uri="https://app.example.com/callback",
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                par_service=AsyncMock(),
                authorization=None,
                client_id="test_client_id",
                client_secret=None,
                scope="openid",
                state=None,
                code_challenge="bad!!!",
                code_challenge_method="S256",
                nonce=None,
                prompt=None,
            )
        assert exc_info.value.detail["error"] == "invalid_request"
        assert "code_challenge format" in exc_info.value.detail["error_description"]

    @pytest.mark.asyncio
    async def test_success_no_pkce(self):
        from auth.api.routes.oauth2.par import pushed_authorization_request

        client = make_oauth2_client(is_confidential=False, require_pkce=False)
        client.is_active = True
        db = AsyncMock()
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_redirect_uri = MagicMock(return_value=True)
        oauth2_svc.validate_scopes = MagicMock(return_value=True)

        par_svc = AsyncMock()
        par_svc.create_par_request = AsyncMock(
            return_value=("urn:ietf:params:oauth:request_uri:abc", 90)
        )

        result = await pushed_authorization_request(
            response_type="code",
            redirect_uri="https://app.example.com/callback",
            db=db,
            oauth2_service=oauth2_svc,
            par_service=par_svc,
            authorization=None,
            client_id="test_client_id",
            client_secret=None,
            scope="openid",
            state="s1",
            code_challenge=None,
            code_challenge_method=None,
            nonce="n1",
            prompt=None,
        )

        assert result.request_uri == "urn:ietf:params:oauth:request_uri:abc"
        assert result.expires_in == 90
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}.is_valid_code_challenge", return_value=True)
    @patch(f"{MODULE}.is_valid_code_challenge_method", return_value=True)
    async def test_success_with_pkce(self, mock_method, mock_challenge):
        from auth.api.routes.oauth2.par import pushed_authorization_request

        client = make_oauth2_client(is_confidential=True, require_pkce=True)
        client.is_active = True
        db = AsyncMock()
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.verify_client_secret = MagicMock(return_value=True)
        oauth2_svc.validate_redirect_uri = MagicMock(return_value=True)
        oauth2_svc.validate_scopes = MagicMock(return_value=True)

        par_svc = AsyncMock()
        par_svc.create_par_request = AsyncMock(
            return_value=("urn:ietf:params:oauth:request_uri:xyz", 120)
        )

        result = await pushed_authorization_request(
            response_type="code",
            redirect_uri="https://app.example.com/callback",
            db=db,
            oauth2_service=oauth2_svc,
            par_service=par_svc,
            authorization=None,
            client_id="test_client_id",
            client_secret="valid_secret",
            scope="openid profile",
            state="s2",
            code_challenge="dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
            code_challenge_method="S256",
            nonce="n2",
            prompt="consent",
        )

        assert result.request_uri == "urn:ietf:params:oauth:request_uri:xyz"
        assert result.expires_in == 120
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_basic_auth_used_for_credentials(self):
        from auth.api.routes.oauth2.par import pushed_authorization_request

        client = make_oauth2_client(is_confidential=True, require_pkce=False)
        client.is_active = True
        db = AsyncMock()
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.verify_client_secret = MagicMock(return_value=True)
        oauth2_svc.validate_redirect_uri = MagicMock(return_value=True)
        oauth2_svc.validate_scopes = MagicMock(return_value=True)

        par_svc = AsyncMock()
        par_svc.create_par_request = AsyncMock(
            return_value=("urn:ietf:params:oauth:request_uri:auth", 60)
        )

        result = await pushed_authorization_request(
            response_type="code",
            redirect_uri="https://app.example.com/callback",
            db=db,
            oauth2_service=oauth2_svc,
            par_service=par_svc,
            authorization=_basic_auth("test_client_id", "my_secret"),
            client_id=None,
            client_secret=None,
            scope=None,
            state=None,
            code_challenge=None,
            code_challenge_method=None,
            nonce=None,
            prompt=None,
        )

        assert result.request_uri == "urn:ietf:params:oauth:request_uri:auth"
        oauth2_svc.verify_client_secret.assert_called_once_with(client, "my_secret")

    @pytest.mark.asyncio
    async def test_default_scope_openid(self):
        from auth.api.routes.oauth2.par import pushed_authorization_request

        client = make_oauth2_client(is_confidential=False, require_pkce=False)
        client.is_active = True
        db = AsyncMock()
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_redirect_uri = MagicMock(return_value=True)
        oauth2_svc.validate_scopes = MagicMock(return_value=True)

        par_svc = AsyncMock()
        par_svc.create_par_request = AsyncMock(
            return_value=("urn:ietf:params:oauth:request_uri:default", 60)
        )

        await pushed_authorization_request(
            response_type="code",
            redirect_uri="https://app.example.com/callback",
            db=db,
            oauth2_service=oauth2_svc,
            par_service=par_svc,
            authorization=None,
            client_id="test_client_id",
            client_secret=None,
            scope=None,
            state=None,
            code_challenge=None,
            code_challenge_method=None,
            nonce=None,
            prompt=None,
        )

        # Verify scopes default to ["openid"] when no scope is provided
        call_kwargs = par_svc.create_par_request.call_args[1]
        assert call_kwargs["scopes"] == ["openid"]


class TestParPkceMethodDefault:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.is_valid_code_challenge", return_value=True)
    @patch(f"{MODULE}.is_valid_code_challenge_method", return_value=True)
    async def test_missing_method_defaults_to_s256(self, mock_method, mock_challenge):
        from auth.api.routes.oauth2.par import pushed_authorization_request

        client = make_oauth2_client(is_confidential=False, require_pkce=False)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_redirect_uri = MagicMock(return_value=True)
        oauth2_svc.validate_scopes = MagicMock(return_value=True)

        par_svc = AsyncMock()
        par_svc.create_par_request = AsyncMock(
            return_value=("urn:ietf:params:oauth:request_uri:abc", 90)
        )

        await pushed_authorization_request(
            response_type="code",
            redirect_uri="https://app.example.com/callback",
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            par_service=par_svc,
            authorization=None,
            client_id="test_client_id",
            client_secret=None,
            scope="openid",
            state="s1",
            code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            code_challenge_method=None,
            nonce="n1",
            prompt=None,
        )

        mock_method.assert_called_once_with("S256")
