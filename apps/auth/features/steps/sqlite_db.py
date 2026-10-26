# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""A throw-away SQLite database that stands in for PostgreSQL in the scenarios.

The models use a few PostgreSQL-only features (``ARRAY`` and ``JSONB`` types,
partial indexes, the array operators) and timezone aware timestamps. ``adapt_metadata`` swaps them
for SQLite friendly equivalents, ``create_database`` builds the schema, and ``AsyncSessionAdapter``
exposes the ``AsyncSession`` methods used by the repositories on top of a
synchronous session, so the real repositories, services and routes run
unchanged against it.
"""

import json
import os
import shutil
import sys
import tempfile
import uuid
from contextlib import contextmanager
from datetime import UTC
from unittest.mock import patch

from sqlalchemy import CHAR, JSON, DateTime, Uuid, create_engine, event, func, text, type_coerce
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.types import TypeDecorator


class JSONArray(TypeDecorator):
    """A list stored as JSON, with the ``overlap`` and ``contains`` operators of ``ARRAY``."""

    impl = JSON
    cache_ok = True

    class comparator_factory(JSON.Comparator):
        def overlap(self, other):
            return func.json_overlap(self.expr, type_coerce(other, JSON)) == 1

        def contains(self, other, **kwargs):
            return func.json_contains_all(self.expr, type_coerce(other, JSON)) == 1


def _register_sqlite_functions(dbapi_connection, connection_record):
    """SQL functions backing the array operators of ``JSONArray``."""
    dbapi_connection.create_function(
        "json_overlap", 2, lambda a, b: int(bool(set(json.loads(a)) & set(json.loads(b))))
    )
    dbapi_connection.create_function(
        "json_contains_all", 2, lambda a, b: int(set(json.loads(b)) <= set(json.loads(a)))
    )


class UTCDateTime(TypeDecorator):
    """Timezone aware timestamps stored as naive UTC, as SQLite has no timezone support."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(UTC).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value


class LenientUuid(TypeDecorator):
    """UUIDs stored as 32 hex digits that also accept their string form, as PostgreSQL does."""

    impl = CHAR(32)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return (value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))).hex

    def process_result_value(self, value, dialect):
        return None if value is None else uuid.UUID(value)


def adapt_metadata(metadata):
    """Swap the PostgreSQL-only column types for SQLite friendly ones (idempotent)."""
    for table in metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, ARRAY):
                column.type = JSONArray()
            elif isinstance(column.type, JSONB):
                column.type = JSON()
            elif isinstance(column.type, Uuid) and not isinstance(column.type, LenientUuid):
                column.type = LenientUuid()
            elif isinstance(column.type, DateTime) and not isinstance(column.type, UTCDateTime):
                column.type = UTCDateTime()
        for index in table.indexes:
            # PostgreSQL partial indexes are partial on SQLite too.
            where = index.dialect_options["postgresql"]["where"]
            if where is not None and index.dialect_options["sqlite"]["where"] is None:
                index.dialect_options["sqlite"]["where"] = text(str(where))


class AsyncSessionAdapter:
    """The subset of ``AsyncSession`` used by the repositories, over a sync ``Session``."""

    def __init__(self, session: Session):
        self.sync_session = session

    def add(self, obj):
        self.sync_session.add(obj)

    def add_all(self, objs):
        self.sync_session.add_all(objs)

    async def execute(self, *args, **kwargs):
        return self.sync_session.execute(*args, **kwargs)

    async def scalar(self, *args, **kwargs):
        return self.sync_session.scalar(*args, **kwargs)

    async def scalars(self, *args, **kwargs):
        return self.sync_session.scalars(*args, **kwargs)

    async def get(self, *args, **kwargs):
        return self.sync_session.get(*args, **kwargs)

    async def flush(self, *args):
        self.sync_session.flush(*args)

    async def commit(self):
        self.sync_session.commit()

    async def rollback(self):
        self.sync_session.rollback()

    async def refresh(self, obj, attribute_names=None, **kwargs):
        self.sync_session.refresh(obj, attribute_names)

    async def delete(self, obj):
        self.sync_session.delete(obj)

    async def merge(self, obj):
        return self.sync_session.merge(obj)

    async def close(self):
        self.sync_session.close()

    def expunge(self, obj):
        self.sync_session.expunge(obj)

    def __getattr__(self, name):
        return getattr(self.sync_session, name)


def _adapt_models_once():
    """Adapt the metadata before any mapper is configured or any statement compiled."""
    import auth.db.models  # noqa: F401
    from auth.db.base import Base

    adapt_metadata(Base.metadata)


_adapt_models_once()


class _SessionContext:
    """Async context manager returned by the patched ``async_session_factory``."""

    def __init__(self, database):
        self._database = database

    async def __aenter__(self):
        self._session = self._database.new_session()
        return self._session

    async def __aexit__(self, *exc):
        await self._session.close()
        return False


_TEMPLATE = {}


def _template_path():
    """Build, once per process, a database file holding the empty schema."""
    if "path" not in _TEMPLATE:
        from auth.db.base import Base

        directory = tempfile.mkdtemp(prefix="auth-db-template-")
        path = os.path.join(directory, "template.sqlite")
        engine = create_engine(f"sqlite:///{path}")
        Base.metadata.create_all(engine)
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA journal_mode=WAL")
        engine.dispose()
        _TEMPLATE["path"] = path
    return _TEMPLATE["path"]


class Database:
    """A database file for one scenario.

    Every application session gets its own connection, as with PostgreSQL, so
    that a session which is closed or rolled back cannot undo the work of
    another one. The steps use a separate auto-commit session: what they write is
    immediately visible to the application and what the application committed is
    visible to their assertions.
    """

    def __init__(self):
        self.directory = tempfile.mkdtemp(prefix="auth-db-")
        path = os.path.join(self.directory, "auth.sqlite")
        shutil.copyfile(_template_path(), path)
        url = f"sqlite:///{path}"
        connect_args = {"check_same_thread": False}
        self.engine = create_engine(url, connect_args=connect_args)
        self._step_engine = create_engine(
            url, connect_args=connect_args, isolation_level="AUTOCOMMIT"
        )
        for engine in (self.engine, self._step_engine):
            event.listen(engine, "connect", _register_sqlite_functions)
        self._factory = sessionmaker(self.engine, expire_on_commit=False, autoflush=False)
        self._step_session = sessionmaker(
            self._step_engine, expire_on_commit=False, autoflush=False
        )()
        # The async-looking session used by the steps themselves (fixtures and services).
        self.session = AsyncSessionAdapter(self._step_session)

    @property
    def sync_session(self):
        """The steps' session, with nothing cached so that it sees the committed state."""
        self._step_session.expire_all()
        return self._step_session

    def commit(self):
        """Persist the changes made through ``sync_session`` (it never caches them)."""
        self._step_session.commit()

    def new_session(self):
        """A fresh session, as each request or background job gets in the application."""
        return AsyncSessionAdapter(self._factory())

    def dispose(self):
        self._step_session.close()
        self._step_engine.dispose()
        self.engine.dispose()
        shutil.rmtree(self.directory, ignore_errors=True)

    @contextmanager
    def sync_db(self):
        """Replacement of ``get_sync_db`` for Celery tasks."""
        session = self._factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def use_database(context):
    """Route the application and the background code of the scenario to a fresh database."""
    if getattr(context, "database", None) is not None:
        return context.database
    database = Database()
    context.database = database
    context.db = database.session

    async def override_get_db():
        session = database.new_session()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    context.app.dependency_overrides[context.get_db] = override_get_db

    patchers = []
    for name, module in list(sys.modules.items()):
        if not name.startswith("auth.") or module is None:
            continue
        if hasattr(module, "async_session_factory"):
            patchers.append(
                patch.object(module, "async_session_factory", lambda: _SessionContext(database))
            )
        if hasattr(module, "get_sync_db"):
            patchers.append(patch.object(module, "get_sync_db", database.sync_db))
    for patcher in patchers:
        patcher.start()
        context.add_cleanup(patcher.stop)
    context.add_cleanup(database.dispose)
    return database
