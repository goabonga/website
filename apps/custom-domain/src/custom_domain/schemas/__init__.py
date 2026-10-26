# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Pydantic schemas."""

from custom_domain.schemas.client import (
    ClientCreate,
    ClientListItem,
    ClientListResponse,
    ClientResponse,
    ClientUpdate,
)
from custom_domain.schemas.template import (
    ReprovisionError,
    TemplateCreate,
    TemplateListItem,
    TemplateListResponse,
    TemplateReprovisionRequest,
    TemplateReprovisionResponse,
    TemplateResponse,
    TemplateUpdate,
    TemplateValidateRequest,
    TemplateValidateResponse,
)

__all__ = [
    "ClientCreate",
    "ClientListItem",
    "ClientListResponse",
    "ClientResponse",
    "ClientUpdate",
    "ReprovisionError",
    "TemplateCreate",
    "TemplateListItem",
    "TemplateListResponse",
    "TemplateReprovisionRequest",
    "TemplateReprovisionResponse",
    "TemplateResponse",
    "TemplateUpdate",
    "TemplateValidateRequest",
    "TemplateValidateResponse",
]
