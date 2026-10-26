# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Shared pytest fixtures."""

from collections.abc import Iterator

import pytest
from apt_server.main import app
from fastapi.testclient import TestClient


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
