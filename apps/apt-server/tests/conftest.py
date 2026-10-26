# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Shared pytest fixtures."""

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from apt_server.db.models import Base
from apt_server.main import app
from fastapi.testclient import TestClient
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import NullPool


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(type_, compiler, **kw) -> str:
    """Let the PostgreSQL models run on the in-process SQLite test database."""
    return "JSON"


@pytest.fixture
def client() -> Iterator[TestClient]:
    """In-process HTTP client bound to the ASGI application."""
    with TestClient(app) as test_client:
        yield test_client


ISSUER = "https://issuer.example"


@pytest.fixture
def oidc_settings(monkeypatch: pytest.MonkeyPatch):
    """Configure the OAuth2 settings used by the auth clients."""
    from apt_server.auth.jwks import jwks_manager
    from apt_server.config import settings

    monkeypatch.setattr(settings, "oauth2_issuer", ISSUER)
    monkeypatch.setattr(settings, "oauth2_client_id", "apt-client")
    monkeypatch.setattr(settings, "oauth2_client_secret", "apt-secret")
    monkeypatch.setattr(settings, "oauth2_trusted_issuers", "")
    monkeypatch.setattr(settings, "redis_url", "")
    monkeypatch.setattr(jwks_manager, "_issuer_config", None)
    return settings


class FakeRedis:
    """Minimal async stand-in for ``redis.asyncio.Redis``."""

    def __init__(self, fail: bool = False) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.fail = fail
        self.closed = False

    async def get(self, key: str) -> str | None:
        if self.fail:
            raise ConnectionError("redis down")
        return self.store.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        if self.fail:
            raise ConnectionError("redis down")
        self.store[key] = value
        self.ttls[key] = ttl

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def failing_redis() -> FakeRedis:
    return FakeRedis(fail=True)


@pytest_asyncio.fixture
async def session_maker(tmp_path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Session factory bound to a throw-away SQLite database with the schema created."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}", poolclass=NullPool)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


@pytest_asyncio.fixture
async def db(session_maker) -> AsyncIterator[AsyncSession]:
    async with session_maker() as session:
        yield session
