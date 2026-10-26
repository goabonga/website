# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Contact and ContactGroup request/response schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# ==================== Contact Schemas ====================


class ContactCreate(BaseModel):
    """Request schema for creating a contact."""

    email: EmailStr = Field(..., description="Contact email address")
    first_name: str | None = Field(None, max_length=100, description="First name")
    last_name: str | None = Field(None, max_length=100, description="Last name")
    source: str | None = Field(
        None, max_length=100, description="Source of contact (signup, import, etc.)"
    )
    custom_fields: dict[str, Any] | None = Field(None, description="Custom fields for the contact")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "user@example.com",
                "first_name": "John",
                "last_name": "Doe",
                "source": "api",
                "custom_fields": {"company": "Acme Inc", "role": "Developer"},
            }
        }
    )


class ContactUpdate(BaseModel):
    """Request schema for updating a contact."""

    first_name: str | None = Field(None, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    status: str | None = Field(
        None,
        pattern=r"^(active|unsubscribed|bounced|complained)$",
        description="Contact status",
    )
    source: str | None = Field(None, max_length=100)
    custom_fields: dict[str, Any] | None = Field(None)


class ContactResponse(BaseModel):
    """Response schema for a contact."""

    id: UUID
    client_id: str
    email: str
    first_name: str | None
    last_name: str | None
    full_name: str
    status: str
    source: str | None
    custom_fields: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    groups: list["ContactGroupBasic"] | None = None

    model_config = ConfigDict(from_attributes=True)


class ContactListItem(BaseModel):
    """Contact list item for pagination."""

    id: UUID
    email: str
    first_name: str | None
    last_name: str | None
    status: str
    source: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContactListResponse(BaseModel):
    """Paginated contact list response."""

    items: list[ContactListItem]
    total: int
    page: int
    page_size: int
    pages: int


class BulkContactCreate(BaseModel):
    """Request schema for bulk contact creation."""

    contacts: list[ContactCreate] = Field(
        ..., min_length=1, max_length=1000, description="List of contacts to create"
    )
    skip_existing: bool = Field(
        True, description="Skip contacts with existing emails instead of failing"
    )


class BulkContactResponse(BaseModel):
    """Response schema for bulk contact operations."""

    created: int = Field(..., description="Number of contacts created")
    skipped: int = Field(..., description="Number of contacts skipped (existing)")
    failed: int = Field(..., description="Number of contacts that failed to create")
    errors: list[str] | None = Field(None, description="Error messages for failures")


# ==================== Contact Group Schemas ====================


class ContactGroupCreate(BaseModel):
    """Request schema for creating a contact group."""

    slug: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        description="Group identifier, unique per client (lowercase, hyphens allowed)",
    )
    name: str = Field(..., min_length=1, max_length=255, description="Group name")
    description: str | None = Field(None, description="Group description")
    is_dynamic: bool = Field(False, description="Whether this is a dynamic (filter-based) group")
    filter_criteria: dict[str, Any] | None = Field(
        None, description="Filter criteria for dynamic groups"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "slug": "newsletter-subscribers",
                "name": "Newsletter Subscribers",
                "description": "Users subscribed to our weekly newsletter",
                "is_dynamic": False,
            }
        }
    )


class ContactGroupUpdate(BaseModel):
    """Request schema for updating a contact group."""

    name: str | None = Field(None, min_length=1, max_length=255)
    slug: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None)
    is_dynamic: bool | None = Field(None)
    filter_criteria: dict[str, Any] | None = Field(None)


class ContactGroupBasic(BaseModel):
    """Basic contact group info for embedding in contact responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str


class ContactGroupResponse(BaseModel):
    """Response schema for a contact group."""

    id: int
    client_id: str
    slug: str
    name: str
    description: str | None
    is_dynamic: bool
    filter_criteria: dict[str, Any] | None
    member_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContactGroupListItem(BaseModel):
    """Contact group list item for pagination."""

    id: int
    slug: str
    name: str
    description: str | None
    is_dynamic: bool
    member_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContactGroupListResponse(BaseModel):
    """Paginated contact group list response."""

    items: list[ContactGroupListItem]
    total: int
    page: int
    page_size: int
    pages: int


class GroupMembershipRequest(BaseModel):
    """Request schema for managing group membership."""

    contact_ids: list[UUID] = Field(
        ..., min_length=1, max_length=1000, description="List of contact IDs"
    )


class GroupMembershipResponse(BaseModel):
    """Response schema for group membership operations."""

    added: int = Field(..., description="Number of contacts added to group")
    removed: int = Field(..., description="Number of contacts removed from group")
    skipped: int = Field(..., description="Number of contacts skipped (already in/not in group)")


# Update forward references
ContactResponse.model_rebuild()
