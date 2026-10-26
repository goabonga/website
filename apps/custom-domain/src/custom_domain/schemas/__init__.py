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
    DomainStatusResponse,
    DomainUpdate,
    EventHistoryItem,
    EventHistoryResponse,
    ProgressStep,
)
from custom_domain.schemas.template import (
    AvailableTemplate,
    AvailableTemplateListResponse,
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
    "AvailableTemplate",
    "AvailableTemplateListResponse",
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
    "DomainStatusResponse",
    "DomainUpdate",
    "EventHistoryItem",
    "EventHistoryResponse",
    "ProgressStep",
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
