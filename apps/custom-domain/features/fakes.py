# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""In-memory stand-ins for the infrastructure the service talks to.

The SQLAlchemy models target PostgreSQL. For the behave scenarios they are created in an
in-memory SQLite database instead, so no server is needed. ``AsyncSessionShim`` exposes the
subset of the ``AsyncSession`` API the application uses on top of a synchronous session.
"""

from contextlib import contextmanager

from custom_domain.database import get_db
from custom_domain.models import Base
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(type_, compiler, **kw):
    return "JSON"


class AsyncSessionShim:
    """Minimal async facade over a synchronous SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, instance) -> None:
        self._session.add(instance)

    async def execute(self, *args, **kwargs):
        return self._session.execute(*args, **kwargs)

    async def scalar(self, *args, **kwargs):
        return self._session.scalar(*args, **kwargs)

    async def scalars(self, *args, **kwargs):
        return self._session.scalars(*args, **kwargs)

    async def get(self, *args, **kwargs):
        return self._session.get(*args, **kwargs)

    async def commit(self) -> None:
        self._session.commit()

    async def flush(self) -> None:
        self._session.flush()

    async def rollback(self) -> None:
        self._session.rollback()

    async def refresh(self, instance) -> None:
        self._session.refresh(instance)

    async def delete(self, instance) -> None:
        self._session.delete(instance)

    async def close(self) -> None:
        self._session.close()


class FakeDatabase:
    """An in-memory SQLite database holding the application tables."""

    def __init__(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        # SQLite ignores postgresql_where: recreate the partial unique index by hand.
        with self.engine.begin() as connection:
            connection.execute(text("DROP INDEX IF EXISTS ix_custom_domains_domain_unique"))
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX ix_custom_domains_domain_unique "
                    "ON custom_domains (domain) WHERE deleted_at IS NULL"
                )
            )

    @contextmanager
    def session(self):
        """Yield a synchronous session (used to seed and inspect data)."""
        with Session(self.engine, expire_on_commit=False) as session:
            yield session

    def install(self, app) -> None:
        """Make the application use this database for its ``get_db`` dependency."""

        async def override_get_db():
            session = Session(self.engine, expire_on_commit=False)
            try:
                yield AsyncSessionShim(session)
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_get_db
