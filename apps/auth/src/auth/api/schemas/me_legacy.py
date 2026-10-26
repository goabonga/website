# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Legacy /api/me request and response schemas."""

from pydantic import BaseModel, field_validator


class ProfileResponse(BaseModel):
    """User profile response."""

    sub: str
    nickname: str | None = None
    name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    middle_name: str | None = None
    preferred_username: str | None = None
    picture: str | None = None
    website: str | None = None
    gender: str | None = None
    birthdate: str | None = None
    zoneinfo: str | None = None
    locale: str | None = None
    phone_number: str | None = None


class ProfileUpdateRequest(BaseModel):
    """Profile update request."""

    nickname: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    middle_name: str | None = None
    preferred_username: str | None = None
    picture: str | None = None
    website: str | None = None
    gender: str | None = None
    birthdate: str | None = None
    zoneinfo: str | None = None
    locale: str | None = None
    phone_number: str | None = None


class PasswordChangeRequest(BaseModel):
    """Password change request."""

    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        """Validate new password strength."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v
