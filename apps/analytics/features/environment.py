# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Behave environment: scenarios run in-process, without external infrastructure.

The application talks to a temporary SQLite database through aiosqlite instead of
PostgreSQL. The PostgreSQL-only column types (JSONB, INET) are rendered as JSON and
VARCHAR for SQLite.
"""

import asyncio
import os
import tempfile

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.ext.compiler import compiles


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(element, compiler, **kw):
    return "JSON"


@compiles(INET, "sqlite")
def _compile_inet_for_sqlite(element, compiler, **kw):
    return "VARCHAR(45)"


# Settings are resolved when the application modules are imported, which happens
# when behave loads the step definitions: configure the environment first.
_tmpdir = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmpdir.name}/analytics.db"


def before_all(context):
    """Create the event loop, the temporary database and load the ASGI application."""

    context.loop = asyncio.new_event_loop()
    asyncio.set_event_loop(context.loop)

    from analytics.main import app

    context.app = app

    from analytics.database import async_session_maker, engine
    from analytics.models import Base

    context.engine = engine
    context.session_maker = async_session_maker

    async def create_schema():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    context.loop.run_until_complete(create_schema())


def after_all(context):
    """Dispose of the engine, the loop and the temporary database."""
    context.loop.run_until_complete(context.engine.dispose())
    context.loop.close()
    _tmpdir.cleanup()


def before_scenario(context, scenario):
    """Reset the per-scenario state."""
    context.response = None
    context.response_json = None
    context.request_headers = {}

    from analytics.models import Base

    async def clean_tables():
        async with context.engine.begin() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                await conn.execute(text(f"DELETE FROM {table.name}"))

    context.loop.run_until_complete(clean_tables())
