# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment hooks for the in-process BDD scenarios.

Everything runs inside the test process: the FastAPI application is called
through an ASGI transport, so no server, PostgreSQL, Redis or network is
needed.

Token validation is faked: every bearer token used by the scenarios maps to
a set of claims registered in ``context.token_claims``.

The database is an in-memory SQLite engine that replaces the PostgreSQL one
(PostgreSQL ``JSONB`` columns are rendered as plain ``JSON``).
"""

import asyncio
import sys
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
from billing.auth.models import User
from billing.database import get_db
from billing.main import app
from billing.models import Base
from httpx import ASGITransport
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    """Render PostgreSQL JSONB columns as plain JSON on SQLite."""
    return "JSON"


DEFAULT_TOKEN = "bdd.mock.token"


def _create_test_user(scopes=None):
    """Create a test user with billing:* wildcard scope by default."""
    return User(
        id=uuid4(),
        email="bdd-test@example.com",
        name="BDD Test User",
        scopes=scopes or ["billing:*"],
        is_machine_client=False,
        client_id="bdd-test-client",
    )


def _create_jwt_claims(user):
    """Create JWT claims dict from a User instance."""
    return {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
        "scope": " ".join(user.scopes) if user.scopes else "",
        "client_id": user.client_id,
    }


def register_token(context, token, scopes):
    """Make the fake token validation accept ``token`` with the given scopes."""
    context.token_claims[token] = _create_jwt_claims(_create_test_user(scopes))


async def _create_schema(engine):
    """Create every table on the in-memory SQLite engine."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _cleanup_db(engine):
    """Empty all tables between scenarios for isolation."""
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(text(f"DELETE FROM {table.name}"))


async def _create_async_client(headers=None):
    """Create an httpx AsyncClient using ASGI transport."""
    return httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers=headers or {},
    )


# -- Behave hooks -------------------------------------------------------------


def before_all(context):
    """Set up the event loop, the fakes and the HTTP clients."""
    context.loop = asyncio.new_event_loop()
    asyncio.set_event_loop(context.loop)

    # Fake token validation: the claims come from the token registry.
    context.token_claims = {}
    register_token(context, DEFAULT_TOKEN, ["billing:*"])

    async def _validate(token):
        if token not in context.token_claims:
            raise ValueError("unknown token")
        return context.token_claims[token]

    mock_jwks = patch("billing.auth.dependencies.jwks_manager").start()
    mock_introspection = patch("billing.auth.dependencies.introspection_client").start()
    mock_jwks.is_configured = True
    mock_introspection.validate_token_with_introspection = AsyncMock(side_effect=_validate)
    mock_introspection.validate_opaque_token = AsyncMock(side_effect=_validate)
    context.register_token = lambda token, scopes: register_token(context, token, scopes)

    # In-memory SQLite database replacing PostgreSQL.
    context.engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    context.session_factory = async_sessionmaker(
        context.engine, class_=AsyncSession, expire_on_commit=False
    )
    context.loop.run_until_complete(_create_schema(context.engine))

    async def _override_get_db():
        async with context.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    # Modules that open their own sessions use the factory directly.
    for name, module in list(sys.modules.items()):
        if name.startswith("billing.") and hasattr(module, "async_session_factory"):
            patch.object(module, "async_session_factory", context.session_factory).start()

    context.anon_client = context.loop.run_until_complete(_create_async_client())
    context.client = context.loop.run_until_complete(
        _create_async_client(headers={"Authorization": f"Bearer {DEFAULT_TOKEN}"})
    )


def before_scenario(context, scenario):
    """Reset per-scenario state."""
    context.response = None
    context.created_ids = {}  # Track created entity IDs for cross-step reference


def after_scenario(context, scenario):
    """Clean up database after each scenario."""
    context.loop.run_until_complete(_cleanup_db(context.engine))


def after_all(context):
    """Tear down clients, patches and event loop."""
    context.loop.run_until_complete(context.anon_client.aclose())
    context.loop.run_until_complete(context.client.aclose())
    patch.stopall()
    app.dependency_overrides.clear()
    context.loop.run_until_complete(context.engine.dispose())
    context.loop.close()
