# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit test fixtures using only unittest.mock. No real database."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest


def _make_result(
    scalar_one_or_none=None,
    scalar=0,
    scalars_all=None,
    rowcount=0,
):
    """Create a mock SQLAlchemy Result object."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_one_or_none
    result.scalar.return_value = scalar
    result.scalars.return_value.all.return_value = scalars_all or []
    result.rowcount = rowcount
    return result


@pytest.fixture
def mock_db():
    """Mock AsyncSession. Default execute returns None/0/[]."""
    db = MagicMock()
    db.execute = AsyncMock(return_value=_make_result())
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    db.delete = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def make_result():
    """Factory fixture to create mock results for db.execute()."""
    return _make_result


@pytest.fixture
def user_id() -> UUID:
    return UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


@pytest.fixture
def other_user_id() -> UUID:
    return UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest.fixture
def org_id() -> UUID:
    return UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


@pytest.fixture
def tenant_id() -> UUID:
    return UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
