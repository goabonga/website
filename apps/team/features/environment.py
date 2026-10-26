# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave hooks.

Every scenario gets its own in-process application: the ASGI app is driven by
a test client, the database is an in-memory SQLite database created from the
SQLAlchemy models, and the authentication clients are replaced by fakes that
answer with the claims the scenario declares. Nothing leaves the process.
"""

import logging
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import JSON, String, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from team.database import get_db
from team.main import app
from team.models import Base


class SqliteUUID(TypeDecorator):
    """UUID stored as text, accepting both strings and UUID objects."""

    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else str(uuid.UUID(str(value)))

    def process_result_value(self, value, dialect):
        return None if value is None else uuid.UUID(value)


def use_sqlite_types() -> None:
    """Swap the PostgreSQL-only column types of the models for SQLite ones (idempotent)."""
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, UUID):
                column.type = SqliteUUID()
            elif isinstance(column.type, JSONB) or type(column.type).__name__ == "Vector":
                column.type = JSON()


def before_all(context) -> None:
    use_sqlite_types()


def before_scenario(context, scenario) -> None:
    context.response = None
    context.vars = {}
    context.claims = None
    context.environ = {}
    context.settings = None
    context.streams = None
    context._client = None
    root = logging.getLogger()
    context._root_state = (list(root.handlers), root.level)

    context.engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    context.session_factory = async_sessionmaker(context.engine, expire_on_commit=False)

    async def override_get_db():
        async with context.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    _patch_authentication(context)
    context.get_client = lambda: get_client(context)
    context.run = lambda func, *args: get_client(context).portal.call(func, *args)


def _patch_authentication(context) -> None:
    """Replace the authentication clients: the claims come from the scenario."""

    async def claims(token: str) -> dict:
        return context.claims

    jwks = MagicMock(is_configured=True)
    introspection = MagicMock()
    introspection.validate_token_with_introspection = AsyncMock(side_effect=claims)
    introspection.validate_opaque_token = AsyncMock(side_effect=claims)
    exchange = MagicMock(is_configured=False)
    for name, fake in (
        ("jwks_manager", jwks),
        ("introspection_client", introspection),
        ("token_exchange_client", exchange),
    ):
        patcher = patch(f"team.auth.dependencies.{name}", fake)
        patcher.start()
        context.add_cleanup(patcher.stop)


def get_client(context) -> TestClient:
    """Return the client of the scenario; the schema is created on first use."""
    if context._client is None:
        client = TestClient(app)
        client.__enter__()

        async def create_schema() -> None:
            async with context.engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

        client.portal.call(create_schema)
        context._client = client
    return context._client


def after_scenario(context, scenario) -> None:
    app.dependency_overrides.clear()
    if context._client is not None:
        context._client.__exit__(None, None, None)
    root = logging.getLogger()
    root.handlers[:] = context._root_state[0]
    root.setLevel(context._root_state[1])
