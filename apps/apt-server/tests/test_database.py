# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Database URL handling and the session dependency."""

import pytest
from apt_server import database


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("postgresql://u@h/db", "postgresql+asyncpg://u@h/db"),
        ("postgres://u@h/db", "postgresql+asyncpg://u@h/db"),
        ("postgresql+asyncpg://u@h/db", "postgresql+asyncpg://u@h/db"),
        ("sqlite+aiosqlite:///x.db", "sqlite+aiosqlite:///x.db"),
    ],
)
def test_async_database_url(url: str, expected: str) -> None:
    assert database.get_async_database_url(url) == expected


async def test_get_db_yields_a_session_and_closes_it(monkeypatch, session_maker) -> None:
    monkeypatch.setattr(database, "async_session_maker", session_maker)

    generator = database.get_db()
    session = await anext(generator)
    assert session.is_active

    with pytest.raises(StopAsyncIteration):
        await anext(generator)


def test_engine_uses_the_asyncpg_driver_by_default() -> None:
    assert database.engine.url.drivername == "postgresql+asyncpg"
