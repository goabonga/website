# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Pydantic schemas for organisations API."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CreateOrganisationAdminRequest(BaseModel):
    """Request body for admin creating an organisation."""

    slug: str = Field(
        ...,
        min_length=2,
        max_length=63,
        pattern=r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$",
    )
    display_name: str = Field(..., min_length=1, max_length=255)


class UpdateOrganisationRequest(BaseModel):
    """Request body for partially updating an organisation."""

    display_name: str | None = Field(None, min_length=1, max_length=255)
    is_active: bool | None = None


class OrganisationResponse(BaseModel):
    """Response for a single organisation."""

    id: uuid.UUID
    slug: str
    display_name: str
    custom_domain: str | None = None
    is_active: bool
    trust_mode: str
    member_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


class MemberResponse(BaseModel):
    """Response for a single organisation member."""

    user_id: uuid.UUID
    role_id: uuid.UUID | None = None
    role_name: str
    role_display_name: str
    joined_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AddMemberRequest(BaseModel):
    """Request body for adding a member to an organisation."""

    user_id: uuid.UUID
    role_id: uuid.UUID | None = None


class UpdateMemberRequest(BaseModel):
    """Request body for updating a member's role."""

    role_id: uuid.UUID


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------


class RoleResponse(BaseModel):
    """Response for a single organisation role."""

    id: uuid.UUID
    name: str
    display_name: str
    description: str | None = None
    scopes: list[str]
    is_system: bool
    is_default: bool
    display_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CreateRoleRequest(BaseModel):
    """Request body for creating a custom role."""

    name: str = Field(..., min_length=1, max_length=100)
    display_name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=500)
    scopes: list[str] = Field(..., min_length=1)


class UpdateRoleRequest(BaseModel):
    """Request body for updating a custom role.

    ``is_default`` toggles whether new self-registrants / auto-provisioned
    users receive this role. Setting it to ``True`` atomically clears any
    previously-default role in the same tenant.
    """

    display_name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=500)
    scopes: list[str] | None = Field(None, min_length=1)
    is_default: bool | None = None


# ---------------------------------------------------------------------------
# Trust
# ---------------------------------------------------------------------------


class TrustedSourceResponse(BaseModel):
    """Response for a single trusted source entry."""

    id: uuid.UUID
    trusted_tenant_id: uuid.UUID | None = None
    trusted_tenant_name: str | None = None
    trusted_tenant_slug: str | None = None
    is_platform: bool = False
    description: str | None = None


class TrustConfigResponse(BaseModel):
    """Response containing the full trust configuration for an org."""

    mode: str
    trusted_sources: list[TrustedSourceResponse]


class UpdateTrustModeRequest(BaseModel):
    """Request body for updating the trust mode."""

    mode: str = Field(..., min_length=1, max_length=50)


class AddTrustedSourceRequest(BaseModel):
    """Request body for adding a trusted source."""

    source_tenant_id: uuid.UUID


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class SettingsResponse(BaseModel):
    """Response containing the organisation settings dict."""

    settings: dict


class UpdateSettingsRequest(BaseModel):
    """Request body for partially updating organisation settings."""

    settings: dict


# ---------------------------------------------------------------------------
# OAuth2 Clients
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Identity Providers
# ---------------------------------------------------------------------------


class IdPResponse(BaseModel):
    """Response for a single identity provider."""

    id: uuid.UUID
    name: str
    provider_type: str
    discovery_url: str | None = None
    authorization_endpoint: str | None = None
    token_endpoint: str | None = None
    userinfo_endpoint: str | None = None
    jwks_uri: str | None = None
    client_id: str
    scopes: list[str]
    attribute_mapping: dict | None = None
    allowed_domains: list[str] | None = None
    is_active: bool
    is_default: bool
    auto_provision: bool
    allow_linking: bool
    icon_url: str | None = None
    button_text: str | None = None
    display_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CreateIdPRequest(BaseModel):
    """Request body for creating an identity provider."""

    name: str = Field(..., min_length=1, max_length=255)
    provider_type: str = Field(..., max_length=32)
    discovery_url: str | None = Field(None, max_length=2048)
    authorization_endpoint: str | None = Field(None, max_length=2048)
    token_endpoint: str | None = Field(None, max_length=2048)
    userinfo_endpoint: str | None = Field(None, max_length=2048)
    jwks_uri: str | None = Field(None, max_length=2048)
    client_id: str = Field(..., max_length=255)
    client_secret: str | None = None
    scopes: list[str] = Field(default_factory=lambda: ["openid", "profile", "email"])
    attribute_mapping: dict | None = None
    allowed_domains: list[str] | None = None
    is_active: bool = True
    is_default: bool = False
    auto_provision: bool = True
    allow_linking: bool = True
    icon_url: str | None = Field(None, max_length=2048)
    button_text: str | None = Field(None, max_length=100)
    display_order: int = 0


class UpdateIdPRequest(BaseModel):
    """Request body for partially updating an identity provider."""

    name: str | None = Field(None, min_length=1, max_length=255)
    discovery_url: str | None = Field(None, max_length=2048)
    authorization_endpoint: str | None = Field(None, max_length=2048)
    token_endpoint: str | None = Field(None, max_length=2048)
    userinfo_endpoint: str | None = Field(None, max_length=2048)
    jwks_uri: str | None = Field(None, max_length=2048)
    client_id: str | None = Field(None, max_length=255)
    client_secret: str | None = None
    scopes: list[str] | None = None
    attribute_mapping: dict | None = None
    allowed_domains: list[str] | None = None
    is_active: bool | None = None
    is_default: bool | None = None
    auto_provision: bool | None = None
    allow_linking: bool | None = None
    icon_url: str | None = Field(None, max_length=2048)
    button_text: str | None = Field(None, max_length=100)
    display_order: int | None = None


# ---------------------------------------------------------------------------
# Branding
# ---------------------------------------------------------------------------


class BrandingResponse(BaseModel):
    """Response for tenant branding configuration."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    logo_url: str | None = None
    logo_dark_url: str | None = None
    favicon_url: str | None = None
    primary_color: str
    secondary_color: str
    accent_color: str
    background_color: str
    surface_color: str
    text_color: str
    text_muted_color: str
    error_color: str
    success_color: str
    border_color: str
    warning_color: str
    info_color: str
    input_background_color: str | None = None
    input_focus_background_color: str | None = None
    input_border_color: str | None = None
    input_focus_border_color: str | None = None
    input_text_color: str | None = None
    font_family: str
    font_url: str | None = None
    custom_css: str | None = None
    custom_js: str | None = None
    show_powered_by: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UpdateBrandingRequest(BaseModel):
    """Request body for updating tenant branding."""

    logo_url: str | None = Field(None, max_length=2048)
    logo_dark_url: str | None = Field(None, max_length=2048)
    favicon_url: str | None = Field(None, max_length=2048)
    primary_color: str | None = Field(None, min_length=4, max_length=7)
    secondary_color: str | None = Field(None, min_length=4, max_length=7)
    accent_color: str | None = Field(None, min_length=4, max_length=7)
    background_color: str | None = Field(None, min_length=4, max_length=7)
    surface_color: str | None = Field(None, min_length=4, max_length=7)
    text_color: str | None = Field(None, min_length=4, max_length=7)
    text_muted_color: str | None = Field(None, min_length=4, max_length=7)
    error_color: str | None = Field(None, min_length=4, max_length=7)
    success_color: str | None = Field(None, min_length=4, max_length=7)
    border_color: str | None = Field(None, min_length=4, max_length=7)
    warning_color: str | None = Field(None, min_length=4, max_length=7)
    info_color: str | None = Field(None, min_length=4, max_length=7)
    input_background_color: str | None = Field(None, min_length=4, max_length=7)
    input_focus_background_color: str | None = Field(None, min_length=4, max_length=7)
    input_border_color: str | None = Field(None, min_length=4, max_length=7)
    input_focus_border_color: str | None = Field(None, min_length=4, max_length=7)
    input_text_color: str | None = Field(None, min_length=4, max_length=7)
    font_family: str | None = Field(None, max_length=255)
    font_url: str | None = Field(None, max_length=2048)
    custom_css: str | None = None
    custom_js: str | None = None
    show_powered_by: bool | None = None


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


class TemplateResponse(BaseModel):
    """Response for a tenant template."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    template_name: str
    content: str
    is_active: bool
    description: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UpdateTemplateRequest(BaseModel):
    """Request body for creating or updating a tenant template."""

    content: str = Field(..., min_length=1)
    description: str | None = Field(None, max_length=500)
    is_active: bool = True


# ---------------------------------------------------------------------------
# Registration Fields
# ---------------------------------------------------------------------------


class RegistrationFieldsResponse(BaseModel):
    """Registration field visibility toggles."""

    fields: dict[str, bool]


class UpdateRegistrationFieldsRequest(BaseModel):
    """Request body for updating registration field toggles."""

    fields: dict[str, bool]


# ---------------------------------------------------------------------------
# Profile Fields
# ---------------------------------------------------------------------------


class ProfileFieldsResponse(BaseModel):
    """Profile field visibility toggles."""

    fields: dict[str, bool]


class UpdateProfileFieldsRequest(BaseModel):
    """Request body for updating profile field toggles."""

    fields: dict[str, bool]


# ---------------------------------------------------------------------------
# Email Sender
# ---------------------------------------------------------------------------


class EmailSenderResponse(BaseModel):
    """Email sender configuration."""

    email_sender_address: str | None = None
    email_sender_name: str | None = None


class UpdateEmailSenderRequest(BaseModel):
    """Request body for updating email sender configuration."""

    email_sender_address: str | None = None
    email_sender_name: str | None = None


# ---------------------------------------------------------------------------
# Custom Domain
# ---------------------------------------------------------------------------


class CustomDomainResponse(BaseModel):
    """Custom domain of an organisation and the state of its verification."""

    custom_domain: str | None = None
    status: str | None = None
    error: str | None = None
    verified_at: datetime | None = None
    ssl_at: datetime | None = None
    checked_at: datetime | None = None


class SetCustomDomainRequest(BaseModel):
    """Request body for setting the custom domain of an organisation."""

    custom_domain: str = Field(..., min_length=1, max_length=253)


# ---------------------------------------------------------------------------
# Allowed Scopes
# ---------------------------------------------------------------------------


class AllowedScopesResponse(BaseModel):
    """Allowed scopes for tenant custom roles."""

    allowed_scopes: list[str] | None = None


class UpdateAllowedScopesRequest(BaseModel):
    """Request body for updating allowed scopes. None = all allowed."""

    allowed_scopes: list[str] | None = None


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------


class WebhookResponse(BaseModel):
    """Response for a single webhook (secret never returned)."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    url: str
    events: list[str]
    headers: dict[str, str]
    is_active: bool
    last_triggered_at: datetime | None = None
    last_status_code: int | None = None
    last_error: str | None = None
    failure_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WebhookCreateResponse(BaseModel):
    """Response after creating a webhook; includes the signing secret once."""

    webhook: WebhookResponse
    secret: str = Field(..., description="HMAC signing secret. Stored only once; save it now.")


class WebhookSecretResponse(BaseModel):
    """Response from rotate-secret; contains the new signing secret."""

    secret: str


class CreateWebhookRequest(BaseModel):
    """Request body for creating a webhook."""

    name: str = Field(..., min_length=1, max_length=100)
    url: str = Field(..., min_length=1, max_length=2048)
    events: list[str] = Field(..., min_length=1)
    headers: dict[str, str] | None = None
    is_active: bool = True


class UpdateWebhookRequest(BaseModel):
    """Request body for partially updating a webhook."""

    name: str | None = Field(None, min_length=1, max_length=100)
    url: str | None = Field(None, min_length=1, max_length=2048)
    events: list[str] | None = None
    headers: dict[str, str] | None = None
    is_active: bool | None = None


class WebhookEventsCatalogResponse(BaseModel):
    """Catalog of subscribable event keys grouped by prefix."""

    groups: dict[str, list[str]]


class WebhookDeliveryResponse(BaseModel):
    """Response for a single delivery attempt chain."""

    id: uuid.UUID
    webhook_id: uuid.UUID
    event: str
    status: str
    attempt: int
    max_attempts: int
    request_url: str
    request_headers: dict[str, str]
    response_status: int | None = None
    response_headers: dict[str, str] | None = None
    response_body: str | None = None
    error: str | None = None
    duration_ms: int | None = None
    delivered_at: datetime | None = None
    next_retry_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class WebhookDeliveryEnqueuedResponse(BaseModel):
    """Response returned when a delivery is enqueued (test or replay)."""

    delivery_id: uuid.UUID
