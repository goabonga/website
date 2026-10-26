# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Local cache of user identity resolved from the auth service.

Stores the mapping between OIDC ``sub`` (pairwise UUID) and human-readable
fields (email, display name, avatar URL). Updated on every login and
used to render owner/grantee names without calling the auth service.
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from apt_server.db.models.base import Base


class UserCache(Base):
    """Locally cached user profile from auth."""

    __tablename__ = "user_cache"

    sub: Mapped[str] = mapped_column(String(255), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    avatar_url: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    @property
    def display(self) -> str:
        return self.email or self.name or self.sub

    def __repr__(self) -> str:
        return f"<UserCache {self.sub} {self.email}>"
