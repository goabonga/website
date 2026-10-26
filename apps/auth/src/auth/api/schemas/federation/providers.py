# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Federation provider listing request and response schemas."""

from pydantic import BaseModel, ConfigDict


class IdentityProviderResponse(BaseModel):
    """Identity provider response for listing available IdPs."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    provider_type: str
    icon_url: str | None
    button_text: str | None


class ProvidersListResponse(BaseModel):
    """Response with list of identity providers for a tenant."""

    tenant_slug: str
    providers: list[IdentityProviderResponse]
    local_login_enabled: bool = True
