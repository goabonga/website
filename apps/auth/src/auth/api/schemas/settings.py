# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Schemas for /auth/settings endpoints."""

from pydantic import BaseModel


class ProfileUpdateRequest(BaseModel):
    """Request model for profile update via API."""

    nickname: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    middle_name: str | None = None
    preferred_username: str | None = None
    picture_url: str | None = None
    profile_url: str | None = None
    website: str | None = None
    gender: str | None = None
    birthdate: str | None = None
    zoneinfo: str | None = None
    locale: str | None = None
    phone_number: str | None = None
    # Address fields
    address_street: str | None = None
    address_locality: str | None = None
    address_region: str | None = None
    address_postal_code: str | None = None
    address_country: str | None = None


class ProfileResponse(BaseModel):
    """Response model for profile data."""

    nickname: str | None = None
    name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    middle_name: str | None = None
    preferred_username: str | None = None
    picture_url: str | None = None
    profile_url: str | None = None
    website: str | None = None
    gender: str | None = None
    birthdate: str | None = None
    zoneinfo: str | None = None
    locale: str | None = None
    phone_number: str | None = None
    # Address fields
    address_street: str | None = None
    address_locality: str | None = None
    address_region: str | None = None
    address_postal_code: str | None = None
    address_country: str | None = None


class PasswordChangeRequest(BaseModel):
    """Request model for password change via API."""

    current_password: str
    new_password: str
