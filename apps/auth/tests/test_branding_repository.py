# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.db.repositories.branding — BrandingRepository (100% mocked)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth.db.repositories.branding import BrandingRepository

from tests.conftest import make_execute_result


@pytest.fixture
def db():
    session = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def repo():
    return BrandingRepository()


def _mock(**kwargs):
    m = MagicMock()
    for k, v in kwargs.items():
        setattr(m, k, v)
    return m


# ── find_tenant_with_branding ────────────────────────────────────────────────


class TestFindTenantWithBranding:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        tenant = _mock(id=uuid.uuid4(), branding=None)
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=tenant))

        result = await repo.find_tenant_with_branding(db, tenant.id)

        assert result is tenant

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_tenant_with_branding(db, uuid.uuid4())

        assert result is None


# ── find_branding ────────────────────────────────────────────────────────────


class TestFindBranding:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        branding = _mock(primary_color="#ff0000")
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=branding))

        result = await repo.find_branding(db, uuid.uuid4())

        assert result is branding

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_branding(db, uuid.uuid4())

        assert result is None


# ── find_active_template ─────────────────────────────────────────────────────


class TestFindActiveTemplate:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        template = _mock(content="<h1>override</h1>")
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=template))

        result = await repo.find_active_template(db, uuid.uuid4(), "auth/login.html")

        assert result is template

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_active_template(db, uuid.uuid4(), "missing.html")

        assert result is None


# ── find_template ────────────────────────────────────────────────────────────


class TestFindTemplate:
    @pytest.mark.asyncio
    async def test_found(self, db, repo):
        template = _mock(is_active=False)
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=template))

        result = await repo.find_template(db, uuid.uuid4(), "auth/login.html")

        assert result is template

    @pytest.mark.asyncio
    async def test_not_found(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalar_value=None))

        result = await repo.find_template(db, uuid.uuid4(), "missing.html")

        assert result is None


# ── list_templates ───────────────────────────────────────────────────────────


class TestListTemplates:
    @pytest.mark.asyncio
    async def test_returns_list(self, db, repo):
        rows = [_mock(), _mock()]
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=rows))

        result = await repo.list_templates(db, uuid.uuid4())

        assert result == rows

    @pytest.mark.asyncio
    async def test_empty(self, db, repo):
        db.execute = AsyncMock(return_value=make_execute_result(scalars_list=[]))

        result = await repo.list_templates(db, uuid.uuid4())

        assert result == []


# ── add / delete / flush ─────────────────────────────────────────────────────


class TestAdd:
    @pytest.mark.asyncio
    async def test_adds_and_flushes(self, db, repo):
        branding = _mock()

        await repo.add(db, branding)

        db.add.assert_called_once_with(branding)
        db.flush.assert_awaited_once()


class TestDelete:
    @pytest.mark.asyncio
    async def test_deletes_and_flushes(self, db, repo):
        branding = _mock()
        db.delete = AsyncMock()

        await repo.delete(db, branding)

        db.delete.assert_awaited_once_with(branding)
        db.flush.assert_awaited_once()


class TestFlush:
    @pytest.mark.asyncio
    async def test_awaits_flush(self, db, repo):
        await repo.flush(db)

        db.flush.assert_awaited_once()
