# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Database configuration and session management."""

from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from custom_domain.config import settings


def _get_async_url(url: str) -> str:
    """Convert PostgreSQL URL to async format (asyncpg)."""
    return url.replace("postgresql://", "postgresql+asyncpg://").replace(
        "postgresql:///", "postgresql+asyncpg:///"
    )


def _get_sync_url(url: str) -> str:
    """Convert PostgreSQL URL to sync format (psycopg2)."""
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    return url.replace("postgresql://", "postgresql+psycopg2://", 1)


# Async engine for FastAPI
async_engine = create_async_engine(
    _get_async_url(settings.database_url),
    echo=settings.database_echo,
    pool_pre_ping=True,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
)

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Alias for main.py lifespan
engine = async_engine


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session for FastAPI dependency injection.

    Yields:
        AsyncSession: Database session
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


@asynccontextmanager
async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session as context manager.

    Yields:
        AsyncSession: Database session
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# Sync engine for Celery workers
sync_engine = create_engine(
    _get_sync_url(settings.database_url),
    echo=settings.database_echo,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

# Sync session factory
SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False,
)


@contextmanager
def get_sync_db() -> Generator[Session, None, None]:
    """Get sync database session for Celery workers.

    Yields:
        Session: Database session
    """
    session = SyncSessionLocal()
    try:
        yield session
    finally:
        session.close()
