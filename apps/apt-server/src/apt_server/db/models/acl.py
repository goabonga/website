# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Per-package ACL model."""

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apt_server.db.models.base import Base


class ACLRole(enum.StrEnum):
    """Role granted by an ACL entry."""

    READ = "read"
    WRITE = "write"


class PackageACL(Base):
    """Grant a user or group a role on a specific package.

    Exactly one of ``grantee_user_id`` or ``grantee_group`` must be set:
    - ``grantee_user_id``: OIDC ``sub`` of the user receiving the grant.
    - ``grantee_group``: group/role claim (e.g. ``team:backend``) sourced
      from the ``auth`` introspection response.
    """

    __tablename__ = "package_acl"
    __table_args__ = (
        CheckConstraint(
            "(grantee_user_id IS NOT NULL) <> (grantee_group IS NOT NULL)",
            name="ck_package_acl_grantee_exclusive",
        ),
        Index(
            "uq_package_acl_user",
            "package_id",
            "grantee_user_id",
            "role",
            unique=True,
            postgresql_where="grantee_user_id IS NOT NULL",
        ),
        Index(
            "uq_package_acl_group",
            "package_id",
            "grantee_group",
            "role",
            unique=True,
            postgresql_where="grantee_group IS NOT NULL",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    package_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("packages.id", ondelete="CASCADE"),
        index=True,
    )

    grantee_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    grantee_group: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    role: Mapped[ACLRole] = mapped_column(
        Enum(ACLRole, name="package_acl_role", values_callable=lambda e: [m.value for m in e])
    )

    granted_by: Mapped[str] = mapped_column(String(255))
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    package: Mapped["Package"] = relationship("Package", back_populates="acl")

    def __repr__(self) -> str:
        target = self.grantee_user_id or self.grantee_group
        return f"<PackageACL package={self.package_id} {target} role={self.role}>"


from apt_server.db.models.package import Package  # noqa: E402, F401
