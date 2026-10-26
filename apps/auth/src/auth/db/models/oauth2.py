# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""OAuth2-related database models."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auth.db.base import Base, TimestampMixin


class DeviceCodeStatus(StrEnum):
    """Status of a device authorization request."""

    PENDING = "pending"  # Waiting for user authorization
    AUTHORIZED = "authorized"  # User approved
    DENIED = "denied"  # User denied
    EXPIRED = "expired"  # Code expired


class OAuth2Client(Base, TimestampMixin):
    """OAuth2 client application."""

    __tablename__ = "oauth2_clients"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    client_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    client_secret_hash: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    homepage_url: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )
    redirect_uris: Mapped[list[str]] = mapped_column(
        ARRAY(String(2048)),
        nullable=False,
        default=list,
    )
    allowed_scopes: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)),
        nullable=False,
        default=list,
    )
    allowed_grant_types: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)),
        nullable=False,
        default=list,
    )
    token_endpoint_auth_method: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="client_secret_basic",
    )
    is_confidential: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    require_pkce: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    require_consent: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    # JAR (JWT Authorization Request) - RFC 9101
    jwks_uri: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )
    request_object_signing_alg: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
        default="RS256",
    )
    # CORS allowed origins for browser-based OAuth2 flows
    allowed_origins: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(2048)),
        nullable=True,
        default=None,
    )
    # Custom token expiry settings (NULL = use global config defaults)
    access_token_expiry_seconds: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None,
    )
    refresh_token_expiry_seconds: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None,
    )
    # Multi-tenancy: optional tenant scope (NULL = global client)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Relationships
    authorization_codes: Mapped[list["AuthorizationCode"]] = relationship(
        back_populates="client",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<OAuth2Client client_id={self.client_id} name={self.name}>"


class AuthorizationCode(Base, TimestampMixin):
    """OAuth2 authorization code."""

    __tablename__ = "authorization_codes"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    code_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("oauth2_clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    redirect_uri: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
    )
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)),
        nullable=False,
        default=list,
    )
    code_challenge: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    code_challenge_method: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )
    nonce: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    state: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
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
    client: Mapped["OAuth2Client"] = relationship(back_populates="authorization_codes")
    user: Mapped["User"] = relationship()

    def __repr__(self) -> str:
        return f"<AuthorizationCode client_id={self.client_id} used={self.used_at is not None}>"


class AccessToken(Base, TimestampMixin):
    """OAuth2 access token (stored hash only)."""

    __tablename__ = "access_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    jti: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("oauth2_clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)),
        nullable=False,
        default=list,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    client: Mapped["OAuth2Client"] = relationship()
    user: Mapped["User | None"] = relationship()
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="access_token",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<AccessToken jti={self.jti} revoked={self.revoked_at is not None}>"


class RefreshToken(Base, TimestampMixin):
    """OAuth2 refresh token (stored hash only)."""

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    access_token_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("access_tokens.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("oauth2_clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)),
        nullable=False,
        default=list,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    access_token: Mapped["AccessToken"] = relationship(back_populates="refresh_tokens")
    client: Mapped["OAuth2Client"] = relationship()
    user: Mapped["User | None"] = relationship()

    def __repr__(self) -> str:
        return (
            f"<RefreshToken revoked={self.revoked_at is not None} used={self.used_at is not None}>"
        )


class DeviceCode(Base, TimestampMixin):
    """OAuth2 Device Authorization (RFC 8628)."""

    __tablename__ = "device_codes"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    device_code_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    user_code: Mapped[str] = mapped_column(
        String(16),
        unique=True,
        nullable=False,
        index=True,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("oauth2_clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)),
        nullable=False,
        default=list,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=DeviceCodeStatus.PENDING.value,
    )
    verification_uri: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
    )
    interval: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    last_poll_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    client: Mapped["OAuth2Client"] = relationship()
    user: Mapped["User | None"] = relationship()

    def __repr__(self) -> str:
        return f"<DeviceCode user_code={self.user_code} status={self.status}>"


class PARRequest(Base, TimestampMixin):
    """Pushed Authorization Request (RFC 9126)."""

    __tablename__ = "par_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    request_uri: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
        index=True,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("oauth2_clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Store the full authorization request parameters
    response_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    redirect_uri: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
    )
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)),
        nullable=False,
        default=list,
    )
    state: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    code_challenge: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    code_challenge_method: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )
    nonce: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    prompt: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
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
    client: Mapped["OAuth2Client"] = relationship()

    def __repr__(self) -> str:
        return f"<PARRequest request_uri={self.request_uri} used={self.used_at is not None}>"


# Forward reference for User relationship
from auth.db.models.user import User  # noqa: E402, F401
