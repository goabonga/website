# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""SQLAlchemy declarative base.

This module provides the Base class for all SQLAlchemy models.
It is separated from database.py to allow importing Base without
creating the async engine (needed for Alembic migrations).
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass
