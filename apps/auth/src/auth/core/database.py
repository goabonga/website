# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Database connection module.

Provides async PostgreSQL connectivity using SQLAlchemy 2.0 with asyncpg.
Also provides sync sessions for Celery workers.
"""

import logging
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from auth.config import settings
from auth.db.base import Base

logger = logging.getLogger(__name__)


def get_async_database_url(url: str) -> str:
    """Convert database URL to async format with asyncpg driver.

    Handles both:
    - postgresql://... -> postgresql+asyncpg://...
    - postgresql+asyncpg://... -> postgresql+asyncpg://... (no change)
    """
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


# Create async engine
engine: AsyncEngine = create_async_engine(
    get_async_database_url(settings.database_url),
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    echo=settings.database_echo,
    pool_pre_ping=True,
)

# Session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for database sessions outside of FastAPI."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_database_connection() -> bool:
    """Check if database connection is healthy."""
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
            return True
    except Exception as e:
        logger.error("Database connection check failed: %s", e)
        return False


async def init_database() -> None:
    """Initialize database (create tables). Use Alembic in production."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_database() -> None:
    """Close database connection pool."""
    await engine.dispose()


# =============================================================================
# Sync database connection for Celery workers
# =============================================================================


def get_sync_database_url(url: str) -> str:
    """Convert database URL to sync format with psycopg2 driver.

    Handles:
    - postgresql+asyncpg://... -> postgresql+psycopg2://...
    - postgresql://... -> postgresql+psycopg2://...
    - postgres://... -> postgresql+psycopg2://...
    """
    if "+asyncpg" in url:
        return url.replace("+asyncpg", "+psycopg2")
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    return url


# Create sync engine for Celery workers
sync_engine = create_engine(
    get_sync_database_url(settings.database_url),
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    echo=settings.database_echo,
    pool_pre_ping=True,
)

# Sync session factory for Celery workers
sync_session_factory = sessionmaker(
    bind=sync_engine,
    expire_on_commit=False,
    autoflush=False,
)


@contextmanager
def get_sync_db() -> Generator[Session, None, None]:
    """Context manager for sync database sessions (for Celery workers)."""
    session = sync_session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
