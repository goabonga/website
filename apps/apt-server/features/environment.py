# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment: scenarios drive the ASGI application in-process.

Scenarios tagged ``@database`` get a throw-away SQLite database holding the
real schema, injected in place of the PostgreSQL session dependency.
"""

import asyncio
import shutil
import tempfile
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

from apt_server.database import get_db
from apt_server.db.models import Base
from apt_server.main import app
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import NullPool


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(type_, compiler, **kw):
    return "JSON"


def _make_datetimes_aware(target, *_args) -> None:
    """SQLite drops time zones; PostgreSQL returns aware datetimes, so mimic it."""
    for key, value in list(target.__dict__.items()):
        if isinstance(value, datetime) and value.tzinfo is None:
            target.__dict__[key] = value.replace(tzinfo=UTC)


event.listen(Base, "load", _make_datetimes_aware, propagate=True)
event.listen(Base, "refresh", _make_datetimes_aware, propagate=True)


def _setup_database(context):
    context.workdir = Path(tempfile.mkdtemp(prefix="apt-server-behave-"))
    context.engine = create_async_engine(
        f"sqlite+aiosqlite:///{context.workdir / 'test.db'}", poolclass=NullPool
    )

    async def create_schema():
        async with context.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(create_schema())
    context.session_maker = async_sessionmaker(
        context.engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db():
        async with context.session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    def run_db(coroutine_function):
        """Run ``coroutine_function(session)`` against the scenario database."""

        async def runner():
            async with context.session_maker() as session:
                return await coroutine_function(session)

        return asyncio.run(runner())

    context.run_db = run_db


def before_scenario(context, scenario):
    context.stack = ExitStack()
    context.patch = lambda target, name, value: context.stack.enter_context(
        mock.patch.object(target, name, value)
    )
    context.uses_database = "database" in scenario.effective_tags
    if context.uses_database:
        _setup_database(context)
    context.client = TestClient(app)
    context.response = None


def after_scenario(context, scenario):
    context.client.close()
    context.stack.close()
    app.dependency_overrides.clear()
    if context.uses_database:
        asyncio.run(context.engine.dispose())
        shutil.rmtree(context.workdir, ignore_errors=True)
