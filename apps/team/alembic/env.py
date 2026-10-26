# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Alembic environment configuration.

This module uses synchronous database connections for migrations,
while the application uses async connections at runtime.
"""

import re
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool
from team.config import get_settings

# Import Base and all models to register them with Base.metadata
# This avoids importing the async engine from database.py
from team.models import (  # noqa: F401
    Agent,
    Base,
    Team,
)

config = context.config
settings = get_settings()

# Convert async URL to sync URL for Alembic migrations
# postgresql+asyncpg://user@/db?host=... -> postgresql:///db?host=...
# This removes the asyncpg driver and user (peer auth uses OS user)
sync_database_url = settings.database_url
if "asyncpg" in sync_database_url:
    # Remove driver and user from URL for peer authentication
    sync_database_url = re.sub(
        r"postgresql\+asyncpg://[^@]*@/",
        "postgresql:///",
        sync_database_url,
    )
config.set_main_option("sqlalchemy.url", sync_database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using sync connection."""
    connectable = create_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
