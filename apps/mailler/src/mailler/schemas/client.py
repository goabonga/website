# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Authorized client request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from mailler.services.providers.factory import known_providers


def _check_provider(name: str) -> str:
    if name not in known_providers():
        raise ValueError(f"Unknown provider '{name}' (known: {', '.join(known_providers())})")
    return name


class SenderIdentity(BaseModel):
    """A sender identity a client may use."""

    email: EmailStr = Field(..., description="Sender address")
    name: str | None = Field(None, max_length=255, description="Sender display name")


class ClientCreate(BaseModel):
    """Request schema for registering a client."""

    client_id: str = Field(
        ...,
        min_length=1,
        max_length=255,
        pattern=r"^\S+$",
        description="OAuth2 client the record applies to (client_id or azp of its tokens)",
    )
    name: str | None = Field(None, max_length=255, description="Display name of the application")
    is_active: bool = Field(True, description="An inactive client is refused")
    from_email: EmailStr | None = Field(None, description="Default sender address")
    from_name: str | None = Field(None, max_length=255, description="Default sender name")
    reply_to: EmailStr | None = Field(
        None, description="Reply-to address; when set, emails cannot use another one"
    )
    allowed_senders: list[SenderIdentity] = Field(
        default_factory=list, description="Other sender identities the client may choose"
    )
    allowed_providers: list[str] = Field(
        default_factory=list, description="Providers the client may use"
    )
    default_provider: str | None = Field(
        None, description="Provider used when the client names none"
    )

    @field_validator("allowed_providers")
    @classmethod
    def _known_providers(cls, value: list[str]) -> list[str]:
        return [_check_provider(name) for name in value]

    @field_validator("default_provider")
    @classmethod
    def _known_default_provider(cls, value: str | None) -> str | None:
        return _check_provider(value) if value is not None else None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "client_id": "my-application",
                "name": "My application",
                "from_email": "no-reply@my-application.example",
                "from_name": "My application",
                "allowed_providers": ["brevo"],
                "default_provider": "brevo",
            }
        }
    )


class ClientUpdate(BaseModel):
    """Request schema for updating a client (partial body)."""

    name: str | None = Field(None, max_length=255)
    is_active: bool | None = None
    from_email: EmailStr | None = None
    from_name: str | None = Field(None, max_length=255)
    reply_to: EmailStr | None = None
    allowed_senders: list[SenderIdentity] | None = None
    allowed_providers: list[str] | None = None
    default_provider: str | None = None

    @field_validator("allowed_providers")
    @classmethod
    def _known_providers(cls, value: list[str] | None) -> list[str] | None:
        return [_check_provider(name) for name in value] if value is not None else None

    @field_validator("default_provider")
    @classmethod
    def _known_default_provider(cls, value: str | None) -> str | None:
        return _check_provider(value) if value is not None else None


class ClientResponse(BaseModel):
    """Response schema for a client."""

    id: int
    client_id: str
    name: str | None
    is_active: bool
    from_email: str | None
    from_name: str | None
    reply_to: str | None
    allowed_senders: list[SenderIdentity]
    allowed_providers: list[str]
    default_provider: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClientListResponse(BaseModel):
    """Paginated client list response."""

    items: list[ClientResponse]
    total: int
    page: int
    page_size: int
    pages: int
