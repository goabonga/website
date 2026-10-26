# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Product schemas."""

import re
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

# A plan slug: lower case words joined by single hyphens.
SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"


def slugify(value: str) -> str:
    """Build a plan slug from free text (lower case, runs of other characters become ``-``)."""
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


class ProductCreate(BaseModel):
    """Schema for creating a product."""

    name: str = Field(..., min_length=1, max_length=255)
    slug: str | None = Field(
        None,
        max_length=100,
        pattern=SLUG_PATTERN,
        description="Plan identifier, unique per SaaS application. Defaults to "
        "metadata.slug, then to a slug built from the name.",
    )
    description: str | None = Field(None, max_length=1000)
    metadata: dict | None = None

    @model_validator(mode="after")
    def _resolve_slug(self) -> "ProductCreate":
        """Fill the slug from ``metadata.slug`` or from the name when it is not given."""
        if self.slug is None:
            candidate = (self.metadata or {}).get("slug")
            base = slugify(candidate) if isinstance(candidate, str) else ""
            self.slug = (base or slugify(self.name))[:100].strip("-")
        if not self.slug:
            raise ValueError("A slug cannot be derived from the name, provide one")
        return self


class ProductUpdate(BaseModel):
    """Schema for updating a product."""

    name: str | None = Field(None, min_length=1, max_length=255)
    slug: str | None = Field(None, max_length=100, pattern=SLUG_PATTERN)
    description: str | None = Field(None, max_length=1000)
    metadata: dict | None = None
    is_active: bool | None = None


class ProductResponse(BaseModel):
    """Schema for product response."""

    id: str
    saas_app_id: str
    stripe_product_id: str
    slug: str
    name: str
    description: str | None
    extra_data: dict | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
