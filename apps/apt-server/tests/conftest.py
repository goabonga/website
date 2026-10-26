# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Shared pytest fixtures."""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from apt_server.database import get_db
from apt_server.db.models import Base
from apt_server.main import app
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import NullPool


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(type_, compiler, **kw) -> str:
    """Let the PostgreSQL models run on the in-process SQLite test database."""
    return "JSON"


def _make_datetimes_aware(target, *_args) -> None:
    """SQLite drops time zones; PostgreSQL returns aware datetimes, so mimic it."""
    for key, value in list(target.__dict__.items()):
        if isinstance(value, datetime) and value.tzinfo is None:
            target.__dict__[key] = value.replace(tzinfo=UTC)


event.listen(Base, "load", _make_datetimes_aware, propagate=True)
event.listen(Base, "refresh", _make_datetimes_aware, propagate=True)


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


@pytest_asyncio.fixture
async def http(session_maker) -> AsyncIterator[AsyncClient]:
    """Async HTTP client on the application, wired to the SQLite test database."""

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def repo_root(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Point the APT repository at an empty temporary directory."""
    from apt_server.config import settings

    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setattr(settings, "apt_repo_root", str(root))
    monkeypatch.setattr(settings, "apt_components", "main,private")
    monkeypatch.setattr(settings, "apt_public_components", "main")
    monkeypatch.setattr(settings, "apt_architectures", "amd64")
    monkeypatch.setattr(settings, "apt_suites", "stable")
    return root


@pytest.fixture
def login():
    """Act as a given user on the bearer protected API."""
    from apt_server.auth.dependencies import AuthContext, get_auth_context
    from apt_server.auth.models import User

    def as_user(sub: str, scopes: list[str], email: str | None = None) -> None:
        user = User(id=sub, scopes=scopes, email=email)
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(user)

    yield as_user
    app.dependency_overrides.pop(get_auth_context, None)


@pytest.fixture
def login_caller():
    """Act as an apt ``Caller`` on routes using the Basic or Bearer or session resolver."""
    from apt_server.acl.packages import Caller
    from apt_server.services.apt_auth import resolve_caller

    def as_caller(sub: str | None, scopes: list[str] | None = None, **extra) -> None:
        caller = None if sub is None else Caller(sub=sub, scopes=frozenset(scopes or []), **extra)
        app.dependency_overrides[resolve_caller] = lambda: caller

    yield as_caller
    app.dependency_overrides.pop(resolve_caller, None)
