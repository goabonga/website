# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""OAuth2 request/response schemas."""

from pydantic import BaseModel, Field


class AuthorizeRequest(BaseModel):
    """OAuth2 authorization request parameters."""

    response_type: str = Field(..., description="Must be 'code' for authorization code flow")
    client_id: str = Field(..., description="The client identifier")
    redirect_uri: str = Field(..., description="The redirect URI")
    scope: str | None = Field(None, description="Space-separated list of scopes")
    state: str | None = Field(None, description="Opaque value for CSRF protection")
    code_challenge: str | None = Field(None, description="PKCE code challenge")
    code_challenge_method: str | None = Field(
        None, description="PKCE challenge method (S256 or plain)"
    )
    nonce: str | None = Field(None, description="OIDC nonce for ID token")
    prompt: str | None = Field(
        None, description="Space-separated list of prompts (login, consent, none)"
    )


class TokenRequest(BaseModel):
    """OAuth2 token request parameters."""

    grant_type: str = Field(..., description="The grant type (authorization_code, refresh_token)")
    code: str | None = Field(
        None, description="The authorization code (for authorization_code grant)"
    )
    redirect_uri: str | None = Field(
        None, description="The redirect URI (for authorization_code grant)"
    )
    code_verifier: str | None = Field(
        None, description="PKCE code verifier (for authorization_code grant)"
    )
    refresh_token: str | None = Field(
        None, description="The refresh token (for refresh_token grant)"
    )
    scope: str | None = Field(
        None, description="Space-separated list of scopes (for refresh_token grant)"
    )


class TokenResponse(BaseModel):
    """OAuth2 token response."""

    access_token: str = Field(..., description="The access token")
    token_type: str = Field(default="Bearer", description="The token type")
    expires_in: int = Field(..., description="Token lifetime in seconds")
    refresh_token: str | None = Field(None, description="The refresh token")
    scope: str | None = Field(None, description="Space-separated list of granted scopes")
    id_token: str | None = Field(
        default=None, description="OIDC ID token (if openid scope requested)"
    )


class TokenErrorResponse(BaseModel):
    """OAuth2 token error response."""

    error: str = Field(..., description="Error code")
    error_description: str | None = Field(None, description="Human-readable error description")


class IntrospectionResponse(BaseModel):
    """Token introspection response (RFC 7662)."""

    active: bool = Field(..., description="Whether the token is active")
    scope: str | None = Field(default=None, description="Space-separated list of scopes")
    client_id: str | None = Field(default=None, description="Client identifier")
    username: str | None = Field(
        default=None, description="Human-readable identifier for the resource owner"
    )
    token_type: str | None = Field(default=None, description="Type of the token")
    exp: int | None = Field(default=None, description="Token expiration timestamp")
    iat: int | None = Field(default=None, description="Token issue timestamp")
    nbf: int | None = Field(default=None, description="Token not-before timestamp")
    sub: str | None = Field(default=None, description="Subject of the token")
    aud: str | None = Field(default=None, description="Audience of the token")
    iss: str | None = Field(default=None, description="Issuer of the token")
    jti: str | None = Field(default=None, description="Token identifier")


class AuthorizeResponse(BaseModel):
    """OAuth2 authorization response (for JSON API)."""

    code: str = Field(..., description="The authorization code")
    state: str | None = Field(None, description="The state parameter if provided")


class AuthorizeErrorResponse(BaseModel):
    """OAuth2 authorization error response."""

    error: str = Field(..., description="Error code")
    error_description: str | None = Field(None, description="Human-readable error description")
    state: str | None = Field(None, description="The state parameter if provided")


class ConsentRequest(BaseModel):
    """Consent form submission."""

    consent: str = Field(..., description="'allow' or 'deny'")
    client_id: str = Field(..., description="The client identifier")
    redirect_uri: str = Field(..., description="The redirect URI")
    scope: str | None = Field(None, description="Space-separated list of scopes")
    state: str | None = Field(None, description="The state parameter")
    code_challenge: str | None = Field(None, description="PKCE code challenge")
    code_challenge_method: str | None = Field(None, description="PKCE challenge method")
    nonce: str | None = Field(None, description="OIDC nonce")


class DeviceAuthorizationRequest(BaseModel):
    """Device authorization request (RFC 8628)."""

    client_id: str = Field(..., description="The client identifier")
    scope: str | None = Field(None, description="Space-separated list of scopes")


class DeviceAuthorizationResponse(BaseModel):
    """Device authorization response (RFC 8628)."""

    device_code: str = Field(..., description="The device verification code")
    user_code: str = Field(..., description="The end-user verification code")
    verification_uri: str = Field(..., description="The verification URI")
    verification_uri_complete: str | None = Field(
        None, description="The verification URI with user_code included"
    )
    expires_in: int = Field(..., description="Lifetime in seconds of the device_code and user_code")
    interval: int = Field(default=5, description="Minimum polling interval in seconds")


class DeviceUserCodeRequest(BaseModel):
    """User code verification form submission."""

    user_code: str = Field(..., description="The user code entered by the user")


class DeviceConsentRequest(BaseModel):
    """Device consent form submission."""

    user_code: str = Field(..., description="The user code")
    consent: str = Field(..., description="'allow' or 'deny'")


# Standard OAuth2 error codes
class OAuth2Error:
    """OAuth2 error codes per RFC 6749."""

    # Authorization errors
    INVALID_REQUEST = "invalid_request"
    UNAUTHORIZED_CLIENT = "unauthorized_client"
    ACCESS_DENIED = "access_denied"
    UNSUPPORTED_RESPONSE_TYPE = "unsupported_response_type"
    INVALID_SCOPE = "invalid_scope"
    SERVER_ERROR = "server_error"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"

    # Token errors
    INVALID_CLIENT = "invalid_client"
    INVALID_GRANT = "invalid_grant"
    UNSUPPORTED_GRANT_TYPE = "unsupported_grant_type"

    # Device flow errors (RFC 8628)
    AUTHORIZATION_PENDING = "authorization_pending"
    SLOW_DOWN = "slow_down"
    EXPIRED_TOKEN = "expired_token"

    # Resource access errors (RFC 6750)
    INSUFFICIENT_SCOPE = "insufficient_scope"


class PARRequest(BaseModel):
    """Pushed Authorization Request (RFC 9126)."""

    response_type: str = Field(..., description="Must be 'code' for authorization code flow")
    client_id: str = Field(..., description="The client identifier")
    redirect_uri: str = Field(..., description="The redirect URI")
    scope: str | None = Field(None, description="Space-separated list of scopes")
    state: str | None = Field(None, description="Opaque value for CSRF protection")
    code_challenge: str | None = Field(None, description="PKCE code challenge")
    code_challenge_method: str | None = Field(
        None, description="PKCE challenge method (S256 or plain)"
    )
    nonce: str | None = Field(None, description="OIDC nonce for ID token")
    prompt: str | None = Field(
        None, description="Space-separated list of prompts (login, consent, none)"
    )


class PARResponse(BaseModel):
    """Pushed Authorization Request response (RFC 9126)."""

    request_uri: str = Field(..., description="The request URI to use in authorization request")
    expires_in: int = Field(..., description="Lifetime of the request_uri in seconds")


# Token Exchange (RFC 8693)
class TokenExchangeRequest(BaseModel):
    """Token Exchange request (RFC 8693)."""

    grant_type: str = Field(
        ...,
        description="Must be 'urn:ietf:params:oauth:grant-type:token-exchange'",
    )
    subject_token: str = Field(..., description="The subject token to exchange")
    subject_token_type: str = Field(
        ...,
        description="URI indicating the type of subject_token",
    )
    actor_token: str | None = Field(
        None, description="Token representing the actor (for delegation)"
    )
    actor_token_type: str | None = Field(None, description="URI indicating the type of actor_token")
    requested_token_type: str | None = Field(
        None,
        description="URI indicating the desired type of token",
    )
    audience: str | None = Field(None, description="Logical name of the target service")
    scope: str | None = Field(None, description="Space-separated list of scopes")
    resource: str | None = Field(None, description="URI of the target resource")


class TokenExchangeResponse(BaseModel):
    """Token Exchange response (RFC 8693)."""

    access_token: str = Field(..., description="The issued token")
    issued_token_type: str = Field(..., description="URI indicating the type of issued token")
    token_type: str = Field(default="Bearer", description="The token type")
    expires_in: int = Field(..., description="Token lifetime in seconds")
    scope: str | None = Field(None, description="Space-separated list of granted scopes")
    refresh_token: str | None = Field(None, description="Optional refresh token")


# PKCE error messages
PKCE_REQUIRED_ERROR = "PKCE is required for this client"
PKCE_INVALID_METHOD_ERROR = "Invalid code_challenge_method. Use S256."
PKCE_MISSING_CHALLENGE_ERROR = "code_challenge is required when using PKCE"
