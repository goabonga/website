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
from custom_domain.schemas.domain import (
    DomainActionResponse,
    DomainCreate,
    DomainCreateResponse,
    DomainListItem,
    DomainListResponse,
    DomainLookupResponse,
    DomainResponse,
    DomainUpdate,
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
    "DomainActionResponse",
    "DomainCreate",
    "DomainCreateResponse",
    "DomainListItem",
    "DomainListResponse",
    "DomainLookupResponse",
    "DomainResponse",
    "DomainUpdate",
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
