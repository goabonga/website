# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Database models for Mailler."""

from mailler.models.base import Base
from mailler.models.email import Email, EmailStatus, ProviderStats

__all__ = [
    "Base",
    "Email",
    "EmailStatus",
    "ProviderStats",
]
