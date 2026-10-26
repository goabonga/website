# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.api.routes.oauth2.revoke -- Token revocation endpoint (RFC 7009)."""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from tests.conftest import make_oauth2_client

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MODULE = "auth.api.routes.oauth2.revoke"


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
        from auth.api.routes.oauth2.revoke import _parse_basic_auth

        assert _parse_basic_auth(None) == (None, None)

    def test_non_basic(self):
        from auth.api.routes.oauth2.revoke import _parse_basic_auth

        assert _parse_basic_auth("Bearer xyz") == (None, None)

    def test_valid(self):
        from auth.api.routes.oauth2.revoke import _parse_basic_auth

        cid, cs = _parse_basic_auth(_basic_auth("c1", "s1"))
        assert cid == "c1"
        assert cs == "s1"

    def test_invalid_base64(self):
        from auth.api.routes.oauth2.revoke import _parse_basic_auth

        assert _parse_basic_auth("Basic not_valid!!!") == (None, None)

    def test_missing_colon(self):
        from auth.api.routes.oauth2.revoke import _parse_basic_auth

        encoded = base64.b64encode(b"nocolonseparator").decode()
        assert _parse_basic_auth(f"Basic {encoded}") == (None, None)


# ---------------------------------------------------------------------------
# _extract_jti_from_token
# ---------------------------------------------------------------------------


class TestExtractJtiFromToken:
    @patch(f"{MODULE}.jwt")
    def test_valid_jwt(self, mock_jwt):
        import jwt as real_jwt
        from auth.api.routes.oauth2.revoke import _extract_jti_from_token

        mock_jwt.decode = MagicMock(return_value={"jti": "jti-abc-123"})
        mock_jwt.DecodeError = real_jwt.DecodeError

        assert _extract_jti_from_token("valid.jwt.token") == "jti-abc-123"

    @patch(f"{MODULE}.jwt")
    def test_jwt_without_jti(self, mock_jwt):
        import jwt as real_jwt
        from auth.api.routes.oauth2.revoke import _extract_jti_from_token

        mock_jwt.decode = MagicMock(return_value={"sub": "user1"})
        mock_jwt.DecodeError = real_jwt.DecodeError

        assert _extract_jti_from_token("no.jti.jwt") is None

    @patch(f"{MODULE}.jwt")
    def test_invalid_jwt(self, mock_jwt):
        import jwt as real_jwt
        from auth.api.routes.oauth2.revoke import _extract_jti_from_token

        mock_jwt.decode = MagicMock(side_effect=real_jwt.DecodeError("bad"))
        mock_jwt.DecodeError = real_jwt.DecodeError

        assert _extract_jti_from_token("not.a.jwt") is None


# ---------------------------------------------------------------------------
# revoke_token
# ---------------------------------------------------------------------------


class TestRevokeToken:
    @pytest.mark.asyncio
    async def test_no_client_id_raises_401(self):
        from auth.api.routes.oauth2.revoke import revoke_token

        with pytest.raises(HTTPException) as exc_info:
            await revoke_token(
                token="some_token",
                db=AsyncMock(),
                oauth2_service=AsyncMock(),
                token_service=AsyncMock(),
                authorization=None,
                client_id=None,
                client_secret=None,
                token_type_hint=None,
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_client_raises_401(self):
        from auth.api.routes.oauth2.revoke import revoke_token

        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await revoke_token(
                token="some_token",
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                token_service=AsyncMock(),
                authorization=None,
                client_id="bad_client",
                client_secret=None,
                token_type_hint=None,
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_inactive_client_raises_401(self):
        from auth.api.routes.oauth2.revoke import revoke_token

        client = make_oauth2_client()
        client.is_active = False
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)

        with pytest.raises(HTTPException) as exc_info:
            await revoke_token(
                token="some_token",
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                token_service=AsyncMock(),
                authorization=None,
                client_id="test_client_id",
                client_secret=None,
                token_type_hint=None,
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_confidential_client_missing_secret_raises_401(self):
        from auth.api.routes.oauth2.revoke import revoke_token

        client = make_oauth2_client(is_confidential=True)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)

        with pytest.raises(HTTPException) as exc_info:
            await revoke_token(
                token="some_token",
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                token_service=AsyncMock(),
                authorization=None,
                client_id="test_client_id",
                client_secret=None,
                token_type_hint=None,
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_confidential_client_wrong_secret_raises_401(self):
        from auth.api.routes.oauth2.revoke import revoke_token

        client = make_oauth2_client(is_confidential=True)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.verify_client_secret = MagicMock(return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await revoke_token(
                token="some_token",
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                token_service=AsyncMock(),
                authorization=None,
                client_id="test_client_id",
                client_secret="wrong",
                token_type_hint=None,
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}._extract_jti_from_token", return_value="jti-123")
    async def test_default_tries_access_token_first_and_succeeds(self, mock_jti):
        from auth.api.routes.oauth2.revoke import revoke_token

        client = make_oauth2_client(is_confidential=False)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)

        db = AsyncMock()
        token_svc = AsyncMock()
        token_svc.revoke_access_token = AsyncMock(return_value=True)

        result = await revoke_token(
            token="jwt_token",
            db=db,
            oauth2_service=oauth2_svc,
            token_service=token_svc,
            authorization=None,
            client_id="test_client_id",
            client_secret=None,
            token_type_hint=None,
        )

        assert result.status_code == 200
        token_svc.revoke_access_token.assert_awaited_once_with(db, "jti-123")

    @pytest.mark.asyncio
    @patch(f"{MODULE}._extract_jti_from_token", return_value=None)
    async def test_default_falls_to_refresh_token(self, mock_jti):
        from auth.api.routes.oauth2.revoke import revoke_token

        client = make_oauth2_client(is_confidential=False)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)

        token_svc = AsyncMock()
        token_svc.revoke_refresh_token = AsyncMock(return_value=True)

        result = await revoke_token(
            token="opaque_refresh_token",
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            token_service=token_svc,
            authorization=None,
            client_id="test_client_id",
            client_secret=None,
            token_type_hint=None,
        )

        assert result.status_code == 200
        token_svc.revoke_refresh_token.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_hint_refresh_token_tries_refresh_first(self):
        from auth.api.routes.oauth2.revoke import revoke_token

        client = make_oauth2_client(is_confidential=False)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)

        token_svc = AsyncMock()
        token_svc.revoke_refresh_token = AsyncMock(return_value=True)

        result = await revoke_token(
            token="rt_value",
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            token_service=token_svc,
            authorization=None,
            client_id="test_client_id",
            client_secret=None,
            token_type_hint="refresh_token",
        )

        assert result.status_code == 200
        token_svc.revoke_refresh_token.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}._extract_jti_from_token", return_value="jti-456")
    async def test_hint_refresh_not_found_falls_to_access(self, mock_jti):
        from auth.api.routes.oauth2.revoke import revoke_token

        client = make_oauth2_client(is_confidential=False)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)

        token_svc = AsyncMock()
        token_svc.revoke_refresh_token = AsyncMock(return_value=False)
        token_svc.revoke_access_token = AsyncMock(return_value=True)

        result = await revoke_token(
            token="jwt_token",
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            token_service=token_svc,
            authorization=None,
            client_id="test_client_id",
            client_secret=None,
            token_type_hint="refresh_token",
        )

        assert result.status_code == 200
        token_svc.revoke_access_token.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}._extract_jti_from_token", return_value=None)
    async def test_token_not_found_still_returns_200(self, mock_jti):
        from auth.api.routes.oauth2.revoke import revoke_token

        client = make_oauth2_client(is_confidential=False)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)

        token_svc = AsyncMock()
        token_svc.revoke_refresh_token = AsyncMock(return_value=False)

        result = await revoke_token(
            token="unknown_token",
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            token_service=token_svc,
            authorization=None,
            client_id="test_client_id",
            client_secret=None,
            token_type_hint=None,
        )

        # RFC 7009: always 200 OK
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_basic_auth_credentials(self):
        from auth.api.routes.oauth2.revoke import revoke_token

        client = make_oauth2_client(is_confidential=True)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)
        oauth2_svc.verify_client_secret = MagicMock(return_value=True)

        token_svc = AsyncMock()
        token_svc.revoke_refresh_token = AsyncMock(return_value=False)

        with patch(f"{MODULE}._extract_jti_from_token", return_value=None):
            result = await revoke_token(
                token="some_token",
                db=AsyncMock(),
                oauth2_service=oauth2_svc,
                token_service=token_svc,
                authorization=_basic_auth("test_client_id", "my_secret"),
                client_id=None,
                client_secret=None,
                token_type_hint=None,
            )

        assert result.status_code == 200
        oauth2_svc.verify_client_secret.assert_called_once_with(client, "my_secret")

    @pytest.mark.asyncio
    @patch(f"{MODULE}._extract_jti_from_token", return_value="jti-revoked")
    async def test_hint_access_token_revoked_successfully(self, mock_jti):
        from auth.api.routes.oauth2.revoke import revoke_token

        client = make_oauth2_client(is_confidential=False)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)

        token_svc = AsyncMock()
        token_svc.revoke_access_token = AsyncMock(return_value=True)

        result = await revoke_token(
            token="jwt_token",
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            token_service=token_svc,
            authorization=None,
            client_id="test_client_id",
            client_secret=None,
            token_type_hint="access_token",
        )

        assert result.status_code == 200
        token_svc.revoke_access_token.assert_awaited_once()

    @pytest.mark.asyncio
    @patch(f"{MODULE}._extract_jti_from_token", return_value=None)
    async def test_hint_access_token_not_jwt_falls_to_refresh(self, mock_jti):
        from auth.api.routes.oauth2.revoke import revoke_token

        client = make_oauth2_client(is_confidential=False)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)

        token_svc = AsyncMock()
        token_svc.revoke_refresh_token = AsyncMock(return_value=True)

        result = await revoke_token(
            token="opaque_token",
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            token_service=token_svc,
            authorization=None,
            client_id="test_client_id",
            client_secret=None,
            token_type_hint="access_token",
        )

        assert result.status_code == 200
        token_svc.revoke_refresh_token.assert_awaited_once()


class TestRevokeHintRefreshTokenNonJwt:
    @pytest.mark.asyncio
    @patch(f"{MODULE}._extract_jti_from_token", return_value=None)
    async def test_opaque_token_with_refresh_hint_is_not_retried_as_access(self, mock_jti):
        """With hint=refresh_token, an unrevocable opaque token yields a plain 200."""
        from auth.api.routes.oauth2.revoke import revoke_token

        client = make_oauth2_client(is_confidential=False)
        client.is_active = True
        oauth2_svc = AsyncMock()
        oauth2_svc.get_client_by_client_id = AsyncMock(return_value=client)

        token_svc = AsyncMock()
        token_svc.revoke_refresh_token = AsyncMock(return_value=False)
        token_svc.revoke_access_token = AsyncMock()

        result = await revoke_token(
            token="opaque_token",
            db=AsyncMock(),
            oauth2_service=oauth2_svc,
            token_service=token_svc,
            authorization=None,
            client_id="test_client_id",
            client_secret=None,
            token_type_hint="refresh_token",
        )

        assert result.status_code == 200
        token_svc.revoke_access_token.assert_not_awaited()
