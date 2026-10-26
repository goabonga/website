# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.pat — PersonalAccessTokenService and helpers."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.db.models.pat import PATExpirationPreset
from auth.services.pat import (
    PAT_PREFIX,
    PersonalAccessTokenService,
    calculate_expiration,
    generate_pat_token,
    get_token_suffix,
    hash_pat_token,
)

from tests.conftest import make_execute_result, make_personal_access_token, make_user

# ── Helper functions ─────────────────────────────────────────────────────────


class TestGeneratePatToken:
    def test_starts_with_prefix(self):
        token = generate_pat_token()
        assert token.startswith(PAT_PREFIX)

    def test_total_length(self):
        token = generate_pat_token()
        # "gab_pat_" (8 chars) + 64 hex chars = 72
        assert len(token) == 72

    def test_randomness(self):
        assert generate_pat_token() != generate_pat_token()


class TestHashPatToken:
    def test_sha256(self):
        token = "gab_pat_abc123"
        expected = hashlib.sha256(token.encode()).hexdigest()
        assert hash_pat_token(token) == expected


class TestGetTokenSuffix:
    def test_last_four(self):
        assert get_token_suffix("gab_pat_abcdef1234") == "1234"


class TestCalculateExpiration:
    def test_7_days(self):
        result = calculate_expiration(PATExpirationPreset.DAYS_7)
        assert result is not None
        # Should be approximately 7 days from now
        delta = result - datetime.now(UTC)
        assert 6 < delta.total_seconds() / 86400 < 8

    def test_no_expiration(self):
        result = calculate_expiration(PATExpirationPreset.NO_EXPIRATION)
        assert result is None

    def test_custom_days(self):
        result = calculate_expiration(PATExpirationPreset.CUSTOM, custom_days=15)
        assert result is not None
        delta = result - datetime.now(UTC)
        assert 14 < delta.total_seconds() / 86400 < 16

    def test_all_presets_covered(self):
        for preset in PATExpirationPreset:
            if preset == PATExpirationPreset.CUSTOM:
                result = calculate_expiration(preset, custom_days=10)
            else:
                result = calculate_expiration(preset)
            # Just ensure no exception is raised
            assert result is None or isinstance(result, datetime)


# ── PersonalAccessTokenService ───────────────────────────────────────────────


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def service():
    return PersonalAccessTokenService()


class TestCreateToken:
    @pytest.mark.asyncio
    async def test_creates_token(self, db, service):
        user_id = uuid.uuid4()

        with (
            patch("auth.services.pat.PersonalAccessToken") as MockPAT,
            patch("auth.services.pat.dispatch_webhook_event", new_callable=AsyncMock),
        ):
            mock_pat = MagicMock()
            mock_pat.id = uuid.uuid4()
            MockPAT.return_value = mock_pat

            pat, plain_token = await service.create_token(
                db,
                user_id=user_id,
                name="API Token",
                scopes=["openid", "profile"],
            )

        assert plain_token.startswith(PAT_PREFIX)
        db.add.assert_called_once()
        db.flush.assert_called_once()


class TestGetTokenById:
    @pytest.mark.asyncio
    async def test_found(self, db, service):
        pat = make_personal_access_token()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=pat))

        result = await service.get_token_by_id(db, pat.id)
        assert result is pat

    @pytest.mark.asyncio
    async def test_not_found(self, db, service):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await service.get_token_by_id(db, uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_with_user_filter(self, db, service):
        pat = make_personal_access_token()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=pat))

        result = await service.get_token_by_id(db, pat.id, user_id=pat.user_id)
        assert result is pat


class TestValidateToken:
    @pytest.mark.asyncio
    async def test_valid_token(self, db, service):
        user = make_user(is_active=True)
        pat = make_personal_access_token(user=user, scopes=["openid", "profile"])
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=pat))

        token = PAT_PREFIX + "a" * 64
        result = await service.validate_token(db, token)
        assert result is pat

    @pytest.mark.asyncio
    async def test_invalid_prefix(self, db, service):
        result = await service.validate_token(db, "wrong_prefix_token")
        assert result is None

    @pytest.mark.asyncio
    async def test_token_not_found(self, db, service):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await service.validate_token(db, PAT_PREFIX + "a" * 64)
        assert result is None

    @pytest.mark.asyncio
    async def test_inactive_user(self, db, service):
        user = make_user(is_active=False)
        pat = make_personal_access_token(user=user)
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=pat))

        result = await service.validate_token(db, PAT_PREFIX + "a" * 64)
        assert result is None

    @pytest.mark.asyncio
    async def test_missing_scope(self, db, service):
        user = make_user(is_active=True)
        pat = make_personal_access_token(user=user, scopes=["openid"])
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=pat))

        result = await service.validate_token(db, PAT_PREFIX + "a" * 64, required_scope="admin")
        assert result is None


class TestScopeMatches:
    def test_exact_match(self, service):
        assert service._scope_matches(["openid", "profile"], "openid") is True

    def test_no_match(self, service):
        assert service._scope_matches(["openid"], "admin") is False

    def test_wildcard_all(self, service):
        assert service._scope_matches(["*"], "anything") is True

    def test_prefix_wildcard(self, service):
        assert service._scope_matches(["users:*"], "users:read") is True
        assert service._scope_matches(["users:*"], "billing:read") is False


class TestUpdateTokenUsage:
    @pytest.mark.asyncio
    async def test_updates_stats(self, db, service):
        pat = make_personal_access_token(use_count=5)

        await service.update_token_usage(db, pat, ip_address="1.2.3.4")

        assert pat.last_used_at is not None
        assert pat.last_used_ip == "1.2.3.4"
        assert pat.use_count == 6
        db.flush.assert_called_once()


class TestRevokeToken:
    @pytest.mark.asyncio
    async def test_revokes(self, db, service):
        pat = make_personal_access_token(revoked_at=None)
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=pat))

        result = await service.revoke_token(db, pat.id)
        assert result is True
        assert pat.revoked_at is not None

    @pytest.mark.asyncio
    async def test_already_revoked(self, db, service):
        pat = make_personal_access_token(revoked_at=datetime.now(UTC))
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=pat))

        result = await service.revoke_token(db, pat.id)
        assert result is True

    @pytest.mark.asyncio
    async def test_not_found(self, db, service):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await service.revoke_token(db, uuid.uuid4())
        assert result is False


class TestBulkRevoke:
    @pytest.mark.asyncio
    async def test_revokes_all(self, db, service):
        pats = [
            make_personal_access_token(revoked_at=None),
            make_personal_access_token(revoked_at=None),
        ]
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=pats))

        count = await service.bulk_revoke(db, uuid.uuid4())
        assert count == 2
        assert all(p.revoked_at is not None for p in pats)


class TestListUserTokens:
    @pytest.mark.asyncio
    async def test_returns_tokens_and_count(self, db, service):
        pats = [make_personal_access_token(), make_personal_access_token()]

        # Two calls: count query, then fetch query
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=2),  # count
                make_execute_result(scalars_list=pats),  # fetch
            ]
        )

        tokens, total = await service.list_user_tokens(db, uuid.uuid4())
        assert total == 2
        assert len(tokens) == 2

    @pytest.mark.asyncio
    async def test_include_revoked(self, db, service):
        """Cover branch 305→309: include_revoked=True skips revoked filter."""
        pats = [make_personal_access_token(revoked_at=datetime.now(UTC))]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=1),
                make_execute_result(scalars_list=pats),
            ]
        )

        tokens, total = await service.list_user_tokens(db, uuid.uuid4(), include_revoked=True)
        assert total == 1


class TestCalculateExpirationCustomNoDays:
    def test_custom_without_custom_days_returns_none(self):
        """Cover line 89-90: CUSTOM preset without custom_days falls through to None."""
        result = calculate_expiration(PATExpirationPreset.CUSTOM)
        assert result is None

    def test_custom_with_zero_days(self):
        """Cover: CUSTOM with custom_days=0 (falsy) falls through."""
        result = calculate_expiration(PATExpirationPreset.CUSTOM, custom_days=0)
        assert result is None


class TestListAllTokens:
    @pytest.mark.asyncio
    async def test_returns_tokens_and_count(self, db, service):
        """Cover lines 344-367: list_all_tokens admin view."""
        pats = [make_personal_access_token(), make_personal_access_token()]

        # Two calls: count query, then fetch query
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=2),  # count
                make_execute_result(scalars_list=pats),  # fetch
            ]
        )

        tokens, total = await service.list_all_tokens(db)
        assert total == 2
        assert len(tokens) == 2

    @pytest.mark.asyncio
    async def test_with_user_filter(self, db, service):
        """Cover line 346-347: user_id filter in list_all_tokens."""
        pats = [make_personal_access_token()]
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=1),
                make_execute_result(scalars_list=pats),
            ]
        )

        tokens, total = await service.list_all_tokens(db, user_id=uuid.uuid4())
        assert total == 1

    @pytest.mark.asyncio
    async def test_include_revoked(self, db, service):
        """Cover line 349-350: include_revoked=True skips filter."""
        db.execute = AsyncMock(
            side_effect=[
                make_execute_result(scalar_value=0),
                make_execute_result(scalars_list=[]),
            ]
        )

        tokens, total = await service.list_all_tokens(db, include_revoked=True)
        assert total == 0


class TestRegenerateToken:
    @pytest.mark.asyncio
    async def test_success(self, db, service):
        """Cover lines 430-467: regenerate_token."""
        old_pat = make_personal_access_token(name="Old Token", scopes=["openid", "profile"])
        old_pat.description = "Old description"
        old_pat.tenant_id = None
        old_pat.target_client_id = None
        old_pat.expires_at = datetime.now(UTC) + timedelta(days=30)

        # get_token_by_id returns old_pat first, then for revoke, then None isn't needed
        service.get_token_by_id = AsyncMock(return_value=old_pat)

        with (
            patch("auth.services.pat.PersonalAccessToken") as MockPAT,
            patch("auth.services.pat.dispatch_webhook_event", new_callable=AsyncMock),
        ):
            mock_new_pat = MagicMock()
            mock_new_pat.id = uuid.uuid4()
            mock_new_pat.expires_at = None
            MockPAT.return_value = mock_new_pat

            result = await service.regenerate_token(db, old_pat.id, old_pat.user_id)

        assert result is not None
        new_pat, plain_token = result
        assert plain_token.startswith("gab_pat_")

    @pytest.mark.asyncio
    async def test_not_found(self, db, service):
        """Cover line 432-433: token not found returns None."""
        service.get_token_by_id = AsyncMock(return_value=None)

        result = await service.regenerate_token(db, uuid.uuid4(), uuid.uuid4())
        assert result is None


class TestCleanupExpiredTokens:
    @pytest.mark.asyncio
    async def test_deletes_expired(self, db, service):
        expired_pat = make_personal_access_token(expires_at=datetime.now(UTC) - timedelta(days=60))
        expired_pat.revoked_at = None

        revoked_pat = make_personal_access_token(revoked_at=datetime.now(UTC) - timedelta(days=100))
        revoked_pat.expires_at = None

        db.execute = AsyncMock(
            return_value=make_execute_result(scalars_list=[expired_pat, revoked_pat])
        )

        result = await service.cleanup_expired_tokens(db)
        assert result["total_deleted"] == 2
        assert db.delete.call_count == 2

    @pytest.mark.asyncio
    async def test_counts_expired_and_revoked_separately(self, db, service):
        """Cover branch 551→553: both expired and revoked categories counted."""
        expired_pat = make_personal_access_token(expires_at=datetime.now(UTC) - timedelta(days=60))
        expired_pat.revoked_at = None

        revoked_pat = make_personal_access_token(revoked_at=datetime.now(UTC) - timedelta(days=100))
        revoked_pat.expires_at = None

        db.execute = AsyncMock(
            return_value=make_execute_result(scalars_list=[expired_pat, revoked_pat])
        )

        result = await service.cleanup_expired_tokens(db)
        assert result["expired_deleted"] == 1
        assert result["revoked_deleted"] == 1
        assert result["total_deleted"] == 2

    @pytest.mark.asyncio
    async def test_uncategorized_token_still_deleted(self, db, service):
        """Cover branch 551→553: token that doesn't match either category."""
        uncategorized = make_personal_access_token()
        uncategorized.revoked_at = None
        uncategorized.expires_at = None

        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=[uncategorized]))

        result = await service.cleanup_expired_tokens(db)
        assert result["expired_deleted"] == 0
        assert result["revoked_deleted"] == 0
        assert result["total_deleted"] == 0
        # Token is still deleted from DB
        db.delete.assert_called_once()


class TestUpdateTokenScopes:
    @pytest.mark.asyncio
    async def test_updates_scopes(self):
        from auth.services.pat import PersonalAccessTokenService

        service = PersonalAccessTokenService()
        pat = make_personal_access_token()
        pat.revoked_at = None
        service.get_token_by_id = AsyncMock(return_value=pat)
        db = AsyncMock()
        token_id, user_id = uuid.uuid4(), uuid.uuid4()

        result = await service.update_token_scopes(db, token_id, user_id, ["users:read"])

        assert result is pat
        assert pat.scopes == ["users:read"]
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unknown_token_returns_none(self):
        from auth.services.pat import PersonalAccessTokenService

        service = PersonalAccessTokenService()
        service.get_token_by_id = AsyncMock(return_value=None)

        result = await service.update_token_scopes(
            AsyncMock(), uuid.uuid4(), uuid.uuid4(), ["users:read"]
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_revoked_token_returns_none(self):
        from auth.services.pat import PersonalAccessTokenService

        service = PersonalAccessTokenService()
        pat = make_personal_access_token()
        pat.revoked_at = datetime.now(UTC)
        service.get_token_by_id = AsyncMock(return_value=pat)

        result = await service.update_token_scopes(
            AsyncMock(), uuid.uuid4(), uuid.uuid4(), ["users:read"]
        )
        assert result is None


class TestBulkRevokeAll:
    @pytest.mark.asyncio
    async def test_revokes_every_active_token(self):
        from auth.services.pat import PersonalAccessTokenService

        service = PersonalAccessTokenService()
        tokens = [make_personal_access_token(), make_personal_access_token()]
        service._repo.list_active = AsyncMock(return_value=tokens)
        db = AsyncMock()
        admin_id = uuid.uuid4()

        count = await service.bulk_revoke_all(db, revoked_by=admin_id, reason="security incident")

        assert count == 2
        for token in tokens:
            assert token.revoked_at is not None
            assert token.revoked_by == admin_id
            assert token.revocation_reason == "security incident"
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_active_tokens(self):
        from auth.services.pat import PersonalAccessTokenService

        service = PersonalAccessTokenService()
        service._repo.list_active = AsyncMock(return_value=[])

        assert await service.bulk_revoke_all(AsyncMock()) == 0
