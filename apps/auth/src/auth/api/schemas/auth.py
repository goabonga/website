# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Authentication schemas."""

import re
from typing import Literal

from pydantic import BaseModel, EmailStr, field_validator


class ProfileFields(BaseModel):
    """OIDC standard profile claims for registration."""

    # Required fields
    nickname: str
    firstname: str  # maps to given_name
    lastname: str  # maps to family_name

    # Optional OIDC standard claims
    middle_name: str | None = None
    preferred_username: str | None = None
    profile_url: str | None = None
    picture_url: str | None = None
    website: str | None = None
    gender: Literal["male", "female", "other"] | str | None = None
    birthdate: str | None = None  # YYYY-MM-DD format
    zoneinfo: str | None = None  # e.g., "Europe/Paris"
    locale: str | None = None  # e.g., "fr-FR"

    # Address claims
    address_street: str | None = None
    address_locality: str | None = None  # city
    address_region: str | None = None  # state/province
    address_postal_code: str | None = None
    address_country: str | None = None

    # Phone
    phone_number: str | None = None

    @field_validator("nickname", "firstname", "lastname")
    @classmethod
    def validate_required_fields(cls, v: str, info) -> str:
        """Validate required profile fields."""
        field_name = info.field_name
        v = v.strip()
        if not v:
            raise ValueError(f"{field_name.capitalize()} is required")
        if len(v) > 255:
            raise ValueError(f"{field_name.capitalize()} must be at most 255 characters")
        return v

    @field_validator("middle_name", "preferred_username")
    @classmethod
    def validate_optional_string_fields(cls, v: str | None) -> str | None:
        """Validate optional string fields."""
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if len(v) > 255:
            raise ValueError("Field must be at most 255 characters")
        return v

    @field_validator("profile_url", "picture_url", "website")
    @classmethod
    def validate_url_fields(cls, v: str | None) -> str | None:
        """Validate URL fields."""
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if len(v) > 2048:
            raise ValueError("URL must be at most 2048 characters")
        # Basic URL validation
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v

    @field_validator("birthdate")
    @classmethod
    def validate_birthdate(cls, v: str | None) -> str | None:
        """Validate birthdate format (YYYY-MM-DD)."""
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError("Birthdate must be in YYYY-MM-DD format")
        return v

    @field_validator("locale")
    @classmethod
    def validate_locale(cls, v: str | None) -> str | None:
        """Validate locale format (e.g., fr-FR)."""
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if len(v) > 10:
            raise ValueError("Locale must be at most 10 characters")
        return v

    @field_validator("zoneinfo")
    @classmethod
    def validate_zoneinfo(cls, v: str | None) -> str | None:
        """Validate timezone."""
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if len(v) > 50:
            raise ValueError("Timezone must be at most 50 characters")
        return v

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        """Validate phone number format."""
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if len(v) > 50:
            raise ValueError("Phone number must be at most 50 characters")
        return v

    @field_validator("address_street")
    @classmethod
    def validate_address_street(cls, v: str | None) -> str | None:
        """Validate street address."""
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if len(v) > 500:
            raise ValueError("Street address must be at most 500 characters")
        return v

    @field_validator("address_locality", "address_region")
    @classmethod
    def validate_address_fields(cls, v: str | None) -> str | None:
        """Validate address locality and region."""
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if len(v) > 255:
            raise ValueError("Field must be at most 255 characters")
        return v

    @field_validator("address_postal_code")
    @classmethod
    def validate_postal_code(cls, v: str | None) -> str | None:
        """Validate postal code."""
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if len(v) > 50:
            raise ValueError("Postal code must be at most 50 characters")
        return v

    @field_validator("address_country")
    @classmethod
    def validate_country(cls, v: str | None) -> str | None:
        """Validate country."""
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if len(v) > 100:
            raise ValueError("Country must be at most 100 characters")
        return v

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str | None) -> str | None:
        """Validate gender."""
        if v is None:
            return None
        v = v.strip().lower()
        if not v:
            return None
        if len(v) > 50:
            raise ValueError("Gender must be at most 50 characters")
        return v

    def to_profile_dict(self) -> dict:
        """Convert to dictionary for UserProfile creation."""
        return {
            "nickname": self.nickname,
            "given_name": self.firstname,
            "family_name": self.lastname,
            "middle_name": self.middle_name,
            "preferred_username": self.preferred_username,
            "profile_url": self.profile_url,
            "picture_url": self.picture_url,
            "website": self.website,
            "gender": self.gender,
            "birthdate": self.birthdate,
            "zoneinfo": self.zoneinfo,
            "locale": self.locale,
            "address_street": self.address_street,
            "address_locality": self.address_locality,
            "address_region": self.address_region,
            "address_postal_code": self.address_postal_code,
            "address_country": self.address_country,
            "phone_number": self.phone_number,
        }


class RegistrationSource(BaseModel):
    """Registration source information for tracking."""

    # Source type: 'direct' (auth UI), 'api' (client app), 'oauth' (social login)
    source: Literal["direct", "api", "oauth"] = "api"
    # OAuth client_id that initiated the registration
    client_id: str | None = None
    # Client application name (for display/audit purposes)
    client_name: str | None = None

    @field_validator("client_id", "client_name")
    @classmethod
    def validate_optional_fields(cls, v: str | None) -> str | None:
        """Validate optional source fields."""
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if len(v) > 255:
            raise ValueError("Field must be at most 255 characters")
        return v


class RegisterRequest(BaseModel):
    """User registration request with full OIDC profile support."""

    email: EmailStr
    password: str
    profile: ProfileFields
    # Optional registration source tracking
    registration_source: RegistrationSource | None = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password strength."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if len(v) > 128:
            raise ValueError("Password must be at most 128 characters")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain a lowercase letter")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain an uppercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain a digit")
        if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?~`]", v):
            raise ValueError("Password must contain a special character")
        return v


class RegisterResponse(BaseModel):
    """User registration response."""

    id: str
    email: str
    message: str


class LoginRequest(BaseModel):
    """Login request."""

    email: EmailStr
    password: str
    otp: str | None = None


class LoginResponse(BaseModel):
    """Login response."""

    message: str
    csrf_token: str


class ForgotPasswordRequest(BaseModel):
    """Forgot password request."""

    email: EmailStr
    # Optional custom base URL for reset link (for client apps that proxy the reset flow)
    reset_base_url: str | None = None

    @field_validator("reset_base_url")
    @classmethod
    def validate_reset_base_url(cls, v: str | None) -> str | None:
        """Validate reset base URL."""
        if v is None:
            return None
        v = v.strip().rstrip("/")
        if not v:
            return None
        if not v.startswith(("http://", "https://")):
            raise ValueError("reset_base_url must start with http:// or https://")
        if len(v) > 500:
            raise ValueError("reset_base_url must be at most 500 characters")
        return v


class ResetPasswordRequest(BaseModel):
    """Reset password request."""

    token: str
    password: str

    @field_validator("password")
    @classmethod
    def validate_reset_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class VerifyEmailRequest(BaseModel):
    """Verify email request."""

    email: EmailStr
    code: str


class ResendVerificationRequest(BaseModel):
    """Resend verification email request."""

    email: EmailStr
