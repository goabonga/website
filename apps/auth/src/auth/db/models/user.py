# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""User-related database models."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auth.db.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """User account."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Registration source tracking
    registration_source: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment=(
            "How user registered: 'direct' (auth UI), 'api' (client app), 'oauth' (social login)"
        ),
    )
    registration_client_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="OAuth client_id that created the user (for API registrations)",
    )
    registration_tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Tenant context during registration (if any)",
    )
    registration_ip: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        comment="IP address at registration",
    )
    registration_user_agent: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="User agent at registration",
    )

    # Relationships
    emails: Mapped[list["UserEmail"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    passwords: Mapped[list["UserPassword"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    profile: Mapped["UserProfile | None"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} active={self.is_active}>"


class UserEmail(Base, TimestampMixin):
    """User email address."""

    __tablename__ = "user_emails"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="emails")

    def __repr__(self) -> str:
        return f"<UserEmail email={self.email} verified={self.is_verified}>"


class UserPassword(Base, TimestampMixin):
    """User password (hashed)."""

    __tablename__ = "user_passwords"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    password_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    is_current: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="passwords")

    def __repr__(self) -> str:
        return f"<UserPassword user_id={self.user_id} current={self.is_current}>"


class VerificationCode(Base, TimestampMixin):
    """Email verification code."""

    __tablename__ = "verification_codes"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    code_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship()

    def __repr__(self) -> str:
        return f"<VerificationCode email={self.email} used={self.used_at is not None}>"


class PasswordResetToken(Base, TimestampMixin):
    """Password reset token."""

    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship()

    def __repr__(self) -> str:
        return f"<PasswordResetToken email={self.email} used={self.used_at is not None}>"


class Session(Base, TimestampMixin):
    """User session for browser authentication."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )
    csrf_token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
    )
    user_agent: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # Multi-tenancy: optional tenant scope (NULL = global session)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Relationships
    user: Mapped["User"] = relationship()

    def __repr__(self) -> str:
        return f"<Session user_id={self.user_id} revoked={self.revoked_at is not None}>"


class UserMFA(Base, TimestampMixin):
    """User MFA configuration."""

    __tablename__ = "user_mfas"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    totp_secret_encrypted: Mapped[bytes | None] = mapped_column(
        nullable=True,
    )
    totp_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    totp_enabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship()
    backup_codes: Mapped[list["MFABackupCode"]] = relationship(
        back_populates="user_mfa",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<UserMFA user_id={self.user_id} totp_enabled={self.totp_enabled}>"


class MFABackupCode(Base, TimestampMixin):
    """MFA backup/recovery code."""

    __tablename__ = "mfa_backup_codes"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    user_mfa_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_mfas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    user_mfa: Mapped["UserMFA"] = relationship(back_populates="backup_codes")

    def __repr__(self) -> str:
        return f"<MFABackupCode used={self.used_at is not None}>"


class MFAEmailCode(Base, TimestampMixin):
    """MFA email verification code."""

    __tablename__ = "mfa_email_codes"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    code_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship()

    def __repr__(self) -> str:
        return f"<MFAEmailCode email={self.email} used={self.used_at is not None}>"


class UserProfile(Base, TimestampMixin):
    """User profile for OIDC claims."""

    __tablename__ = "user_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Standard OIDC claims
    name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    given_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    family_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    middle_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    nickname: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    preferred_username: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    profile_url: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )
    picture_url: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )
    website: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )
    gender: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    birthdate: Mapped[str | None] = mapped_column(
        String(10),  # YYYY-MM-DD format
        nullable=True,
    )
    zoneinfo: Mapped[str | None] = mapped_column(
        String(50),  # e.g., "Europe/Paris"
        nullable=True,
    )
    locale: Mapped[str | None] = mapped_column(
        String(10),  # e.g., "en-US"
        nullable=True,
    )

    # Address claims (stored as JSON-compatible fields)
    address_formatted: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    address_street: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    address_locality: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    address_region: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    address_postal_code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    address_country: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # Phone number
    phone_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    phone_number_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="profile")

    def __repr__(self) -> str:
        return f"<UserProfile user_id={self.user_id} name={self.name}>"
