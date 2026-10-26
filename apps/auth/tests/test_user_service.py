# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.user — UserService (repository mocked)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.services.user import UserService

from tests.conftest import make_execute_result, make_user


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def repo():
    """Mock UserRepository — every method is an AsyncMock."""
    mock = MagicMock()
    mock.find_by_id = AsyncMock()
    mock.find_by_email = AsyncMock()
    mock.email_exists = AsyncMock()
    mock.list = AsyncMock()
    mock.add = AsyncMock()
    mock.delete = AsyncMock()
    mock.add_email = AsyncMock()
    mock.delete_email = AsyncMock()
    mock.add_password = AsyncMock()
    mock.add_profile = AsyncMock()
    return mock


@pytest.fixture
def tenant_repo():
    """Mock TenantRepository — exposes the methods UserService calls."""
    mock = MagicMock()
    mock.add_member = AsyncMock()
    return mock


@pytest.fixture
def service(repo, tenant_repo):
    return UserService(repository=repo, tenant_repository=tenant_repo)


# ── get_by_id ────────────────────────────────────────────────────────────────


class TestGetById:
    @pytest.mark.asyncio
    async def test_delegates_to_repo(self, db, service, repo):
        user = make_user()
        repo.find_by_id.return_value = user
        uid = uuid.uuid4()

        result = await service.get_by_id(db, uid)

        repo.find_by_id.assert_awaited_once_with(db, uid)
        assert result is user


# ── get_by_email ─────────────────────────────────────────────────────────────


class TestGetByEmail:
    @pytest.mark.asyncio
    async def test_found(self, db, service, repo):
        user = make_user()
        repo.find_by_email.return_value = user

        result = await service.get_by_email(db, "test@example.com")

        repo.find_by_email.assert_awaited_once_with(db, "test@example.com")
        assert result is user

    @pytest.mark.asyncio
    async def test_not_found(self, db, service, repo):
        repo.find_by_email.return_value = None

        result = await service.get_by_email(db, "missing@example.com")
        assert result is None


# ── email_exists ─────────────────────────────────────────────────────────────


class TestEmailExists:
    @pytest.mark.asyncio
    async def test_exists(self, db, service, repo):
        repo.email_exists.return_value = True

        result = await service.email_exists(db, "existing@example.com")

        repo.email_exists.assert_awaited_once_with(db, "existing@example.com")
        assert result is True

    @pytest.mark.asyncio
    async def test_not_exists(self, db, service, repo):
        repo.email_exists.return_value = False
        assert await service.email_exists(db, "new@example.com") is False


# ── list ─────────────────────────────────────────────────────────────────────


class TestList:
    @pytest.mark.asyncio
    async def test_forwards_all_args(self, db, service, repo):
        users = [make_user(), make_user()]
        repo.list.return_value = (users, 2)
        tid = uuid.uuid4()

        result = await service.list(
            db,
            page=2,
            page_size=50,
            search="alice",
            is_active=True,
            registration_tenant_id=tid,
            filter_no_tenant=False,
        )

        assert result == (users, 2)
        repo.list.assert_awaited_once_with(
            db,
            page=2,
            page_size=50,
            search="alice",
            is_active=True,
            registration_tenant_id=tid,
            filter_no_tenant=False,
        )


# ── create_user ──────────────────────────────────────────────────────────────


class TestCreateUser:
    @pytest.mark.asyncio
    async def test_creates_user_basic(self, db, service, repo):
        repo.email_exists.return_value = False
        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        with (
            patch("auth.services.user.User", return_value=mock_user),
            patch("auth.services.user.UserEmail"),
            patch("auth.services.user.UserPassword"),
            patch("auth.services.user.hash_password", return_value="hashed_pw"),
        ):
            result = await service.create_user(db, "new@example.com", "password123")

        assert result is mock_user
        repo.email_exists.assert_awaited_once_with(db, "new@example.com")
        repo.add.assert_awaited_once_with(db, mock_user)
        db.commit.assert_awaited_once()
        db.refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_on_existing_email(self, db, service, repo):
        repo.email_exists.return_value = True

        with pytest.raises(ValueError, match="Email already registered"):
            await service.create_user(db, "existing@example.com", "password123")

        repo.add.assert_not_awaited()
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_creates_profile_with_data(self, db, service, repo):
        repo.email_exists.return_value = False
        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        profile_data = {
            "given_name": "John",
            "family_name": "Doe",
            "nickname": "johnd",
        }

        with (
            patch("auth.services.user.User", return_value=mock_user),
            patch("auth.services.user.UserEmail"),
            patch("auth.services.user.UserPassword"),
            patch("auth.services.user.UserProfile") as MockProfile,
            patch("auth.services.user.hash_password", return_value="hashed_pw"),
        ):
            await service.create_user(db, "new@example.com", "password", profile_data=profile_data)

        MockProfile.assert_called_once()
        kwargs = MockProfile.call_args[1]
        assert kwargs["given_name"] == "John"
        assert kwargs["family_name"] == "Doe"
        assert kwargs["name"] == "John Doe"

    @pytest.mark.asyncio
    async def test_builds_full_name_from_parts(self, db, service, repo):
        repo.email_exists.return_value = False
        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        profile_data = {
            "given_name": "Jane",
            "middle_name": "Marie",
            "family_name": "Smith",
        }

        with (
            patch("auth.services.user.User", return_value=mock_user),
            patch("auth.services.user.UserEmail"),
            patch("auth.services.user.UserPassword"),
            patch("auth.services.user.UserProfile") as MockProfile,
            patch("auth.services.user.hash_password", return_value="hashed"),
        ):
            await service.create_user(db, "jane@example.com", "pw", profile_data=profile_data)

        assert MockProfile.call_args[1]["name"] == "Jane Marie Smith"

    @pytest.mark.asyncio
    async def test_builds_formatted_address(self, db, service, repo):
        repo.email_exists.return_value = False
        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        profile_data = {
            "address_street": "123 Main St",
            "address_locality": "Springfield",
            "address_country": "US",
        }

        with (
            patch("auth.services.user.User", return_value=mock_user),
            patch("auth.services.user.UserEmail"),
            patch("auth.services.user.UserPassword"),
            patch("auth.services.user.UserProfile") as MockProfile,
            patch("auth.services.user.hash_password", return_value="hashed"),
        ):
            await service.create_user(db, "addr@example.com", "pw", profile_data=profile_data)

        formatted = MockProfile.call_args[1]["address_formatted"]
        assert "123 Main St" in formatted
        assert "Springfield" in formatted

    @pytest.mark.asyncio
    async def test_auto_adds_tenant_member(self, db, service, repo):
        tenant_id = str(uuid.uuid4())
        mock_role = MagicMock()
        mock_role.id = uuid.uuid4()
        mock_role.name = "member"

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        repo.email_exists.return_value = False

        with (
            patch("auth.services.user.User", return_value=mock_user),
            patch("auth.services.user.UserEmail"),
            patch("auth.services.user.UserPassword"),
            patch("auth.services.user.TenantMember") as MockTenantMember,
            patch("auth.services.user.hash_password", return_value="hashed"),
            patch(
                "auth.services.user.tenant_role_service.resolve_default_registration_role",
                new_callable=AsyncMock,
                return_value=mock_role,
            ),
            patch(
                "auth.services.user.dispatch_webhook_event",
                new_callable=AsyncMock,
            ),
        ):
            await service.create_user(
                db, "tenant@example.com", "pw", registration_tenant_id=tenant_id
            )

        MockTenantMember.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_member_role_for_tenant(self, db, service, repo):
        tenant_id = str(uuid.uuid4())
        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        repo.email_exists.return_value = False

        with (
            patch("auth.services.user.User", return_value=mock_user),
            patch("auth.services.user.UserEmail"),
            patch("auth.services.user.UserPassword"),
            patch("auth.services.user.TenantMember") as MockTenantMember,
            patch("auth.services.user.hash_password", return_value="hashed"),
            patch(
                "auth.services.user.tenant_role_service.resolve_default_registration_role",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            await service.create_user(
                db, "norole@example.com", "pw", registration_tenant_id=tenant_id
            )

        MockTenantMember.assert_not_called()

    @pytest.mark.asyncio
    async def test_full_address_with_all_fields(self, db, service, repo):
        repo.email_exists.return_value = False
        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        profile_data = {
            "address_street": "123 Main St",
            "address_locality": "Springfield",
            "address_region": "IL",
            "address_postal_code": "62704",
            "address_country": "US",
        }

        with (
            patch("auth.services.user.User", return_value=mock_user),
            patch("auth.services.user.UserEmail"),
            patch("auth.services.user.UserPassword"),
            patch("auth.services.user.UserProfile") as MockProfile,
            patch("auth.services.user.hash_password", return_value="hashed"),
        ):
            await service.create_user(db, "full@example.com", "pw", profile_data=profile_data)

        formatted = MockProfile.call_args[1]["address_formatted"]
        assert "IL" in formatted
        assert "62704" in formatted
        assert "Springfield" in formatted

    @pytest.mark.asyncio
    async def test_profile_no_name_parts(self, db, service, repo):
        repo.email_exists.return_value = False
        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        profile_data = {"nickname": "ghost"}

        with (
            patch("auth.services.user.User", return_value=mock_user),
            patch("auth.services.user.UserEmail"),
            patch("auth.services.user.UserPassword"),
            patch("auth.services.user.UserProfile") as MockProfile,
            patch("auth.services.user.hash_password", return_value="hashed"),
        ):
            await service.create_user(db, "ghost@example.com", "pw", profile_data=profile_data)

        kwargs = MockProfile.call_args[1]
        assert kwargs["name"] is None
        assert kwargs["nickname"] == "ghost"


# ── set_active / delete ──────────────────────────────────────────────────────


class TestSetActive:
    @pytest.mark.asyncio
    async def test_activate(self, db, service):
        user = make_user(is_active=False)

        await service.set_active(db, user, active=True)

        assert user.is_active is True
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_deactivate(self, db, service):
        user = make_user(is_active=True)

        await service.set_active(db, user, active=False)

        assert user.is_active is False
        db.flush.assert_awaited_once()


class TestDelete:
    @pytest.mark.asyncio
    async def test_delegates_to_repo(self, db, service, repo):
        user = make_user()

        await service.delete(db, user)

        repo.delete.assert_awaited_once_with(db, user)


# ── default repository ───────────────────────────────────────────────────────


class TestDefaultRepo:
    def test_instantiates_default_repository(self):
        """A UserService without explicit repo gets a real UserRepository."""
        from auth.db.repositories.user import UserRepository

        svc = UserService()
        assert isinstance(svc._repo, UserRepository)


# Keep a shared helper for tests that still want to build a mock execute result.
_ = make_execute_result


class TestGetUserEmailRow:
    @pytest.mark.asyncio
    async def test_delegates_to_repository(self, db, repo, service):
        row = MagicMock()
        repo.find_user_email_row = AsyncMock(return_value=row)

        assert await service.get_user_email_row(db, "A@Example.com") is row
        repo.find_user_email_row.assert_awaited_once_with(db, "A@Example.com")


class TestCountUsers:
    @pytest.mark.asyncio
    async def test_forwards_filters(self, db, repo, service):
        from datetime import UTC, datetime

        repo.count = AsyncMock(return_value=9)
        since = datetime.now(UTC)

        assert await service.count(db, is_active=True, created_since=since) == 9
        repo.count.assert_awaited_once_with(db, is_active=True, created_since=since)

    @pytest.mark.asyncio
    async def test_defaults(self, db, repo, service):
        repo.count = AsyncMock(return_value=0)

        assert await service.count(db) == 0
        repo.count.assert_awaited_once_with(db, is_active=None, created_since=None)


class TestCreateAdminUser:
    @pytest.mark.asyncio
    async def test_duplicate_email_rejected(self, db, repo, service):
        repo.email_exists.return_value = True

        with pytest.raises(ValueError, match="Email already registered"):
            await service.create_admin_user(db, email="a@example.com", password="pw")

        repo.add.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_creates_user_email_and_password(self, db, repo, service):
        repo.email_exists.return_value = False

        user = await service.create_admin_user(
            db, email="Admin@Example.com", password="pw", is_verified=True
        )

        assert user.is_active is True
        added_email = repo.add_email.await_args[0][1]
        assert added_email.email == "admin@example.com"
        assert added_email.is_primary is True
        assert added_email.is_verified is True
        assert added_email.verified_at is not None
        repo.add_password.assert_awaited_once()
        repo.add_profile.assert_not_awaited()
        db.flush.assert_awaited_once()
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unverified_email_has_no_verified_at(self, db, repo, service):
        repo.email_exists.return_value = False

        await service.create_admin_user(db, email="a@example.com", password="pw")

        added_email = repo.add_email.await_args[0][1]
        assert added_email.is_verified is False
        assert added_email.verified_at is None

    @pytest.mark.asyncio
    async def test_name_creates_profile(self, db, repo, service):
        repo.email_exists.return_value = False

        await service.create_admin_user(db, email="a@example.com", password="pw", name="Ada")

        repo.add_profile.assert_awaited_once()
        assert repo.add_profile.await_args[0][1].name == "Ada"
