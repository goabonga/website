# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""OIDC UserInfo response schemas."""

from pydantic import BaseModel, Field


class UserInfoResponse(BaseModel):
    """OIDC UserInfo response."""

    # Required
    sub: str = Field(..., description="Subject identifier")

    # Profile scope
    name: str | None = Field(None, description="Full name")
    given_name: str | None = Field(None, description="Given name(s)")
    family_name: str | None = Field(None, description="Family name(s)")
    middle_name: str | None = Field(None, description="Middle name(s)")
    nickname: str | None = Field(None, description="Casual name")
    preferred_username: str | None = Field(None, description="Preferred username")
    profile: str | None = Field(None, description="Profile page URL")
    picture: str | None = Field(None, description="Profile picture URL")
    website: str | None = Field(None, description="Website URL")
    gender: str | None = Field(None, description="Gender")
    birthdate: str | None = Field(None, description="Birthday (YYYY-MM-DD)")
    zoneinfo: str | None = Field(None, description="Time zone")
    locale: str | None = Field(None, description="Locale")
    updated_at: int | None = Field(None, description="Last update timestamp")

    # Email scope
    email: str | None = Field(None, description="Email address")
    email_verified: bool | None = Field(None, description="Email verified flag")

    # Phone scope
    phone_number: str | None = Field(None, description="Phone number")
    phone_number_verified: bool | None = Field(None, description="Phone verified flag")

    # Address scope
    address: dict[str, str] | None = Field(None, description="Address claim")
