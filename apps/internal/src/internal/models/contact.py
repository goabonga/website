# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Contact and ContactGroup models for email campaigns."""

import uuid as uuid_lib
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from internal.database import Base


class ContactStatus(StrEnum):
    """Status of a contact."""

    ACTIVE = "active"
    UNSUBSCRIBED = "unsubscribed"
    BOUNCED = "bounced"
    COMPLAINED = "complained"


class Contact(Base):
    """Contact for email campaigns.

    Stores contact information with support for custom fields.
    Tracks subscription status and source of acquisition.
    """

    __tablename__ = "contacts"

    id: Mapped[uuid_lib.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid_lib.uuid4,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    first_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    last_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ContactStatus.ACTIVE.value,
        index=True,
    )
    source: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    custom_fields: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    group_memberships: Mapped[list["ContactGroupMember"]] = relationship(
        "ContactGroupMember",
        back_populates="contact",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    @property
    def full_name(self) -> str:
        """Get full name of the contact."""
        parts = [self.first_name, self.last_name]
        return " ".join(p for p in parts if p) or ""

    @property
    def groups(self) -> list["ContactGroup"]:
        """Get all groups this contact belongs to."""
        return [m.group for m in self.group_memberships if m.group]

    def __repr__(self) -> str:
        return f"<Contact(id={self.id}, email='{self.email}', status='{self.status}')>"


class ContactGroup(Base):
    """Group of contacts for targeted campaigns.

    Supports both static groups (manual membership) and dynamic groups
    (filter-based membership, future enhancement).
    """

    __tablename__ = "contact_groups"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    slug: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    is_dynamic: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )
    filter_criteria: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    members: Mapped[list["ContactGroupMember"]] = relationship(
        "ContactGroupMember",
        back_populates="group",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    @property
    def member_count(self) -> int:
        """Get count of members in this group."""
        return len(self.members)

    @property
    def contacts(self) -> list[Contact]:
        """Get all contacts in this group."""
        return [m.contact for m in self.members if m.contact]

    def __repr__(self) -> str:
        return f"<ContactGroup(id={self.id}, slug='{self.slug}', members={self.member_count})>"


class ContactGroupMember(Base):
    """Association table for contact-group membership."""

    __tablename__ = "contact_group_members"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    contact_id: Mapped[uuid_lib.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("contact_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Relationships
    contact: Mapped[Contact] = relationship(
        "Contact",
        back_populates="group_memberships",
        lazy="selectin",
    )
    group: Mapped[ContactGroup] = relationship(
        "ContactGroup",
        back_populates="members",
        lazy="select",
    )

    __table_args__ = (UniqueConstraint("contact_id", "group_id", name="uq_contact_group_member"),)

    def __repr__(self) -> str:
        return f"<ContactGroupMember(contact_id={self.contact_id}, group_id={self.group_id})>"
