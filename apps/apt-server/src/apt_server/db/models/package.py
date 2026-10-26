# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Package domain model."""

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, Enum, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apt_server.db.models.base import Base


class PackageVisibility(enum.StrEnum):
    """Visibility level of a stored package.

    - ``public``: anyone with read access to the component sees the package.
    - ``private``: only the owner and explicit ACL grantees see the package.
    - ``shared``: owner + ACL grantees, with the understanding that grantees
      may further share (signalling intent only; enforcement stays ACL-based).
    """

    PUBLIC = "public"
    PRIVATE = "private"
    SHARED = "shared"


class Package(Base):
    """An uploaded ``.deb`` tracked in the repository."""

    __tablename__ = "packages"
    __table_args__ = (
        UniqueConstraint(
            "name",
            "version",
            "architecture",
            "suite",
            "component",
            name="uq_packages_identity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    name: Mapped[str] = mapped_column(String(255), index=True)
    version: Mapped[str] = mapped_column(String(255))
    architecture: Mapped[str] = mapped_column(String(32))
    suite: Mapped[str] = mapped_column(String(64), index=True)
    component: Mapped[str] = mapped_column(String(64), index=True)

    owner_id: Mapped[str] = mapped_column(String(255), index=True)
    visibility: Mapped[PackageVisibility] = mapped_column(
        Enum(
            PackageVisibility,
            name="package_visibility",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=PackageVisibility.PRIVATE,
    )

    filename: Mapped[str] = mapped_column(Text, unique=True)
    size: Mapped[int] = mapped_column(BigInteger)
    md5: Mapped[str] = mapped_column(String(32))
    sha1: Mapped[str] = mapped_column(String(40))
    sha256: Mapped[str] = mapped_column(String(64), index=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    control: Mapped[dict] = mapped_column(JSONB, default=dict)

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    acl: Mapped[list["PackageACL"]] = relationship(
        "PackageACL",
        back_populates="package",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Package {self.name} {self.version} {self.architecture} {self.component}>"


from apt_server.db.models.acl import PackageACL  # noqa: E402, F401
