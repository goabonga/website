# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""SaaS application schemas."""

from datetime import datetime
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, Field


def validate_url_allowlist(entries: list[str] | None) -> list[str] | None:
    """Check the entries of a checkout URL allow-list.

    Each entry is an absolute ``http`` or ``https`` URL prefix (an origin such
    as ``https://app.example.test`` or an origin followed by a path) without
    credentials, query string or fragment.

    Raises:
        ValueError: If an entry is not an acceptable prefix.
    """
    if entries is None:
        return None
    cleaned: list[str] = []
    for entry in entries:
        parts = urlsplit(entry.strip())
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError(f"'{entry}' is not an absolute http(s) URL")
        if parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError(f"'{entry}' must not contain credentials, query or fragment")
        cleaned.append(entry.strip().rstrip("/"))
    return cleaned


UrlAllowlist = Annotated[list[str], AfterValidator(validate_url_allowlist)]


class SaasAppCreate(BaseModel):
    """Schema for creating a SaaS application."""

    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: str | None = Field(None, max_length=1000)
    webhook_url: str | None = Field(None, max_length=500)
    webhook_secret: str | None = Field(None, max_length=255)
    branding: dict | None = None
    checkout_url_allowlist: UrlAllowlist | None = None


class SaasAppUpdate(BaseModel):
    """Schema for updating a SaaS application."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)
    webhook_url: str | None = Field(None, max_length=500)
    webhook_secret: str | None = Field(None, max_length=255)
    branding: dict | None = None
    checkout_url_allowlist: UrlAllowlist | None = None
    is_active: bool | None = None


class SaasAppResponse(BaseModel):
    """Schema for SaaS application response."""

    id: str
    name: str
    slug: str
    description: str | None
    webhook_url: str | None
    branding: dict | None
    checkout_url_allowlist: list[str] | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
