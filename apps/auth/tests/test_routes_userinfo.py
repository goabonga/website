# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.api.routes.userinfo — OIDC UserInfo endpoint."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

MODULE = "auth.api.routes.userinfo"


_SENTINEL = object()


def _make_token_record(revoked=False, expired=False, user_id=_SENTINEL):
    rec = MagicMock()
    rec.revoked_at = datetime.now(UTC) if revoked else None
    if expired:
        rec.expires_at = datetime.now(UTC) - timedelta(hours=1)
    else:
        rec.expires_at = datetime.now(UTC) + timedelta(hours=1)
    rec.user_id = uuid.uuid4() if user_id is _SENTINEL else user_id
    return rec


def _make_user(with_profile=True, with_email=True, active=True):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = active

    if with_profile:
        profile = MagicMock()
        profile.name = "John Doe"
        profile.given_name = "John"
        profile.family_name = "Doe"
        profile.middle_name = None
        profile.nickname = "johnny"
        profile.preferred_username = "johnd"
        profile.profile_url = "https://example.com/johnd"
        profile.picture_url = "https://example.com/pic.jpg"
        profile.website = "https://johndoe.com"
        profile.gender = "male"
        profile.birthdate = "1990-01-01"
        profile.zoneinfo = "America/New_York"
        profile.locale = "en-US"
        profile.updated_at = datetime(2025, 1, 1, tzinfo=UTC)
        profile.phone_number = "+1234567890"
        profile.phone_number_verified = True
        profile.address_formatted = "123 Main St"
        profile.address_street = "123 Main St"
        profile.address_locality = "Anytown"
        profile.address_region = "NY"
        profile.address_postal_code = "12345"
        profile.address_country = "US"
        user.profile = profile
    else:
        user.profile = None

    if with_email:
        email_obj = MagicMock()
        email_obj.email = "john@example.com"
        email_obj.is_primary = True
        email_obj.is_verified = True
        user.emails = [email_obj]
    else:
        user.emails = []

    return user


# ---------------------------------------------------------------------------
# _extract_bearer_token
# ---------------------------------------------------------------------------


class TestExtractBearerToken:
    def test_valid(self):
        from auth.api.routes.userinfo import _extract_bearer_token

        assert _extract_bearer_token("Bearer abc123") == "abc123"

    def test_none(self):
        from auth.api.routes.userinfo import _extract_bearer_token

        assert _extract_bearer_token(None) is None

    def test_no_bearer_prefix(self):
        from auth.api.routes.userinfo import _extract_bearer_token

        assert _extract_bearer_token("Token abc") is None

    def test_empty(self):
        from auth.api.routes.userinfo import _extract_bearer_token

        assert _extract_bearer_token("") is None


# ---------------------------------------------------------------------------
# _get_userinfo
# ---------------------------------------------------------------------------


class TestGetUserinfo:
    @pytest.mark.asyncio
    async def test_invalid_token_format(self):
        from auth.api.routes.userinfo import _get_userinfo

        db = AsyncMock()
        token_service = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await _get_userinfo(db, token_service, "not-a-jwt")
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.jwt")
    async def test_missing_jti(self, mock_jwt):
        from auth.api.routes.userinfo import _get_userinfo

        mock_jwt.decode.return_value = {"sub": "user1"}
        mock_jwt.DecodeError = Exception

        with pytest.raises(HTTPException) as exc:
            await _get_userinfo(AsyncMock(), AsyncMock(), "valid.jwt.token")
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.jwt")
    async def test_token_not_in_db(self, mock_jwt):
        from auth.api.routes.userinfo import _get_userinfo

        mock_jwt.decode.return_value = {"jti": "abc", "scope": "openid"}
        mock_jwt.DecodeError = Exception

        token_service = AsyncMock()
        token_service.get_access_token_by_jti = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc:
            await _get_userinfo(AsyncMock(), token_service, "valid.jwt.token")
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.jwt")
    async def test_token_revoked(self, mock_jwt):
        from auth.api.routes.userinfo import _get_userinfo

        mock_jwt.decode.return_value = {"jti": "abc", "scope": "openid"}
        mock_jwt.DecodeError = Exception

        token_service = AsyncMock()
        token_service.get_access_token_by_jti = AsyncMock(
            return_value=_make_token_record(revoked=True)
        )

        with pytest.raises(HTTPException) as exc:
            await _get_userinfo(AsyncMock(), token_service, "valid.jwt.token")
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.jwt")
    async def test_token_expired(self, mock_jwt):
        from auth.api.routes.userinfo import _get_userinfo

        mock_jwt.decode.return_value = {"jti": "abc", "scope": "openid"}
        mock_jwt.DecodeError = Exception

        token_service = AsyncMock()
        token_service.get_access_token_by_jti = AsyncMock(
            return_value=_make_token_record(expired=True)
        )

        with pytest.raises(HTTPException) as exc:
            await _get_userinfo(AsyncMock(), token_service, "valid.jwt.token")
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.jwt")
    async def test_missing_openid_scope(self, mock_jwt):
        from auth.api.routes.userinfo import _get_userinfo

        mock_jwt.decode.return_value = {"jti": "abc", "scope": "profile"}
        mock_jwt.DecodeError = Exception

        token_service = AsyncMock()
        token_service.get_access_token_by_jti = AsyncMock(return_value=_make_token_record())

        with pytest.raises(HTTPException) as exc:
            await _get_userinfo(AsyncMock(), token_service, "valid.jwt.token")
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    @patch(f"{MODULE}.jwt")
    async def test_no_user_id_on_token(self, mock_jwt):
        from auth.api.routes.userinfo import _get_userinfo

        mock_jwt.decode.return_value = {"jti": "abc", "scope": "openid"}
        mock_jwt.DecodeError = Exception

        token_service = AsyncMock()
        token_service.get_access_token_by_jti = AsyncMock(
            return_value=_make_token_record(user_id=None)
        )

        with pytest.raises(HTTPException) as exc:
            await _get_userinfo(AsyncMock(), token_service, "valid.jwt.token")
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.jwt")
    async def test_user_not_found(self, mock_jwt):
        from auth.api.routes.userinfo import _get_userinfo

        uid = uuid.uuid4()
        mock_jwt.decode.return_value = {"jti": "abc", "scope": "openid"}
        mock_jwt.DecodeError = Exception

        token_service = AsyncMock()
        token_service.get_access_token_by_jti = AsyncMock(
            return_value=_make_token_record(user_id=uid)
        )

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(HTTPException) as exc:
            await _get_userinfo(db, token_service, "valid.jwt.token")
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}.jwt")
    async def test_success_openid_only(self, mock_jwt):
        from auth.api.routes.userinfo import _get_userinfo

        user = _make_user()
        mock_jwt.decode.return_value = {"jti": "abc", "scope": "openid"}
        mock_jwt.DecodeError = Exception

        token_record = _make_token_record(user_id=user.id)
        token_record.client_id = uuid.uuid4()

        token_service = AsyncMock()
        token_service.get_access_token_by_jti = AsyncMock(return_value=token_record)

        # db.execute called twice: user lookup then client lookup (client not found -> fallback)
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        client_result = MagicMock()
        client_result.scalar_one_or_none.return_value = None

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[user_result, client_result])

        claims = await _get_userinfo(db, token_service, "valid.jwt.token")
        assert claims["sub"] == str(user.id)
        assert "email" not in claims
        assert "name" not in claims

    @pytest.mark.asyncio
    @patch(f"{MODULE}.jwt")
    async def test_success_all_scopes(self, mock_jwt):
        from auth.api.routes.userinfo import _get_userinfo

        user = _make_user()
        mock_jwt.decode.return_value = {
            "jti": "abc",
            "scope": "openid profile email phone address",
        }
        mock_jwt.DecodeError = Exception

        token_record = _make_token_record(user_id=user.id)
        token_record.client_id = uuid.uuid4()

        token_service = AsyncMock()
        token_service.get_access_token_by_jti = AsyncMock(return_value=token_record)

        # db.execute called twice: user lookup then client lookup (client not found -> fallback)
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        client_result = MagicMock()
        client_result.scalar_one_or_none.return_value = None

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[user_result, client_result])

        claims = await _get_userinfo(db, token_service, "valid.jwt.token")
        assert claims["sub"] == str(user.id)
        assert claims["name"] == "John Doe"
        assert claims["email"] == "john@example.com"
        assert claims["email_verified"] is True
        assert claims["phone_number"] == "+1234567890"
        assert claims["address"]["street_address"] == "123 Main St"


# ---------------------------------------------------------------------------
# get_userinfo / post_userinfo
# ---------------------------------------------------------------------------


class TestGetUserinfoEndpoint:
    @pytest.mark.asyncio
    async def test_missing_auth(self):
        from auth.api.routes.userinfo import get_userinfo

        with pytest.raises(HTTPException) as exc:
            await get_userinfo(AsyncMock(), AsyncMock(), authorization=None)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}._get_userinfo", new_callable=AsyncMock, return_value={"sub": "u1"})
    async def test_success(self, mock_get):
        from auth.api.routes.userinfo import get_userinfo

        result = await get_userinfo(AsyncMock(), AsyncMock(), authorization="Bearer tok")
        assert result["sub"] == "u1"


class TestPostUserinfoEndpoint:
    @pytest.mark.asyncio
    async def test_missing_auth(self):
        from auth.api.routes.userinfo import post_userinfo

        with pytest.raises(HTTPException) as exc:
            await post_userinfo(AsyncMock(), AsyncMock(), authorization=None)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    @patch(f"{MODULE}._get_userinfo", new_callable=AsyncMock, return_value={"sub": "u1"})
    async def test_success(self, mock_get):
        from auth.api.routes.userinfo import post_userinfo

        result = await post_userinfo(AsyncMock(), AsyncMock(), authorization="Bearer tok")
        assert result["sub"] == "u1"


# ---------------------------------------------------------------------------
# Pairwise subject in userinfo
# ---------------------------------------------------------------------------


class TestGetUserinfoPairwise:
    """Tests for pairwise subject identifier support in userinfo."""

    @pytest.mark.asyncio
    @patch(f"{MODULE}.jwt")
    async def test_pairwise_replaces_sub(self, mock_jwt):
        """Sub should be the pairwise value."""
        from auth.api.routes.userinfo import _get_userinfo

        user = _make_user()
        pairwise_sub = str(uuid.uuid4())

        mock_jwt.decode.return_value = {"jti": "abc", "scope": "openid"}
        mock_jwt.DecodeError = Exception

        token_record = _make_token_record(user_id=user.id)
        token_record.client_id = uuid.uuid4()

        token_service = AsyncMock()
        token_service.get_access_token_by_jti = AsyncMock(return_value=token_record)

        # Mock the OAuth2Client returned by db.execute
        mock_client = MagicMock()
        mock_client.tenant_id = uuid.uuid4()

        # db.execute is called twice: once for user, once for client
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user

        client_result = MagicMock()
        client_result.scalar_one_or_none.return_value = mock_client

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[user_result, client_result])

        with patch(f"{MODULE}.PairwiseSubjectService") as mock_pw_cls:
            mock_pw_instance = AsyncMock()
            mock_pw_instance.get_sub_for_client = AsyncMock(return_value=pairwise_sub)
            mock_pw_cls.return_value = mock_pw_instance

            claims = await _get_userinfo(db, token_service, "valid.jwt.token")

        assert claims["sub"] == pairwise_sub
        mock_pw_instance.get_sub_for_client.assert_awaited_once_with(db, user.id, mock_client)

    @pytest.mark.asyncio
    @patch(f"{MODULE}.jwt")
    async def test_pairwise_client_not_found_keeps_user_id(self, mock_jwt):
        """When client is not found, sub falls back to user_id."""
        from auth.api.routes.userinfo import _get_userinfo

        user = _make_user()

        mock_jwt.decode.return_value = {"jti": "abc", "scope": "openid"}
        mock_jwt.DecodeError = Exception

        token_record = _make_token_record(user_id=user.id)
        token_record.client_id = uuid.uuid4()

        token_service = AsyncMock()
        token_service.get_access_token_by_jti = AsyncMock(return_value=token_record)

        # db.execute: user found, client not found
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user

        client_result = MagicMock()
        client_result.scalar_one_or_none.return_value = None

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[user_result, client_result])

        claims = await _get_userinfo(db, token_service, "valid.jwt.token")
        assert claims["sub"] == str(user.id)


# ---------------------------------------------------------------------------
# Claim assembly branches
# ---------------------------------------------------------------------------


def _empty_profile_user():
    """A user whose profile exists but has every optional claim unset."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = True
    profile = MagicMock()
    for attr in (
        "name",
        "given_name",
        "family_name",
        "middle_name",
        "nickname",
        "preferred_username",
        "profile_url",
        "picture_url",
        "website",
        "gender",
        "birthdate",
        "zoneinfo",
        "locale",
        "updated_at",
        "phone_number",
        "address_formatted",
        "address_street",
        "address_locality",
        "address_region",
        "address_postal_code",
        "address_country",
    ):
        setattr(profile, attr, None)
    user.profile = profile
    user.emails = []
    return user


async def _claims_for(user, scope):
    """Run ``_get_userinfo`` for ``user`` with ``scope`` and return the claims."""
    from auth.api.routes.userinfo import _get_userinfo

    token_record = _make_token_record(user_id=user.id)
    token_record.client_id = uuid.uuid4()

    token_service = AsyncMock()
    token_service.get_access_token_by_jti = AsyncMock(return_value=token_record)

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user
    client_result = MagicMock()
    client_result.scalar_one_or_none.return_value = None

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[user_result, client_result])

    with patch("auth.api.routes.userinfo.jwt") as mock_jwt:
        mock_jwt.decode.return_value = {"jti": "abc", "scope": scope}
        mock_jwt.DecodeError = Exception
        return await _get_userinfo(db, token_service, "valid.jwt.token")


class TestClaimsWithEmptyProfile:
    @pytest.mark.asyncio
    async def test_no_optional_claims_are_emitted(self):
        claims = await _claims_for(_empty_profile_user(), "openid profile phone address")

        assert set(claims) == {"sub"}

    @pytest.mark.asyncio
    async def test_no_emails_omits_email_claims(self):
        claims = await _claims_for(_empty_profile_user(), "openid email")

        assert "email" not in claims
        assert "email_verified" not in claims


class TestClaimsWithFullProfile:
    @pytest.mark.asyncio
    async def test_every_profile_claim_is_emitted(self):
        user = _make_user()
        user.profile.middle_name = "Quincy"

        claims = await _claims_for(user, "openid profile email phone address")

        assert claims["middle_name"] == "Quincy"
        assert claims["nickname"] == "johnny"
        assert claims["preferred_username"] == "johnd"
        assert claims["profile"] == "https://example.com/johnd"
        assert claims["picture"] == "https://example.com/pic.jpg"
        assert claims["website"] == "https://johndoe.com"
        assert claims["gender"] == "male"
        assert claims["birthdate"] == "1990-01-01"
        assert claims["zoneinfo"] == "America/New_York"
        assert claims["locale"] == "en-US"
        assert claims["updated_at"] == int(datetime(2025, 1, 1, tzinfo=UTC).timestamp())
        assert claims["address"] == {
            "formatted": "123 Main St",
            "street_address": "123 Main St",
            "locality": "Anytown",
            "region": "NY",
            "postal_code": "12345",
            "country": "US",
        }

    @pytest.mark.asyncio
    async def test_falls_back_to_first_email_when_none_is_primary(self):
        user = _make_user()
        user.emails[0].is_primary = False

        claims = await _claims_for(user, "openid email")

        assert claims["email"] == "john@example.com"
