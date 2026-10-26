# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Pydantic schemas for users API."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserResponse(BaseModel):
    """Response for a single user."""

    id: uuid.UUID
    email: str
    is_active: bool
    registration_source: str | None = None
    name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    nickname: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CreateUserRequest(BaseModel):
    """Request body for creating a user."""

    email: EmailStr = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    is_active: bool = True


class UpdateUserRequest(BaseModel):
    """Request body for partially updating a user.

    Sparse update: only fields present in the request body are modified.
    Profile fields (``name``, ``given_name``, ``family_name``, ``nickname``)
    are propagated to the associated :class:`UserProfile`. An omitted field
    leaves the database value untouched; an explicit ``null`` clears the
    stored value.
    """

    is_active: bool | None = None
    name: str | None = Field(default=None, max_length=255)
    given_name: str | None = Field(default=None, max_length=255)
    family_name: str | None = Field(default=None, max_length=255)
    nickname: str | None = Field(default=None, max_length=255)
