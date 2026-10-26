# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""OIDC Discovery / OAuth 2.0 Authorization Server Metadata schemas."""

from pydantic import BaseModel, Field


class OpenIDConfigurationResponse(BaseModel):
    """OpenID Connect Discovery 1.0 / RFC 8414 provider metadata response."""

    issuer: str = Field(..., description="The issuer identifier URL")
    authorization_endpoint: str = Field(..., description="URL of the authorization endpoint")
    token_endpoint: str = Field(..., description="URL of the token endpoint")
    userinfo_endpoint: str = Field(..., description="URL of the UserInfo endpoint")
    jwks_uri: str = Field(..., description="URL of the JWK Set document")
    revocation_endpoint: str = Field(
        ..., description="URL of the token revocation endpoint (RFC 7009)"
    )
    introspection_endpoint: str = Field(
        ..., description="URL of the token introspection endpoint (RFC 7662)"
    )
    device_authorization_endpoint: str = Field(
        ..., description="URL of the device authorization endpoint (RFC 8628)"
    )
    pushed_authorization_request_endpoint: str = Field(
        ..., description="URL of the pushed authorization request endpoint (RFC 9126)"
    )
    registration_endpoint: str = Field(
        ..., description="URL of the dynamic client registration endpoint"
    )
    scopes_supported: list[str] = Field(..., description="Supported OAuth2 scopes")
    response_types_supported: list[str] = Field(..., description="Supported OAuth2 response types")
    response_modes_supported: list[str] = Field(..., description="Supported OAuth2 response modes")
    grant_types_supported: list[str] = Field(..., description="Supported OAuth2 grant types")
    subject_types_supported: list[str] = Field(..., description="Supported OIDC subject types")
    id_token_signing_alg_values_supported: list[str] = Field(
        ..., description="JWS signing algorithms supported for ID tokens"
    )
    token_endpoint_auth_methods_supported: list[str] = Field(
        ..., description="Supported client authentication methods at the token endpoint"
    )
    code_challenge_methods_supported: list[str] = Field(
        ..., description="Supported PKCE code challenge methods (RFC 7636)"
    )
    claims_supported: list[str] = Field(..., description="Supported claim names")
    request_parameter_supported: bool = Field(
        ..., description="Whether the `request` parameter is supported"
    )
    request_uri_parameter_supported: bool = Field(
        ..., description="Whether the `request_uri` parameter is supported"
    )
    require_request_uri_registration: bool = Field(
        ..., description="Whether `request_uri` values must be pre-registered"
    )
