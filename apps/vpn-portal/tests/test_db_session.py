# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for vpn_portal.db.session."""

import importlib.util
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import vpn_portal.config
from vpn_portal.db import session as session_module


@pytest.fixture
def reload_session():
    """Execute a private copy of the session module with the given settings.

    The real module is left alone: other modules hold references to its ``get_db``.
    """

    def _reload(url: str, **overrides):
        values = {
            "database_url": url,
            "database_pool_size": 5,
            "database_max_overflow": 10,
            "database_echo": False,
        } | overrides
        spec = importlib.util.spec_from_file_location("session_probe", session_module.__file__)
        module = importlib.util.module_from_spec(spec)
        with patch.multiple(vpn_portal.config.settings, **values):
            spec.loader.exec_module(module)
        return module

    return _reload


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("postgresql://u:p@db/vpn", "postgresql+asyncpg://u:p@db/vpn"),
        ("postgres://u:p@db/vpn", "postgresql+asyncpg://u:p@db/vpn"),
        ("postgresql+asyncpg://u:p@db/vpn", "postgresql+asyncpg://u:p@db/vpn"),
    ],
)
def test_database_url_uses_the_asyncpg_driver(reload_session, url, expected):
    module = reload_session(url)

    assert module.database_url == expected
    assert module.engine.url.render_as_string(hide_password=False) == expected


def test_engine_uses_pool_settings(reload_session):
    module = reload_session("postgresql://db/vpn", database_pool_size=3, database_max_overflow=7)

    assert module.engine.pool.size() == 3
    assert module.engine.pool._max_overflow == 7


def test_engine_echo_follows_settings(reload_session):
    module = reload_session("postgresql://db/vpn", database_echo=True)

    assert module.engine.echo is True


async def test_get_db_yields_a_session_and_closes_it():
    fake_session = AsyncMock()
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=fake_session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch.object(session_module, "async_session_factory", factory):
        generator = session_module.get_db()
        yielded = await anext(generator)
        assert yielded is fake_session
        fake_session.close.assert_not_called()
        await generator.aclose()

    fake_session.close.assert_awaited_once()


def test_sessions_do_not_expire_on_commit():
    assert session_module.async_session_factory.kw["expire_on_commit"] is False
