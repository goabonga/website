# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.repositories.profile — ProfileRepository (100% mocked)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.db.repositories.profile import ProfileRepository

from tests.conftest import make_execute_result


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def repo():
    return ProfileRepository()


def _make_profile(**kwargs):
    p = MagicMock()
    for k, v in kwargs.items():
        setattr(p, k, v)
    return p


# ── find_by_user_id ──────────────────────────────────────────────────────────


class TestFindByUserId:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        profile = _make_profile(nickname="nick")
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=profile))

        result = await repo.find_by_user_id(db, "user-id")

        assert result is profile
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_by_user_id(db, "user-id")

        assert result is None

    @pytest.mark.asyncio
    async def test_uses_string_user_id(self, db, repo):
        """ProfileRepository accepts string user IDs transparently."""
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_by_user_id(db, str(uuid.uuid4()))

        assert result is None
        db.execute.assert_awaited_once()


# ── add ──────────────────────────────────────────────────────────────────────


class TestAdd:
    @pytest.mark.asyncio
    async def test_adds_and_flushes(self, db, repo):
        profile = _make_profile()

        await repo.add(db, profile)

        db.add.assert_called_once_with(profile)
        db.flush.assert_awaited_once()


# ── stage ────────────────────────────────────────────────────────────────────


class TestStage:
    @pytest.mark.asyncio
    async def test_stages_without_flush(self, db, repo):
        profile = _make_profile()

        result = await repo.stage(db, profile)

        db.add.assert_called_once_with(profile)
        db.flush.assert_not_awaited()
        assert result is profile


# ── flush ────────────────────────────────────────────────────────────────────


class TestFlush:
    @pytest.mark.asyncio
    async def test_awaits_flush(self, db, repo):
        await repo.flush(db)

        db.flush.assert_awaited_once()
