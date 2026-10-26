# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Database configuration and session management for Mailler API."""

from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from mailler.config import settings

# Async engine for FastAPI
async_engine = create_async_engine(
    settings.database_url.replace("postgresql://", "postgresql+asyncpg://").replace(
        "postgresql:///", "postgresql+asyncpg:///"
    ),
    echo=settings.database_echo,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


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
    settings.database_url.replace("postgresql+asyncpg://", "postgresql://").replace("+asyncpg", ""),
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
