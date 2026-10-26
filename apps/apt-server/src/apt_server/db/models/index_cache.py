# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Cached per-caller Packages indexes.

`Packages` / `Packages.gz` files are filtered to the caller's visible set, so
they are expensive to regenerate on every `apt update`. The entries in this
table are short-lived snapshots keyed on a hash of (caller, suite, component,
architecture) and invalidated on any upload/delete/ACL change that affects
the caller's view.
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from apt_server.db.models.base import Base


class IndexCache(Base):
    """Rendered Packages index bound to a specific caller view."""

    __tablename__ = "index_cache"

    cache_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    body: Mapped[bytes] = mapped_column(LargeBinary)
    sha256: Mapped[str] = mapped_column(String(64))
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    def __repr__(self) -> str:
        return f"<IndexCache {self.cache_key} generated_at={self.generated_at}>"
