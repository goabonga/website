# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Alembic environment configuration for Custom Domain Service."""

import os
from logging.config import fileConfig

from alembic import context

# Import only what we need - avoid importing database.py
from custom_domain.models.base import Base

# Import all models to register them with Base.metadata
# These imports must not trigger database.py loading
from custom_domain.models.client import AuthorizedClient  # noqa: F401
from custom_domain.models.domain import CustomDomain  # noqa: F401
from custom_domain.models.template import NginxTemplate  # noqa: F401
from sqlalchemy import engine_from_config, pool

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Model metadata for autogenerate
target_metadata = Base.metadata


def get_url() -> str:
    """Get database URL from environment or default."""
    # Get URL directly from environment to avoid importing custom_domain.config
    # which might trigger other imports
    url = os.environ.get("DATABASE_URL", "postgresql:///custom_domain")
    # Ensure we use sync driver for alembic (psycopg2, not asyncpg)
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    return url.replace("postgresql://", "postgresql+psycopg2://", 1)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
