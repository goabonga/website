# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.api.routes.api.users — admin user management endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

MODULE = "auth.api.routes.api.users"


def _make_user(is_active=True, primary=True, with_profile=True):
    """Build a mock User with the fields UserResponse reads."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_active = is_active
    user.created_at = datetime.now(UTC)
    user.updated_at = datetime.now(UTC)
    user.registration_source = "admin"

    email = MagicMock()
    email.email = "user@example.com"
    email.is_primary = primary
    email.is_verified = True
    user.emails = [email]

    if with_profile:
        profile = MagicMock()
        profile.name = "Test User"
        profile.given_name = "Test"
        profile.family_name = "User"
        profile.nickname = "tester"
        user.profile = profile
    else:
        user.profile = None

    return user


def _admin():
    admin = MagicMock()
    admin.id = uuid.uuid4()
    return admin


class TestUserToResponse:
    def test_non_primary_email_is_skipped(self):
        from auth.api.routes.api.users import _user_to_response

        user = _make_user(primary=False)

        assert _user_to_response(user).email == ""

    def test_primary_email_is_used(self):
        from auth.api.routes.api.users import _user_to_response

        assert _user_to_response(_make_user()).email == "user@example.com"


class TestCreateUser:
    def _body(self, **overrides):
        from auth.api.schemas.api.users import CreateUserRequest

        payload = {"email": "alice@example.com", "password": "s3cr3t!Passw0rd", "is_active": True}
        payload.update(overrides)
        return CreateUserRequest(**payload)

    @pytest.mark.asyncio
    async def test_duplicate_email_is_a_409(self):
        from auth.api.routes.api.users import create_user

        with (
            patch(f"{MODULE}._user_service.email_exists", AsyncMock(return_value=True)),
            pytest.raises(HTTPException) as exc,
        ):
            await create_user(self._body(), AsyncMock(), _admin())

        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_active_user_is_created(self):
        from auth.api.routes.api.users import create_user

        created = _make_user()

        with (
            patch(f"{MODULE}._user_service.email_exists", AsyncMock(return_value=False)),
            patch(f"{MODULE}._user_service.create_user", AsyncMock(return_value=created)),
            patch(f"{MODULE}._user_service.set_active", AsyncMock()) as set_active,
            patch(f"{MODULE}._user_service.get_by_id", AsyncMock(return_value=created)),
        ):
            result = await create_user(self._body(), AsyncMock(), _admin())

        assert result.email == "user@example.com"
        set_active.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_inactive_flag_disables_the_new_user(self):
        from auth.api.routes.api.users import create_user

        created = _make_user(is_active=False)

        with (
            patch(f"{MODULE}._user_service.email_exists", AsyncMock(return_value=False)),
            patch(f"{MODULE}._user_service.create_user", AsyncMock(return_value=created)),
            patch(f"{MODULE}._user_service.set_active", AsyncMock()) as set_active,
            patch(f"{MODULE}._user_service.get_by_id", AsyncMock(return_value=created)),
        ):
            await create_user(self._body(is_active=False), AsyncMock(), _admin())

        set_active.assert_awaited_once()
        assert set_active.await_args.kwargs["active"] is False


class TestDeleteUser:
    @pytest.mark.asyncio
    async def test_delegates_to_service(self):
        from auth.api.routes.api.users import delete_user

        target = _make_user()
        db = AsyncMock()

        with (
            patch(f"{MODULE}._user_service.get_by_id", AsyncMock(return_value=target)),
            patch(f"{MODULE}._user_service.delete", AsyncMock()) as delete,
        ):
            assert await delete_user(target.id, db, _admin()) is None

        delete.assert_awaited_once_with(db, target)

    @pytest.mark.asyncio
    async def test_missing_raises_404(self):
        from auth.api.routes.api.users import delete_user

        with (
            patch(f"{MODULE}._user_service.get_by_id", AsyncMock(return_value=None)),
            pytest.raises(HTTPException) as exc,
        ):
            await delete_user(uuid.uuid4(), AsyncMock(), _admin())

        assert exc.value.status_code == 404


class TestDisableUser:
    @pytest.mark.asyncio
    async def test_active_user_is_disabled(self):
        from auth.api.routes.api.users import disable_user

        target = _make_user(is_active=True)

        with (
            patch(f"{MODULE}._user_service.get_by_id", AsyncMock(return_value=target)),
            patch(f"{MODULE}._user_service.set_active", AsyncMock()) as set_active,
        ):
            result = await disable_user(target.id, AsyncMock(), _admin())

        assert result.id == target.id
        assert set_active.await_args.kwargs["active"] is False

    @pytest.mark.asyncio
    async def test_already_disabled_is_a_400(self):
        from auth.api.routes.api.users import disable_user

        target = _make_user(is_active=False)

        with (
            patch(f"{MODULE}._user_service.get_by_id", AsyncMock(return_value=target)),
            pytest.raises(HTTPException) as exc,
        ):
            await disable_user(target.id, AsyncMock(), _admin())

        assert exc.value.status_code == 400
        assert "already disabled" in exc.value.detail


class TestEnableUser:
    @pytest.mark.asyncio
    async def test_disabled_user_is_enabled(self):
        from auth.api.routes.api.users import enable_user

        target = _make_user(is_active=False)

        with (
            patch(f"{MODULE}._user_service.get_by_id", AsyncMock(return_value=target)),
            patch(f"{MODULE}._user_service.set_active", AsyncMock()) as set_active,
        ):
            result = await enable_user(target.id, AsyncMock(), _admin())

        assert result.id == target.id
        assert set_active.await_args.kwargs["active"] is True

    @pytest.mark.asyncio
    async def test_already_active_is_a_400(self):
        from auth.api.routes.api.users import enable_user

        target = _make_user(is_active=True)

        with (
            patch(f"{MODULE}._user_service.get_by_id", AsyncMock(return_value=target)),
            pytest.raises(HTTPException) as exc,
        ):
            await enable_user(target.id, AsyncMock(), _admin())

        assert exc.value.status_code == 400
        assert "already active" in exc.value.detail
