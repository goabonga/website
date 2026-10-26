# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""SQLite stand-in for the PostgreSQL database, used by the browser scenarios.

A real browser follows redirects, posts forms and loads pages whose queries join several
tables, which the mock sessions of the in-process scenarios do not evaluate. The browser
scenarios therefore run the real SQLAlchemy models and queries on a SQLite file created for
the scenario:

- the PostgreSQL column types (``JSONB``, ``UUID``, pgvector ``Vector``) are rendered as
  ``JSON``, ``CHAR(32)`` and ``TEXT`` for SQLite;
- foreign keys are enforced, so ``ON DELETE CASCADE`` behaves as it does in production;
- datetimes come back timezone-aware (UTC), as they do from PostgreSQL;
- the pgvector distance operators do not exist in SQLite, so the search page is served by an
  in-Python ranking (see ``browser_web_search_steps``).

The application uses an asynchronous session per request, created from the file; the
scenario steps use a synchronous session on the same file to prepare and to check data.
"""

import shutil
import tempfile
from collections.abc import AsyncGenerator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from pgvector.sqlalchemy import Vector
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from knowledge.models import Base


@compiles(JSONB, "sqlite")
def _jsonb_as_json(type_, compiler, **kwargs):
    return "JSON"


@compiles(PG_UUID, "sqlite")
def _uuid_as_char(type_, compiler, **kwargs):
    return "CHAR(32)"


@compiles(Vector, "sqlite")
def _vector_as_text(type_, compiler, **kwargs):
    return "TEXT"


def _aware(value):
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


@event.listens_for(Base, "load", propagate=True)
@event.listens_for(Base, "refresh", propagate=True)
def _restore_timezones(target, *args):
    """SQLite drops the timezone of datetimes; the models store UTC."""
    for name, value in list(vars(target).items()):
        if isinstance(value, datetime) and value.tzinfo is None:
            target.__dict__[name] = _aware(value)


def _enforce_foreign_keys(connection, record):
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class Database:
    """One SQLite file with the application schema."""

    def __init__(self):
        self.directory = Path(tempfile.mkdtemp(prefix="knowledge-browser-"))
        path = self.directory / "knowledge.sqlite"
        self.sync_engine = create_engine(f"sqlite:///{path}", poolclass=NullPool)
        self.async_engine = create_async_engine(f"sqlite+aiosqlite:///{path}", poolclass=NullPool)
        event.listen(self.sync_engine, "connect", _enforce_foreign_keys)
        event.listen(self.async_engine.sync_engine, "connect", _enforce_foreign_keys)
        Base.metadata.create_all(self.sync_engine)
        self._async_sessions = async_sessionmaker(
            self.async_engine, class_=AsyncSession, expire_on_commit=False
        )
        self._sessions = sessionmaker(self.sync_engine, class_=Session, expire_on_commit=False)

    async def dependency(self) -> AsyncGenerator[AsyncSession, None]:
        """Replacement of ``knowledge.database.get_db``: one session per request."""
        async with self._async_sessions() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    @contextmanager
    def session(self):
        """A synchronous session to prepare or to check data; commits on exit."""
        with self._sessions() as session:
            yield session
            session.commit()

    def dispose(self):
        self.sync_engine.dispose()
        shutil.rmtree(self.directory, ignore_errors=True)
