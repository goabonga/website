# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Database configuration with SQLAlchemy async support."""

from collections.abc import AsyncGenerator, Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from internal.config import settings


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""

    pass


def get_async_database_url(url: str) -> str:
    """Convert database URL to async driver format."""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def get_sync_database_url(url: str) -> str:
    """Convert database URL to sync driver format (for Celery tasks).

    Uses psycopg (v3) driver which is already installed.
    """
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" in url:
        url = url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://") and "+psycopg" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


# Create async engine (shared database with backend - contains chat history)
engine = create_async_engine(
    get_async_database_url(settings.database_url),
    echo=settings.debug,
)

# Create async session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# Create sync engine for Celery tasks
sync_engine = create_engine(
    get_sync_database_url(settings.database_url),
    echo=settings.debug,
)

# Create sync session factory for Celery tasks
sync_session_maker = sessionmaker(
    sync_engine,
    class_=Session,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession]:
    """Dependency to get database session."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


@contextmanager
def get_sync_db_session() -> Generator[Session]:
    """Context manager for sync database session (for Celery tasks)."""
    session = sync_session_maker()
    try:
        yield session
    finally:
        session.close()
