# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.api.routes.oauth2.token -- OAuth2 token endpoint."""

import base64
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from tests.conftest import (
    make_authorization_code,
    make_device_code,
    make_oauth2_client,
    make_refresh_token,
    make_user,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MODULE = "auth.api.routes.oauth2.token"


@pytest.fixture(autouse=True)
def _patch_webhook_dispatch():
    """Prevent webhook dispatch from running the SQLAlchemy path against AsyncMock sessions."""
    with patch(f"{MODULE}.dispatch_webhook_event", new_callable=AsyncMock):
        yield


def _basic_auth(client_id: str, client_secret: str) -> str:
    encoded = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    return f"Basic {encoded}"


# ---------------------------------------------------------------------------
# _parse_basic_auth
# ---------------------------------------------------------------------------


class TestParseBasicAuth:
    def test_none(self):
        from auth.api.routes.oauth2.token import _parse_basic_auth

        assert _parse_basic_auth(None) == (None, None)

    def test_non_basic(self):
        from auth.api.routes.oauth2.token import _parse_basic_auth

        assert _parse_basic_auth("Bearer xyz") == (None, None)

    def test_valid(self):
        from auth.api.routes.oauth2.token import _parse_basic_auth

        cid, cs = _parse_basic_auth(_basic_auth("c1", "s1"))
        assert cid == "c1"
        assert cs == "s1"

    def test_invalid_encoding(self):
        from auth.api.routes.oauth2.token import _parse_basic_auth

        assert _parse_basic_auth("Basic !!!invalid") == (None, None)


# ---------------------------------------------------------------------------
# _token_error
# ---------------------------------------------------------------------------


class TestTokenError:
    def test_creates_http_exception(self):
        from auth.api.routes.oauth2.token import _token_error

        exc = _token_error("invalid_request", "Missing code")
        assert isinstance(exc, HTTPException)
        assert exc.status_code == 400
        assert exc.detail["error"] == "invalid_request"
        assert exc.detail["error_description"] == "Missing code"


# ---------------------------------------------------------------------------
# token_endpoint - Client authentication
# ---------------------------------------------------------------------------


class TestTokenEndpointAuth:
    @pytest.mark.asyncio
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    async def test_no_client_id_raises_400(self, mock_issuer):
        from auth.api.routes.oauth2.token import token_endpoint

        with pytest.raises(HTTPException) as exc_info:
            await token_endpoint(
                grant_type="authorization_code",
                db=AsyncMock(),
                oauth2_service=AsyncMock(),
                token_service=AsyncMock(),
                device_service=AsyncMock(),
                token_exchange_service=AsyncMock(),
                auth_service=AsyncMock(),
                authorization=None,
                client_id=None,
                client_secret=None,
                code=None,
                redirect_uri=None,
                code_verifier=None,
                refresh_token=None,
                scope=None,
                device_code=None,
                username=None,
                password=None,
                subject_token=None,
                subject_token_type=None,
                actor_token=None,
                actor_token_type=None,
                requested_token_type=None,
                audience=None,
                resource=None,
            )
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["error"] == "invalid_request"

    @pytest.mark.asyncio
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    async def test_unknown_client_raises_401(self, mock_issuer):
        from auth.api.routes.oauth2.token import token_endpoint

        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await token_endpoint(
                grant_type="authorization_code",
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                token_service=AsyncMock(),
                device_service=AsyncMock(),
                token_exchange_service=AsyncMock(),
                auth_service=AsyncMock(),
                authorization=None,
                client_id="bad",
                client_secret=None,
                code=None,
                redirect_uri=None,
                code_verifier=None,
                refresh_token=None,
                scope=None,
                device_code=None,
                username=None,
                password=None,
                subject_token=None,
                subject_token_type=None,
                actor_token=None,
                actor_token_type=None,
                requested_token_type=None,
                audience=None,
                resource=None,
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    async def test_confidential_missing_secret_raises_401(self, mock_issuer):
        from auth.api.routes.oauth2.token import token_endpoint

        client = make_oauth2_client(is_confidential=True)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)

        with pytest.raises(HTTPException) as exc_info:
            await token_endpoint(
                grant_type="authorization_code",
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                token_service=AsyncMock(),
                device_service=AsyncMock(),
                token_exchange_service=AsyncMock(),
                auth_service=AsyncMock(),
                authorization=None,
                client_id="test_client_id",
                client_secret=None,
                code=None,
                redirect_uri=None,
                code_verifier=None,
                refresh_token=None,
                scope=None,
                device_code=None,
                username=None,
                password=None,
                subject_token=None,
                subject_token_type=None,
                actor_token=None,
                actor_token_type=None,
                requested_token_type=None,
                audience=None,
                resource=None,
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    async def test_confidential_wrong_secret_raises_401(self, mock_issuer):
        from auth.api.routes.oauth2.token import token_endpoint

        client = make_oauth2_client(is_confidential=True)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.verify_client_secret = MagicMock(return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await token_endpoint(
                grant_type="authorization_code",
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                token_service=AsyncMock(),
                device_service=AsyncMock(),
                token_exchange_service=AsyncMock(),
                auth_service=AsyncMock(),
                authorization=None,
                client_id="test_client_id",
                client_secret="wrong",
                code=None,
                redirect_uri=None,
                code_verifier=None,
                refresh_token=None,
                scope=None,
                device_code=None,
                username=None,
                password=None,
                subject_token=None,
                subject_token_type=None,
                actor_token=None,
                actor_token_type=None,
                requested_token_type=None,
                audience=None,
                resource=None,
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    async def test_unauthorized_grant_type_raises_400(self, mock_issuer):
        from auth.api.routes.oauth2.token import token_endpoint

        client = make_oauth2_client(is_confidential=False)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_grant_type = MagicMock(return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await token_endpoint(
                grant_type="client_credentials",
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                token_service=AsyncMock(),
                device_service=AsyncMock(),
                token_exchange_service=AsyncMock(),
                auth_service=AsyncMock(),
                authorization=None,
                client_id="test_client_id",
                client_secret=None,
                code=None,
                redirect_uri=None,
                code_verifier=None,
                refresh_token=None,
                scope=None,
                device_code=None,
                username=None,
                password=None,
                subject_token=None,
                subject_token_type=None,
                actor_token=None,
                actor_token_type=None,
                requested_token_type=None,
                audience=None,
                resource=None,
            )
        assert exc_info.value.detail["error"] == "unauthorized_client"

    @pytest.mark.asyncio
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    async def test_unsupported_grant_type_raises_400(self, mock_issuer):
        from auth.api.routes.oauth2.token import token_endpoint

        client = make_oauth2_client(is_confidential=False)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_grant_type = MagicMock(return_value=True)

        with pytest.raises(HTTPException) as exc_info:
            await token_endpoint(
                grant_type="unsupported_type",
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                token_service=AsyncMock(),
                device_service=AsyncMock(),
                token_exchange_service=AsyncMock(),
                auth_service=AsyncMock(),
                authorization=None,
                client_id="test_client_id",
                client_secret=None,
                code=None,
                redirect_uri=None,
                code_verifier=None,
                refresh_token=None,
                scope=None,
                device_code=None,
                username=None,
                password=None,
                subject_token=None,
                subject_token_type=None,
                actor_token=None,
                actor_token_type=None,
                requested_token_type=None,
                audience=None,
                resource=None,
            )
        assert exc_info.value.detail["error"] == "unsupported_grant_type"


# ---------------------------------------------------------------------------
# _handle_authorization_code
# ---------------------------------------------------------------------------


class TestHandleAuthorizationCode:
    @pytest.mark.asyncio
    async def test_missing_code_raises(self):
        from auth.api.routes.oauth2.token import _handle_authorization_code

        with pytest.raises(HTTPException) as exc_info:
            await _handle_authorization_code(
                db=AsyncMock(),
                oauth2_service=AsyncMock(),
                token_service=AsyncMock(),
                client=MagicMock(),
                code=None,
                redirect_uri="https://app.example.com/cb",
                code_verifier=None,
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "invalid_request"

    @pytest.mark.asyncio
    async def test_missing_redirect_uri_raises(self):
        from auth.api.routes.oauth2.token import _handle_authorization_code

        with pytest.raises(HTTPException) as exc_info:
            await _handle_authorization_code(
                db=AsyncMock(),
                oauth2_service=AsyncMock(),
                token_service=AsyncMock(),
                client=MagicMock(),
                code="abc",
                redirect_uri=None,
                code_verifier=None,
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "invalid_request"

    @pytest.mark.asyncio
    async def test_invalid_code_raises(self):
        from auth.api.routes.oauth2.token import _handle_authorization_code

        oauth2_svc = AsyncMock()
        oauth2_svc.get_authorization_code = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await _handle_authorization_code(
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                token_service=AsyncMock(),
                client=MagicMock(),
                code="bad_code",
                redirect_uri="https://app.example.com/cb",
                code_verifier=None,
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "invalid_grant"

    @pytest.mark.asyncio
    async def test_client_mismatch_raises(self):
        from auth.api.routes.oauth2.token import _handle_authorization_code

        client = make_oauth2_client()
        auth_code = make_authorization_code(client_id=uuid.uuid4())  # Different client
        oauth2_svc = AsyncMock()
        oauth2_svc.get_authorization_code = AsyncMock(return_value=auth_code)

        with pytest.raises(HTTPException) as exc_info:
            await _handle_authorization_code(
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                token_service=AsyncMock(),
                client=client,
                code="valid_code",
                redirect_uri="https://app.example.com/callback",
                code_verifier=None,
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "invalid_grant"

    @pytest.mark.asyncio
    async def test_redirect_uri_mismatch_raises(self):
        from auth.api.routes.oauth2.token import _handle_authorization_code

        client = make_oauth2_client()
        auth_code = make_authorization_code(
            client_id=client.id,
            redirect_uri="https://app.example.com/original",
        )
        oauth2_svc = AsyncMock()
        oauth2_svc.get_authorization_code = AsyncMock(return_value=auth_code)

        with pytest.raises(HTTPException) as exc_info:
            await _handle_authorization_code(
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                token_service=AsyncMock(),
                client=client,
                code="valid_code",
                redirect_uri="https://app.example.com/different",
                code_verifier=None,
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "invalid_grant"

    @pytest.mark.asyncio
    async def test_pkce_required_but_no_verifier(self):
        from auth.api.routes.oauth2.token import _handle_authorization_code

        client = make_oauth2_client()
        auth_code = make_authorization_code(
            client_id=client.id,
            redirect_uri="https://app.example.com/callback",
            code_challenge="challenge_value",
            code_challenge_method="S256",
        )
        oauth2_svc = AsyncMock()
        oauth2_svc.get_authorization_code = AsyncMock(return_value=auth_code)

        with pytest.raises(HTTPException) as exc_info:
            await _handle_authorization_code(
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                token_service=AsyncMock(),
                client=client,
                code="valid_code",
                redirect_uri="https://app.example.com/callback",
                code_verifier=None,
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "invalid_request"

    @pytest.mark.asyncio
    @patch(f"{MODULE}.is_valid_code_verifier", return_value=False)
    async def test_invalid_verifier_format(self, mock_verifier):
        from auth.api.routes.oauth2.token import _handle_authorization_code

        client = make_oauth2_client()
        auth_code = make_authorization_code(
            client_id=client.id,
            redirect_uri="https://app.example.com/callback",
            code_challenge="challenge_value",
        )
        oauth2_svc = AsyncMock()
        oauth2_svc.get_authorization_code = AsyncMock(return_value=auth_code)

        with pytest.raises(HTTPException) as exc_info:
            await _handle_authorization_code(
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                token_service=AsyncMock(),
                client=client,
                code="valid_code",
                redirect_uri="https://app.example.com/callback",
                code_verifier="bad!!!",
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "invalid_request"

    @pytest.mark.asyncio
    @patch(f"{MODULE}.verify_code_challenge", return_value=False)
    @patch(f"{MODULE}.is_valid_code_verifier", return_value=True)
    async def test_pkce_verification_failed(self, mock_valid, mock_verify):
        from auth.api.routes.oauth2.token import _handle_authorization_code

        client = make_oauth2_client()
        auth_code = make_authorization_code(
            client_id=client.id,
            redirect_uri="https://app.example.com/callback",
            code_challenge="challenge_value",
            code_challenge_method="S256",
        )
        oauth2_svc = AsyncMock()
        oauth2_svc.get_authorization_code = AsyncMock(return_value=auth_code)

        with pytest.raises(HTTPException) as exc_info:
            await _handle_authorization_code(
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                token_service=AsyncMock(),
                client=client,
                code="valid_code",
                redirect_uri="https://app.example.com/callback",
                code_verifier="wrong_verifier",
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "invalid_grant"

    @pytest.mark.asyncio
    async def test_success_without_pkce(self):
        from auth.api.routes.oauth2.token import _handle_authorization_code

        client = make_oauth2_client()
        auth_code = make_authorization_code(
            client_id=client.id,
            redirect_uri="https://app.example.com/callback",
            scopes=["openid", "profile"],
            user_id="user-1",
            nonce="n1",
        )
        auth_code.code_challenge = None
        db = AsyncMock()
        oauth2_svc = AsyncMock()
        oauth2_svc.get_authorization_code = AsyncMock(return_value=auth_code)
        oauth2_svc.consume_authorization_code = AsyncMock()

        token_svc = AsyncMock()
        token_svc.create_token_pair = AsyncMock(return_value=("at_123", "rt_456", 3600))
        token_svc.create_id_token = AsyncMock(return_value="id_token_789")

        result = await _handle_authorization_code(
            db=db,
            oauth2_service=oauth2_svc,
            token_service=token_svc,
            client=client,
            code="valid_code",
            redirect_uri="https://app.example.com/callback",
            code_verifier=None,
            issuer="https://auth.example.com",
        )

        assert result.access_token == "at_123"
        assert result.refresh_token == "rt_456"
        assert result.expires_in == 3600
        assert result.id_token == "id_token_789"
        assert result.scope == "openid profile"
        oauth2_svc.consume_authorization_code.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_success_no_openid_scope_no_id_token(self):
        from auth.api.routes.oauth2.token import _handle_authorization_code

        client = make_oauth2_client()
        auth_code = make_authorization_code(
            client_id=client.id,
            redirect_uri="https://app.example.com/callback",
            scopes=["profile"],
            user_id="user-1",
        )
        auth_code.code_challenge = None
        db = AsyncMock()
        oauth2_svc = AsyncMock()
        oauth2_svc.get_authorization_code = AsyncMock(return_value=auth_code)
        oauth2_svc.consume_authorization_code = AsyncMock()

        token_svc = AsyncMock()
        token_svc.create_token_pair = AsyncMock(return_value=("at_123", "rt_456", 3600))

        result = await _handle_authorization_code(
            db=db,
            oauth2_service=oauth2_svc,
            token_service=token_svc,
            client=client,
            code="valid_code",
            redirect_uri="https://app.example.com/callback",
            code_verifier=None,
            issuer="https://auth.example.com",
        )

        assert result.id_token is None
        token_svc.create_id_token.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_token_creation_error(self):
        from auth.api.routes.oauth2.token import _handle_authorization_code

        client = make_oauth2_client()
        auth_code = make_authorization_code(
            client_id=client.id,
            redirect_uri="https://app.example.com/callback",
        )
        auth_code.code_challenge = None
        oauth2_svc = AsyncMock()
        oauth2_svc.get_authorization_code = AsyncMock(return_value=auth_code)
        oauth2_svc.consume_authorization_code = AsyncMock()

        token_svc = AsyncMock()
        token_svc.create_token_pair = AsyncMock(side_effect=ValueError("No signing key"))

        with pytest.raises(HTTPException) as exc_info:
            await _handle_authorization_code(
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                token_service=token_svc,
                client=client,
                code="valid_code",
                redirect_uri="https://app.example.com/callback",
                code_verifier=None,
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "server_error"


# ---------------------------------------------------------------------------
# _handle_refresh_token
# ---------------------------------------------------------------------------


class TestHandleRefreshToken:
    @pytest.mark.asyncio
    async def test_missing_refresh_token_raises(self):
        from auth.api.routes.oauth2.token import _handle_refresh_token

        with pytest.raises(HTTPException) as exc_info:
            await _handle_refresh_token(
                db=AsyncMock(),
                token_service=AsyncMock(),
                client=MagicMock(),
                refresh_token=None,
                scope=None,
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "invalid_request"

    @pytest.mark.asyncio
    async def test_invalid_refresh_token_raises(self):
        from auth.api.routes.oauth2.token import _handle_refresh_token

        token_svc = AsyncMock()
        token_svc.get_refresh_token = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await _handle_refresh_token(
                db=AsyncMock(),
                token_service=token_svc,
                client=MagicMock(),
                refresh_token="bad_rt",
                scope=None,
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "invalid_grant"

    @pytest.mark.asyncio
    async def test_client_mismatch_raises(self):
        from auth.api.routes.oauth2.token import _handle_refresh_token

        client = make_oauth2_client()
        rt = make_refresh_token(client_id=uuid.uuid4())  # Different client
        token_svc = AsyncMock()
        token_svc.get_refresh_token = AsyncMock(return_value=rt)

        with pytest.raises(HTTPException) as exc_info:
            await _handle_refresh_token(
                db=AsyncMock(),
                token_service=token_svc,
                client=client,
                refresh_token="valid_rt",
                scope=None,
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "invalid_grant"

    @pytest.mark.asyncio
    async def test_success(self):
        from auth.api.routes.oauth2.token import _handle_refresh_token

        client = make_oauth2_client()
        rt = make_refresh_token(client_id=client.id, scopes=["openid", "profile"])
        token_svc = AsyncMock()
        token_svc.get_refresh_token = AsyncMock(return_value=rt)
        token_svc.refresh_tokens = AsyncMock(return_value=("new_at", "new_rt", 3600))

        result = await _handle_refresh_token(
            db=AsyncMock(),
            token_service=token_svc,
            client=client,
            refresh_token="valid_rt",
            scope=None,
            issuer="https://auth.example.com",
        )

        assert result.access_token == "new_at"
        assert result.refresh_token == "new_rt"
        assert result.expires_in == 3600
        assert result.scope == "openid profile"

    @pytest.mark.asyncio
    async def test_success_with_scope_downgrade(self):
        from auth.api.routes.oauth2.token import _handle_refresh_token

        client = make_oauth2_client()
        rt = make_refresh_token(client_id=client.id, scopes=["openid", "profile", "email"])
        token_svc = AsyncMock()
        token_svc.get_refresh_token = AsyncMock(return_value=rt)
        token_svc.refresh_tokens = AsyncMock(return_value=("new_at", "new_rt", 3600))

        result = await _handle_refresh_token(
            db=AsyncMock(),
            token_service=token_svc,
            client=client,
            refresh_token="valid_rt",
            scope="openid",
            issuer="https://auth.example.com",
        )

        assert result.scope == "openid"

    @pytest.mark.asyncio
    async def test_refresh_error_raises(self):
        from auth.api.routes.oauth2.token import _handle_refresh_token

        client = make_oauth2_client()
        rt = make_refresh_token(client_id=client.id)
        token_svc = AsyncMock()
        token_svc.get_refresh_token = AsyncMock(return_value=rt)
        token_svc.refresh_tokens = AsyncMock(side_effect=ValueError("Scope error"))

        with pytest.raises(HTTPException) as exc_info:
            await _handle_refresh_token(
                db=AsyncMock(),
                token_service=token_svc,
                client=client,
                refresh_token="valid_rt",
                scope="bad_scope",
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "invalid_scope"


# ---------------------------------------------------------------------------
# _handle_client_credentials
# ---------------------------------------------------------------------------


class TestHandleClientCredentials:
    @pytest.mark.asyncio
    async def test_non_confidential_client_raises(self):
        from auth.api.routes.oauth2.token import _handle_client_credentials

        client = make_oauth2_client(is_confidential=False)

        with pytest.raises(HTTPException) as exc_info:
            await _handle_client_credentials(
                db=AsyncMock(),
                oauth2_service=AsyncMock(),
                token_service=AsyncMock(),
                client=client,
                scope=None,
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "unauthorized_client"

    @pytest.mark.asyncio
    async def test_invalid_scopes_raises(self):
        from auth.api.routes.oauth2.token import _handle_client_credentials

        client = make_oauth2_client(is_confidential=True)
        oauth2_svc = AsyncMock()
        oauth2_svc.validate_scopes = MagicMock(return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await _handle_client_credentials(
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                token_service=AsyncMock(),
                client=client,
                scope="bad_scope",
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "invalid_scope"

    @pytest.mark.asyncio
    async def test_success(self):
        from auth.api.routes.oauth2.token import _handle_client_credentials

        client = make_oauth2_client(is_confidential=True, allowed_scopes=["openid", "api"])
        oauth2_svc = AsyncMock()
        oauth2_svc.validate_scopes = MagicMock(return_value=True)
        token_svc = AsyncMock()
        token_svc.create_token_pair = AsyncMock(return_value=("cc_at", None, 3600))

        result = await _handle_client_credentials(
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            token_service=token_svc,
            client=client,
            scope="openid",
            issuer="https://auth.example.com",
        )

        assert result.access_token == "cc_at"
        assert result.refresh_token is None
        assert result.expires_in == 3600

    @pytest.mark.asyncio
    async def test_success_default_scopes(self):
        from auth.api.routes.oauth2.token import _handle_client_credentials

        client = make_oauth2_client(is_confidential=True, allowed_scopes=["openid", "api"])
        oauth2_svc = AsyncMock()
        oauth2_svc.validate_scopes = MagicMock(return_value=True)
        token_svc = AsyncMock()
        token_svc.create_token_pair = AsyncMock(return_value=("cc_at", None, 3600))

        result = await _handle_client_credentials(
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            token_service=token_svc,
            client=client,
            scope=None,
            issuer="https://auth.example.com",
        )

        assert result.scope == "openid api"

    @pytest.mark.asyncio
    async def test_token_creation_error(self):
        from auth.api.routes.oauth2.token import _handle_client_credentials

        client = make_oauth2_client(is_confidential=True)
        oauth2_svc = AsyncMock()
        oauth2_svc.validate_scopes = MagicMock(return_value=True)
        token_svc = AsyncMock()
        token_svc.create_token_pair = AsyncMock(side_effect=ValueError("Key error"))

        with pytest.raises(HTTPException) as exc_info:
            await _handle_client_credentials(
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                token_service=token_svc,
                client=client,
                scope=None,
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "server_error"


# ---------------------------------------------------------------------------
# _handle_password
# ---------------------------------------------------------------------------


class TestHandlePassword:
    @pytest.mark.asyncio
    async def test_missing_username_raises(self):
        from auth.api.routes.oauth2.token import _handle_password

        with pytest.raises(HTTPException) as exc_info:
            await _handle_password(
                db=AsyncMock(),
                oauth2_service=AsyncMock(),
                auth_service=AsyncMock(),
                token_service=AsyncMock(),
                client=MagicMock(),
                username=None,
                password="pw",
                scope=None,
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "invalid_request"

    @pytest.mark.asyncio
    async def test_missing_password_raises(self):
        from auth.api.routes.oauth2.token import _handle_password

        with pytest.raises(HTTPException) as exc_info:
            await _handle_password(
                db=AsyncMock(),
                oauth2_service=AsyncMock(),
                auth_service=AsyncMock(),
                token_service=AsyncMock(),
                client=MagicMock(),
                username="user@example.com",
                password=None,
                scope=None,
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "invalid_request"

    @pytest.mark.asyncio
    async def test_authentication_failed_raises(self):
        from auth.api.routes.oauth2.token import _handle_password

        auth_svc = AsyncMock()
        auth_svc.authenticate = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await _handle_password(
                db=AsyncMock(),
                oauth2_service=AsyncMock(),
                auth_service=auth_svc,
                token_service=AsyncMock(),
                client=MagicMock(),
                username="user@example.com",
                password="wrong_pw",
                scope=None,
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "invalid_grant"

    @pytest.mark.asyncio
    async def test_mfa_required_without_otp_raises(self):
        from auth.api.routes.oauth2.token import _handle_password

        user = make_user()
        client = make_oauth2_client(allowed_scopes=["openid", "profile"])
        auth_svc = AsyncMock()
        auth_svc.authenticate = AsyncMock(return_value=user)
        oauth2_svc = AsyncMock()
        oauth2_svc.validate_scopes = MagicMock(return_value=True)
        mfa_svc = AsyncMock()
        mfa_svc.get_user_mfa = AsyncMock(return_value=MagicMock(totp_enabled=True))

        with pytest.raises(HTTPException) as exc_info:
            await _handle_password(
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                auth_service=auth_svc,
                token_service=AsyncMock(),
                client=client,
                username="user@example.com",
                password="correct_pw",
                scope="openid",
                issuer="https://auth.example.com",
                otp=None,
                mfa_service=mfa_svc,
            )
        assert exc_info.value.detail["error"] == "invalid_grant"
        assert exc_info.value.detail["error_description"] == "mfa_required"

    @pytest.mark.asyncio
    async def test_mfa_invalid_otp_raises(self):
        from auth.api.routes.oauth2.token import _handle_password

        user = make_user()
        client = make_oauth2_client(allowed_scopes=["openid", "profile"])
        auth_svc = AsyncMock()
        auth_svc.authenticate = AsyncMock(return_value=user)
        oauth2_svc = AsyncMock()
        oauth2_svc.validate_scopes = MagicMock(return_value=True)
        mfa_svc = AsyncMock()
        mfa_svc.get_user_mfa = AsyncMock(return_value=MagicMock(totp_enabled=True))
        mfa_svc.verify_mfa_code_with_email = AsyncMock(return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await _handle_password(
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                auth_service=auth_svc,
                token_service=AsyncMock(),
                client=client,
                username="user@example.com",
                password="correct_pw",
                scope="openid",
                issuer="https://auth.example.com",
                otp="123456",
                mfa_service=mfa_svc,
            )
        assert exc_info.value.detail["error"] == "invalid_grant"
        assert exc_info.value.detail["error_description"] == "invalid_otp"

    @pytest.mark.asyncio
    async def test_success_with_mfa_otp(self):
        from auth.api.routes.oauth2.token import _handle_password

        user = make_user()
        client = make_oauth2_client(allowed_scopes=["openid", "profile"])
        auth_svc = AsyncMock()
        auth_svc.authenticate = AsyncMock(return_value=user)
        oauth2_svc = AsyncMock()
        oauth2_svc.validate_scopes = MagicMock(return_value=True)
        token_svc = AsyncMock()
        token_svc.create_token_pair = AsyncMock(return_value=("pw_at", "pw_rt", 3600))
        token_svc.create_id_token = AsyncMock(return_value="pw_id_token")
        mfa_svc = AsyncMock()
        mfa_svc.get_user_mfa = AsyncMock(return_value=MagicMock(totp_enabled=True))
        mfa_svc.verify_mfa_code_with_email = AsyncMock(return_value=True)

        result = await _handle_password(
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            auth_service=auth_svc,
            token_service=token_svc,
            client=client,
            username="user@example.com",
            password="correct_pw",
            scope="openid",
            issuer="https://auth.example.com",
            otp="123456",
            mfa_service=mfa_svc,
        )

        assert result.access_token == "pw_at"
        assert result.refresh_token == "pw_rt"
        assert result.id_token == "pw_id_token"

    @pytest.mark.asyncio
    async def test_invalid_scopes_raises(self):
        from auth.api.routes.oauth2.token import _handle_password

        user = make_user()
        auth_svc = AsyncMock()
        auth_svc.authenticate = AsyncMock(return_value=user)
        oauth2_svc = AsyncMock()
        oauth2_svc.validate_scopes = MagicMock(return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await _handle_password(
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                auth_service=auth_svc,
                token_service=AsyncMock(),
                client=make_oauth2_client(),
                username="user@example.com",
                password="correct_pw",
                scope="bad_scope",
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "invalid_scope"

    @pytest.mark.asyncio
    async def test_success_with_id_token(self):
        from auth.api.routes.oauth2.token import _handle_password

        user = make_user()
        client = make_oauth2_client(allowed_scopes=["openid", "profile"])
        auth_svc = AsyncMock()
        auth_svc.authenticate = AsyncMock(return_value=user)
        oauth2_svc = AsyncMock()
        oauth2_svc.validate_scopes = MagicMock(return_value=True)
        token_svc = AsyncMock()
        token_svc.create_token_pair = AsyncMock(return_value=("pw_at", "pw_rt", 3600))
        token_svc.create_id_token = AsyncMock(return_value="pw_id_token")

        result = await _handle_password(
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            auth_service=auth_svc,
            token_service=token_svc,
            client=client,
            username="user@example.com",
            password="correct_pw",
            scope="openid",
            issuer="https://auth.example.com",
        )

        assert result.access_token == "pw_at"
        assert result.refresh_token == "pw_rt"
        assert result.id_token == "pw_id_token"

    @pytest.mark.asyncio
    async def test_success_no_openid_no_id_token(self):
        from auth.api.routes.oauth2.token import _handle_password

        user = make_user()
        client = make_oauth2_client(allowed_scopes=["profile"])
        auth_svc = AsyncMock()
        auth_svc.authenticate = AsyncMock(return_value=user)
        oauth2_svc = AsyncMock()
        oauth2_svc.validate_scopes = MagicMock(return_value=True)
        token_svc = AsyncMock()
        token_svc.create_token_pair = AsyncMock(return_value=("pw_at", "pw_rt", 3600))

        result = await _handle_password(
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            auth_service=auth_svc,
            token_service=token_svc,
            client=client,
            username="user@example.com",
            password="correct_pw",
            scope="profile",
            issuer="https://auth.example.com",
        )

        assert result.id_token is None

    @pytest.mark.asyncio
    async def test_token_creation_error(self):
        from auth.api.routes.oauth2.token import _handle_password

        user = make_user()
        client = make_oauth2_client()
        auth_svc = AsyncMock()
        auth_svc.authenticate = AsyncMock(return_value=user)
        oauth2_svc = AsyncMock()
        oauth2_svc.validate_scopes = MagicMock(return_value=True)
        token_svc = AsyncMock()
        token_svc.create_token_pair = AsyncMock(side_effect=ValueError("No key"))

        with pytest.raises(HTTPException) as exc_info:
            await _handle_password(
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                auth_service=auth_svc,
                token_service=token_svc,
                client=client,
                username="user@example.com",
                password="correct_pw",
                scope=None,
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "server_error"


# ---------------------------------------------------------------------------
# _handle_device_code
# ---------------------------------------------------------------------------


class TestHandleDeviceCode:
    @pytest.mark.asyncio
    async def test_missing_device_code_raises(self):
        from auth.api.routes.oauth2.token import _handle_device_code

        with pytest.raises(HTTPException) as exc_info:
            await _handle_device_code(
                db=AsyncMock(),
                device_service=AsyncMock(),
                token_service=AsyncMock(),
                client=MagicMock(),
                device_code=None,
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "invalid_request"

    @pytest.mark.asyncio
    async def test_invalid_device_code_raises(self):
        from auth.api.routes.oauth2.token import _handle_device_code

        device_svc = AsyncMock()
        device_svc.get_by_device_code = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await _handle_device_code(
                db=AsyncMock(),
                device_service=device_svc,
                token_service=AsyncMock(),
                client=MagicMock(),
                device_code="bad_dc",
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "invalid_grant"

    @pytest.mark.asyncio
    async def test_client_mismatch_raises(self):
        from auth.api.routes.oauth2.token import _handle_device_code

        client = make_oauth2_client()
        device = make_device_code(client_id=uuid.uuid4())
        device_svc = AsyncMock()
        device_svc.get_by_device_code = AsyncMock(return_value=device)

        with pytest.raises(HTTPException) as exc_info:
            await _handle_device_code(
                db=AsyncMock(),
                device_service=device_svc,
                token_service=AsyncMock(),
                client=client,
                device_code="valid_dc",
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "invalid_grant"

    @pytest.mark.asyncio
    async def test_expired_raises(self):
        from auth.api.routes.oauth2.token import _handle_device_code

        client = make_oauth2_client()
        device = make_device_code(client_id=client.id)
        device_svc = AsyncMock()
        device_svc.get_by_device_code = AsyncMock(return_value=device)
        device_svc.is_expired = MagicMock(return_value=True)

        with pytest.raises(HTTPException) as exc_info:
            await _handle_device_code(
                db=AsyncMock(),
                device_service=device_svc,
                token_service=AsyncMock(),
                client=client,
                device_code="expired_dc",
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "expired_token"

    @pytest.mark.asyncio
    async def test_slow_down_raises(self):
        from auth.api.routes.oauth2.token import _handle_device_code

        client = make_oauth2_client()
        device = make_device_code(client_id=client.id)
        device_svc = AsyncMock()
        device_svc.get_by_device_code = AsyncMock(return_value=device)
        device_svc.is_expired = MagicMock(return_value=False)
        device_svc.is_slow_down_required = MagicMock(return_value=True)

        with pytest.raises(HTTPException) as exc_info:
            await _handle_device_code(
                db=AsyncMock(),
                device_service=device_svc,
                token_service=AsyncMock(),
                client=client,
                device_code="fast_dc",
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "slow_down"

    @pytest.mark.asyncio
    async def test_authorization_pending_raises(self):
        from auth.api.routes.oauth2.token import _handle_device_code

        client = make_oauth2_client()
        device = make_device_code(client_id=client.id, status="pending")
        device_svc = AsyncMock()
        device_svc.get_by_device_code = AsyncMock(return_value=device)
        device_svc.is_expired = MagicMock(return_value=False)
        device_svc.is_slow_down_required = MagicMock(return_value=False)
        device_svc.update_poll_time = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await _handle_device_code(
                db=AsyncMock(),
                device_service=device_svc,
                token_service=AsyncMock(),
                client=client,
                device_code="pending_dc",
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "authorization_pending"

    @pytest.mark.asyncio
    async def test_denied_raises(self):
        from auth.api.routes.oauth2.token import _handle_device_code

        client = make_oauth2_client()
        device = make_device_code(client_id=client.id, status="denied")
        device_svc = AsyncMock()
        device_svc.get_by_device_code = AsyncMock(return_value=device)
        device_svc.is_expired = MagicMock(return_value=False)
        device_svc.is_slow_down_required = MagicMock(return_value=False)
        device_svc.update_poll_time = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await _handle_device_code(
                db=AsyncMock(),
                device_service=device_svc,
                token_service=AsyncMock(),
                client=client,
                device_code="denied_dc",
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "access_denied"

    @pytest.mark.asyncio
    async def test_unknown_status_raises(self):
        from auth.api.routes.oauth2.token import _handle_device_code

        client = make_oauth2_client()
        device = make_device_code(client_id=client.id, status="unknown_status")
        device_svc = AsyncMock()
        device_svc.get_by_device_code = AsyncMock(return_value=device)
        device_svc.is_expired = MagicMock(return_value=False)
        device_svc.is_slow_down_required = MagicMock(return_value=False)
        device_svc.update_poll_time = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await _handle_device_code(
                db=AsyncMock(),
                device_service=device_svc,
                token_service=AsyncMock(),
                client=client,
                device_code="weird_dc",
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "invalid_grant"

    @pytest.mark.asyncio
    async def test_authorized_success(self):
        from auth.api.routes.oauth2.token import _handle_device_code

        client = make_oauth2_client()
        device = make_device_code(
            client_id=client.id,
            status="authorized",
            user_id="user-device-1",
            scopes=["openid", "profile"],
        )
        db = AsyncMock()
        device_svc = AsyncMock()
        device_svc.get_by_device_code = AsyncMock(return_value=device)
        device_svc.is_expired = MagicMock(return_value=False)
        device_svc.is_slow_down_required = MagicMock(return_value=False)
        device_svc.update_poll_time = AsyncMock()

        token_svc = AsyncMock()
        token_svc.create_token_pair = AsyncMock(return_value=("dc_at", "dc_rt", 3600))

        result = await _handle_device_code(
            db=db,
            device_service=device_svc,
            token_service=token_svc,
            client=client,
            device_code="auth_dc",
            issuer="https://auth.example.com",
        )

        assert result.access_token == "dc_at"
        assert result.refresh_token == "dc_rt"
        assert result.scope == "openid profile"
        device_svc.delete.assert_awaited_once_with(db, device)

    @pytest.mark.asyncio
    async def test_token_creation_error(self):
        from auth.api.routes.oauth2.token import _handle_device_code

        client = make_oauth2_client()
        device = make_device_code(client_id=client.id, status="authorized")
        device_svc = AsyncMock()
        device_svc.get_by_device_code = AsyncMock(return_value=device)
        device_svc.is_expired = MagicMock(return_value=False)
        device_svc.is_slow_down_required = MagicMock(return_value=False)
        device_svc.update_poll_time = AsyncMock()
        token_svc = AsyncMock()
        token_svc.create_token_pair = AsyncMock(side_effect=ValueError("Key error"))

        with pytest.raises(HTTPException) as exc_info:
            await _handle_device_code(
                db=AsyncMock(),
                device_service=device_svc,
                token_service=token_svc,
                client=client,
                device_code="err_dc",
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "server_error"


# ---------------------------------------------------------------------------
# _handle_token_exchange
# ---------------------------------------------------------------------------


class TestHandleTokenExchange:
    @pytest.mark.asyncio
    async def test_missing_subject_token_raises(self):
        from auth.api.routes.oauth2.token import _handle_token_exchange

        with pytest.raises(HTTPException) as exc_info:
            await _handle_token_exchange(
                db=AsyncMock(),
                token_exchange_service=AsyncMock(),
                token_service=AsyncMock(),
                client=MagicMock(),
                subject_token=None,
                subject_token_type=None,
                actor_token=None,
                actor_token_type=None,
                requested_token_type=None,
                audience=None,
                resource=None,
                scope=None,
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "invalid_request"

    @pytest.mark.asyncio
    async def test_missing_subject_token_type_raises(self):
        from auth.api.routes.oauth2.token import _handle_token_exchange

        with pytest.raises(HTTPException) as exc_info:
            await _handle_token_exchange(
                db=AsyncMock(),
                token_exchange_service=AsyncMock(),
                token_service=AsyncMock(),
                client=MagicMock(),
                subject_token="some_token",
                subject_token_type=None,
                actor_token=None,
                actor_token_type=None,
                requested_token_type=None,
                audience=None,
                resource=None,
                scope=None,
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "invalid_request"

    @pytest.mark.asyncio
    async def test_non_confidential_client_raises(self):
        from auth.api.routes.oauth2.token import _handle_token_exchange

        client = make_oauth2_client(is_confidential=False)

        with pytest.raises(HTTPException) as exc_info:
            await _handle_token_exchange(
                db=AsyncMock(),
                token_exchange_service=AsyncMock(),
                token_service=AsyncMock(),
                client=client,
                subject_token="some_token",
                subject_token_type="urn:ietf:params:oauth:token-type:access_token",
                actor_token=None,
                actor_token_type=None,
                requested_token_type=None,
                audience=None,
                resource=None,
                scope=None,
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "unauthorized_client"

    @pytest.mark.asyncio
    async def test_exchange_error_raises(self):
        from auth.api.routes.oauth2.token import _handle_token_exchange
        from auth.services.token_exchange import TokenExchangeError

        client = make_oauth2_client(is_confidential=True)
        te_svc = AsyncMock()
        te_svc.validate_subject_token = AsyncMock(
            side_effect=TokenExchangeError("invalid_grant", "Token invalid")
        )

        with pytest.raises(HTTPException) as exc_info:
            await _handle_token_exchange(
                db=AsyncMock(),
                token_exchange_service=te_svc,
                token_service=AsyncMock(),
                client=client,
                subject_token="bad_token",
                subject_token_type="urn:ietf:params:oauth:token-type:access_token",
                actor_token=None,
                actor_token_type=None,
                requested_token_type=None,
                audience=None,
                resource=None,
                scope=None,
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "invalid_grant"

    @pytest.mark.asyncio
    async def test_success(self):
        from auth.api.routes.oauth2.token import _handle_token_exchange

        client = make_oauth2_client(is_confidential=True)
        te_svc = AsyncMock()
        te_svc.validate_subject_token = AsyncMock(return_value=(MagicMock(), "user-1", ["openid"]))
        te_svc.validate_actor_token = MagicMock(return_value=None)
        te_svc.determine_scopes = AsyncMock(return_value=["openid", "profile"])
        te_svc.validate_audience = MagicMock(return_value="https://api.example.com")

        token_svc = AsyncMock()
        token_svc.create_token_pair = AsyncMock(return_value=("te_at", None, 3600))

        result = await _handle_token_exchange(
            db=AsyncMock(),
            token_exchange_service=te_svc,
            token_service=token_svc,
            client=client,
            subject_token="valid_token",
            subject_token_type="urn:ietf:params:oauth:token-type:access_token",
            actor_token=None,
            actor_token_type=None,
            requested_token_type=None,
            audience="https://api.example.com",
            resource=None,
            scope="openid profile",
            issuer="https://auth.example.com",
        )

        assert result.access_token == "te_at"
        assert result.refresh_token is None
        assert result.scope == "openid profile"

    @pytest.mark.asyncio
    async def test_token_creation_error(self):
        from auth.api.routes.oauth2.token import _handle_token_exchange

        client = make_oauth2_client(is_confidential=True)
        te_svc = AsyncMock()
        te_svc.validate_subject_token = AsyncMock(return_value=(MagicMock(), "user-1", ["openid"]))
        te_svc.validate_actor_token = MagicMock(return_value=None)
        te_svc.determine_scopes = AsyncMock(return_value=["openid"])
        te_svc.validate_audience = MagicMock(return_value=None)

        token_svc = AsyncMock()
        token_svc.create_token_pair = AsyncMock(side_effect=ValueError("No key"))

        with pytest.raises(HTTPException) as exc_info:
            await _handle_token_exchange(
                db=AsyncMock(),
                token_exchange_service=te_svc,
                token_service=token_svc,
                client=client,
                subject_token="valid_token",
                subject_token_type="urn:ietf:params:oauth:token-type:access_token",
                actor_token=None,
                actor_token_type=None,
                requested_token_type=None,
                audience=None,
                resource=None,
                scope=None,
                issuer="https://auth.example.com",
            )
        assert exc_info.value.detail["error"] == "server_error"


# ---------------------------------------------------------------------------
# token_endpoint - Grant type routing (integration-style)
# ---------------------------------------------------------------------------


class TestTokenEndpointRouting:
    """Tests that the top-level token_endpoint dispatches to the correct handler."""

    @pytest.mark.asyncio
    @patch(f"{MODULE}._handle_authorization_code", new_callable=AsyncMock)
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    async def test_routes_to_authorization_code(self, mock_issuer, mock_handler):
        from auth.api.routes.oauth2.token import token_endpoint
        from auth.api.schemas.oauth2 import TokenResponse

        mock_handler.return_value = TokenResponse(
            access_token="at", token_type="Bearer", expires_in=3600
        )
        client = make_oauth2_client(is_confidential=False)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_grant_type = MagicMock(return_value=True)

        await token_endpoint(
            grant_type="authorization_code",
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            token_service=AsyncMock(),
            device_service=AsyncMock(),
            token_exchange_service=AsyncMock(),
            auth_service=AsyncMock(),
            authorization=None,
            client_id="test_client_id",
            client_secret=None,
            code="c1",
            redirect_uri="https://app.example.com/cb",
            code_verifier=None,
            refresh_token=None,
            scope=None,
            device_code=None,
            username=None,
            password=None,
            subject_token=None,
            subject_token_type=None,
            actor_token=None,
            actor_token_type=None,
            requested_token_type=None,
            audience=None,
            resource=None,
        )

        mock_handler.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}._handle_refresh_token", new_callable=AsyncMock)
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    async def test_routes_to_refresh_token(self, mock_issuer, mock_handler):
        from auth.api.routes.oauth2.token import token_endpoint
        from auth.api.schemas.oauth2 import TokenResponse

        mock_handler.return_value = TokenResponse(
            access_token="at", token_type="Bearer", expires_in=3600
        )
        client = make_oauth2_client(is_confidential=False)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_grant_type = MagicMock(return_value=True)

        await token_endpoint(
            grant_type="refresh_token",
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            token_service=AsyncMock(),
            device_service=AsyncMock(),
            token_exchange_service=AsyncMock(),
            auth_service=AsyncMock(),
            authorization=None,
            client_id="test_client_id",
            client_secret=None,
            code=None,
            redirect_uri=None,
            code_verifier=None,
            refresh_token="rt_value",
            scope=None,
            device_code=None,
            username=None,
            password=None,
            subject_token=None,
            subject_token_type=None,
            actor_token=None,
            actor_token_type=None,
            requested_token_type=None,
            audience=None,
            resource=None,
        )

        mock_handler.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}._handle_client_credentials", new_callable=AsyncMock)
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    async def test_routes_to_client_credentials(self, mock_issuer, mock_handler):
        from auth.api.routes.oauth2.token import token_endpoint
        from auth.api.schemas.oauth2 import TokenResponse

        mock_handler.return_value = TokenResponse(
            access_token="at", token_type="Bearer", expires_in=3600
        )
        client = make_oauth2_client(is_confidential=False)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_grant_type = MagicMock(return_value=True)

        await token_endpoint(
            grant_type="client_credentials",
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            token_service=AsyncMock(),
            device_service=AsyncMock(),
            token_exchange_service=AsyncMock(),
            auth_service=AsyncMock(),
            authorization=None,
            client_id="test_client_id",
            client_secret=None,
            code=None,
            redirect_uri=None,
            code_verifier=None,
            refresh_token=None,
            scope=None,
            device_code=None,
            username=None,
            password=None,
            subject_token=None,
            subject_token_type=None,
            actor_token=None,
            actor_token_type=None,
            requested_token_type=None,
            audience=None,
            resource=None,
        )

        mock_handler.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}._handle_password", new_callable=AsyncMock)
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    async def test_routes_to_password(self, mock_issuer, mock_handler):
        from auth.api.routes.oauth2.token import token_endpoint
        from auth.api.schemas.oauth2 import TokenResponse

        mock_handler.return_value = TokenResponse(
            access_token="at", token_type="Bearer", expires_in=3600
        )
        client = make_oauth2_client(is_confidential=False)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_grant_type = MagicMock(return_value=True)

        await token_endpoint(
            grant_type="password",
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            token_service=AsyncMock(),
            device_service=AsyncMock(),
            token_exchange_service=AsyncMock(),
            auth_service=AsyncMock(),
            authorization=None,
            client_id="test_client_id",
            client_secret=None,
            code=None,
            redirect_uri=None,
            code_verifier=None,
            refresh_token=None,
            scope=None,
            device_code=None,
            username="user",
            password="pw",
            subject_token=None,
            subject_token_type=None,
            actor_token=None,
            actor_token_type=None,
            requested_token_type=None,
            audience=None,
            resource=None,
        )

        mock_handler.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}._handle_device_code", new_callable=AsyncMock)
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    async def test_routes_to_device_code(self, mock_issuer, mock_handler):
        from auth.api.routes.oauth2.token import token_endpoint
        from auth.api.schemas.oauth2 import TokenResponse

        mock_handler.return_value = TokenResponse(
            access_token="at", token_type="Bearer", expires_in=3600
        )
        client = make_oauth2_client(is_confidential=False)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_grant_type = MagicMock(return_value=True)

        await token_endpoint(
            grant_type="urn:ietf:params:oauth:grant-type:device_code",
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            token_service=AsyncMock(),
            device_service=AsyncMock(),
            token_exchange_service=AsyncMock(),
            auth_service=AsyncMock(),
            authorization=None,
            client_id="test_client_id",
            client_secret=None,
            code=None,
            redirect_uri=None,
            code_verifier=None,
            refresh_token=None,
            scope=None,
            device_code="dc_123",
            username=None,
            password=None,
            subject_token=None,
            subject_token_type=None,
            actor_token=None,
            actor_token_type=None,
            requested_token_type=None,
            audience=None,
            resource=None,
        )

        mock_handler.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}._handle_token_exchange", new_callable=AsyncMock)
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    async def test_routes_to_token_exchange(self, mock_issuer, mock_handler):
        from auth.api.routes.oauth2.token import token_endpoint
        from auth.api.schemas.oauth2 import TokenResponse

        mock_handler.return_value = TokenResponse(
            access_token="at", token_type="Bearer", expires_in=3600
        )
        client = make_oauth2_client(is_confidential=False)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.validate_grant_type = MagicMock(return_value=True)

        await token_endpoint(
            grant_type="urn:ietf:params:oauth:grant-type:token-exchange",
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            token_service=AsyncMock(),
            device_service=AsyncMock(),
            token_exchange_service=AsyncMock(),
            auth_service=AsyncMock(),
            authorization=None,
            client_id="test_client_id",
            client_secret=None,
            code=None,
            redirect_uri=None,
            code_verifier=None,
            refresh_token=None,
            scope=None,
            device_code=None,
            username=None,
            password=None,
            subject_token="st",
            subject_token_type="urn:ietf:params:oauth:token-type:access_token",
            actor_token=None,
            actor_token_type=None,
            requested_token_type=None,
            audience=None,
            resource=None,
        )

        mock_handler.assert_awaited_once()


class TestConfidentialClientWithValidSecret:
    @pytest.mark.asyncio
    @patch(f"{MODULE}._handle_client_credentials", new_callable=AsyncMock)
    @patch(
        f"{MODULE}.get_issuer_from_context",
        new_callable=AsyncMock,
        return_value="https://auth.example.com",
    )
    async def test_valid_secret_proceeds_to_grant_dispatch(self, mock_issuer, mock_handler):
        from auth.api.routes.oauth2.token import token_endpoint
        from auth.api.schemas.oauth2 import TokenResponse

        mock_handler.return_value = TokenResponse(
            access_token="at", token_type="Bearer", expires_in=3600
        )
        client = make_oauth2_client(is_confidential=True)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.verify_client_secret = MagicMock(return_value=True)
        oauth2_svc.validate_grant_type = MagicMock(return_value=True)

        await token_endpoint(
            grant_type="client_credentials",
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            token_service=AsyncMock(),
            device_service=AsyncMock(),
            token_exchange_service=AsyncMock(),
            auth_service=AsyncMock(),
            authorization=None,
            client_id="test_client_id",
            client_secret="correct",
            code=None,
            redirect_uri=None,
            code_verifier=None,
            refresh_token=None,
            scope=None,
            device_code=None,
            username=None,
            password=None,
            subject_token=None,
            subject_token_type=None,
            actor_token=None,
            actor_token_type=None,
            requested_token_type=None,
            audience=None,
            resource=None,
        )

        mock_handler.assert_awaited_once()


class TestAuthorizationCodePkceSuccess:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.verify_code_challenge", return_value=True)
    @patch(f"{MODULE}.is_valid_code_verifier", return_value=True)
    async def test_valid_verifier_proceeds(self, mock_valid, mock_verify):
        from auth.api.routes.oauth2.token import _handle_authorization_code

        client = make_oauth2_client()
        auth_code = make_authorization_code(
            client_id=client.id,
            redirect_uri="https://app.example.com/callback",
            scopes=["profile"],
            user_id="user-1",
        )
        auth_code.code_challenge = "challenge"
        auth_code.code_challenge_method = None  # exercises the S256 default

        oauth2_svc = AsyncMock()
        oauth2_svc.get_authorization_code = AsyncMock(return_value=auth_code)
        oauth2_svc.consume_authorization_code = AsyncMock()
        token_svc = AsyncMock()
        token_svc.create_token_pair = AsyncMock(return_value=("at", "rt", 3600))

        result = await _handle_authorization_code(
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            token_service=token_svc,
            client=client,
            code="valid_code",
            redirect_uri="https://app.example.com/callback",
            code_verifier="verifier",
            issuer="https://auth.example.com",
        )

        assert result.access_token == "at"
        mock_verify.assert_called_once_with("verifier", "challenge", "S256")


class TestIdTokenCreationFailures:
    """A failing ID token is logged and the grant still returns its tokens."""

    @pytest.mark.asyncio
    async def test_authorization_code_grant_continues(self):
        from auth.api.routes.oauth2.token import _handle_authorization_code

        client = make_oauth2_client()
        auth_code = make_authorization_code(
            client_id=client.id,
            redirect_uri="https://app.example.com/callback",
            scopes=["openid"],
            user_id="user-1",
        )
        auth_code.code_challenge = None

        oauth2_svc = AsyncMock()
        oauth2_svc.get_authorization_code = AsyncMock(return_value=auth_code)
        oauth2_svc.consume_authorization_code = AsyncMock()
        token_svc = AsyncMock()
        token_svc.create_token_pair = AsyncMock(return_value=("at", "rt", 3600))
        token_svc.create_id_token = AsyncMock(side_effect=ValueError("no signing key"))

        result = await _handle_authorization_code(
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            token_service=token_svc,
            client=client,
            code="valid_code",
            redirect_uri="https://app.example.com/callback",
            code_verifier=None,
            issuer="https://auth.example.com",
        )

        assert result.access_token == "at"
        assert result.id_token is None

    @pytest.mark.asyncio
    async def test_password_grant_continues(self):
        from auth.api.routes.oauth2.token import _handle_password

        client = make_oauth2_client(allowed_scopes=["openid"])
        auth_svc = AsyncMock()
        auth_svc.authenticate = AsyncMock(return_value=make_user())
        oauth2_svc = AsyncMock()
        oauth2_svc.validate_scopes = MagicMock(return_value=True)
        token_svc = AsyncMock()
        token_svc.create_token_pair = AsyncMock(return_value=("pw_at", "pw_rt", 3600))
        token_svc.create_id_token = AsyncMock(side_effect=ValueError("no signing key"))

        result = await _handle_password(
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            auth_service=auth_svc,
            token_service=token_svc,
            client=client,
            username="user@example.com",
            password="correct_pw",
            scope="openid",
            issuer="https://auth.example.com",
        )

        assert result.access_token == "pw_at"
        assert result.id_token is None


class TestPasswordGrantMfaDisabled:
    @pytest.mark.asyncio
    async def test_mfa_service_present_but_totp_disabled(self):
        from auth.api.routes.oauth2.token import _handle_password

        client = make_oauth2_client(allowed_scopes=["profile"])
        auth_svc = AsyncMock()
        auth_svc.authenticate = AsyncMock(return_value=make_user())
        oauth2_svc = AsyncMock()
        oauth2_svc.validate_scopes = MagicMock(return_value=True)
        token_svc = AsyncMock()
        token_svc.create_token_pair = AsyncMock(return_value=("pw_at", "pw_rt", 3600))
        mfa_svc = AsyncMock()
        mfa_svc.get_user_mfa = AsyncMock(return_value=MagicMock(totp_enabled=False))

        result = await _handle_password(
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            auth_service=auth_svc,
            token_service=token_svc,
            client=client,
            username="user@example.com",
            password="correct_pw",
            scope=None,
            issuer="https://auth.example.com",
            mfa_service=mfa_svc,
        )

        assert result.access_token == "pw_at"
        mfa_svc.verify_mfa_code_with_email.assert_not_awaited()
