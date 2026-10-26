# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.repositories.jwk — JWKRepository (100% mocked)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.db.repositories.jwk import JWKRepository

from tests.conftest import make_execute_result, make_jwk


def make_scalars_result(rows: list) -> MagicMock:
    """Build a Result mock where ``.scalars().all()`` returns ``rows``."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    result.scalars.return_value = scalars
    return result


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def repo():
    return JWKRepository()


# ── find_by_id ───────────────────────────────────────────────────────────────


class TestFindById:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        jwk = make_jwk()
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=jwk))

        result = await repo.find_by_id(db, jwk.id)
        assert result is jwk

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_by_id(db, uuid.uuid4())
        assert result is None


# ── find_by_kid ──────────────────────────────────────────────────────────────


class TestFindByKid:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        jwk = make_jwk(kid="kid-1")
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=jwk))

        result = await repo.find_by_kid(db, "kid-1")
        assert result is jwk

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_by_kid(db, "missing")
        assert result is None


# ── find_active ──────────────────────────────────────────────────────────────


class TestFindActive:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        jwk = make_jwk(is_active=True)
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=jwk))

        result = await repo.find_active(db)
        assert result is jwk

    @pytest.mark.asyncio
    async def test_none_active(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_active(db)
        assert result is None


# ── list ─────────────────────────────────────────────────────────────────────


class TestList:
    @pytest.mark.asyncio
    async def test_default_excludes_revoked(self, db, repo):
        jwks = [make_jwk(), make_jwk()]
        db.execute = AsyncMock(return_value=make_scalars_result(jwks))

        result = await repo.list(db)
        assert result == jwks
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_include_revoked(self, db, repo):
        jwks = [make_jwk(), make_jwk()]
        db.execute = AsyncMock(return_value=make_scalars_result(jwks))

        result = await repo.list(db, include_revoked=True)
        assert result == jwks

    @pytest.mark.asyncio
    async def test_active_only(self, db, repo):
        jwks = [make_jwk(is_active=True)]
        db.execute = AsyncMock(return_value=make_scalars_result(jwks))

        result = await repo.list(db, active_only=True)
        assert result == jwks

    @pytest.mark.asyncio
    async def test_empty(self, db, repo):
        db.execute = AsyncMock(return_value=make_scalars_result([]))

        result = await repo.list(db)
        assert result == []


# ── deactivate_all / deactivate_active ───────────────────────────────────────


class TestDeactivate:
    @pytest.mark.asyncio
    async def test_deactivate_all_executes_update(self, db, repo):
        db.execute = AsyncMock()

        await repo.deactivate_all(db)
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_deactivate_active_executes_update(self, db, repo):
        db.execute = AsyncMock()

        await repo.deactivate_active(db)
        db.execute.assert_awaited_once()


# ── add / delete ─────────────────────────────────────────────────────────────


class TestAdd:
    @pytest.mark.asyncio
    async def test_adds_to_session(self, db, repo):
        jwk = make_jwk()

        await repo.add(db, jwk)

        db.add.assert_called_once_with(jwk)


class TestDelete:
    @pytest.mark.asyncio
    async def test_calls_db_delete(self, db, repo):
        jwk = make_jwk()
        db.delete = AsyncMock()

        await repo.delete(db, jwk)

        db.delete.assert_awaited_once_with(jwk)
