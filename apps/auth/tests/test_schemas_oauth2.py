# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.api.schemas.oauth2 — OAuth2 request/response schemas."""

import pytest
from auth.api.schemas.oauth2 import (
    PKCE_INVALID_METHOD_ERROR,
    PKCE_MISSING_CHALLENGE_ERROR,
    PKCE_REQUIRED_ERROR,
    AuthorizeErrorResponse,
    AuthorizeRequest,
    AuthorizeResponse,
    ConsentRequest,
    DeviceAuthorizationRequest,
    DeviceAuthorizationResponse,
    DeviceConsentRequest,
    DeviceUserCodeRequest,
    OAuth2Error,
    PARRequest,
    PARResponse,
    TokenErrorResponse,
    TokenExchangeRequest,
    TokenExchangeResponse,
    TokenRequest,
    TokenResponse,
)
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# AuthorizeRequest
# ---------------------------------------------------------------------------


class TestAuthorizeRequest:
    def test_valid(self):
        r = AuthorizeRequest(
            response_type="code",
            client_id="c1",
            redirect_uri="https://app.example.com/cb",
        )
        assert r.response_type == "code"
        assert r.scope is None
        assert r.state is None
        assert r.code_challenge is None
        assert r.nonce is None
        assert r.prompt is None

    def test_all_fields(self):
        r = AuthorizeRequest(
            response_type="code",
            client_id="c1",
            redirect_uri="https://app.example.com/cb",
            scope="openid profile",
            state="xyz",
            code_challenge="abc",
            code_challenge_method="S256",
            nonce="n1",
            prompt="consent",
        )
        assert r.scope == "openid profile"
        assert r.code_challenge_method == "S256"

    def test_missing_required_raises(self):
        with pytest.raises(ValidationError):
            AuthorizeRequest(response_type="code", client_id="c1")


# ---------------------------------------------------------------------------
# TokenRequest
# ---------------------------------------------------------------------------


class TestTokenRequest:
    def test_authorization_code_grant(self):
        r = TokenRequest(
            grant_type="authorization_code",
            code="abc",
            redirect_uri="https://app.example.com/cb",
            code_verifier="verifier",
        )
        assert r.grant_type == "authorization_code"
        assert r.refresh_token is None

    def test_refresh_token_grant(self):
        r = TokenRequest(grant_type="refresh_token", refresh_token="rt_abc")
        assert r.refresh_token == "rt_abc"
        assert r.code is None

    def test_missing_grant_type_raises(self):
        with pytest.raises(ValidationError):
            TokenRequest()


# ---------------------------------------------------------------------------
# TokenResponse
# ---------------------------------------------------------------------------


class TestTokenResponse:
    def test_minimal(self):
        r = TokenResponse(access_token="at_123", expires_in=3600)
        assert r.access_token == "at_123"
        assert r.token_type == "Bearer"
        assert r.refresh_token is None
        assert r.scope is None
        assert r.id_token is None

    def test_full(self):
        r = TokenResponse(
            access_token="at_123",
            expires_in=3600,
            refresh_token="rt_123",
            scope="openid",
            id_token="id.jwt.here",
        )
        assert r.refresh_token == "rt_123"
        assert r.id_token == "id.jwt.here"

    def test_missing_required_raises(self):
        with pytest.raises(ValidationError):
            TokenResponse(access_token="at_123")


# ---------------------------------------------------------------------------
# TokenErrorResponse
# ---------------------------------------------------------------------------


class TestTokenErrorResponse:
    def test_error_only(self):
        r = TokenErrorResponse(error="invalid_grant")
        assert r.error == "invalid_grant"
        assert r.error_description is None

    def test_with_description(self):
        r = TokenErrorResponse(error="invalid_grant", error_description="Expired")
        assert r.error_description == "Expired"


# ---------------------------------------------------------------------------
# AuthorizeResponse / AuthorizeErrorResponse
# ---------------------------------------------------------------------------


class TestAuthorizeResponse:
    def test_valid(self):
        r = AuthorizeResponse(code="abc123")
        assert r.code == "abc123"
        assert r.state is None

    def test_with_state(self):
        r = AuthorizeResponse(code="abc123", state="xyz")
        assert r.state == "xyz"


class TestAuthorizeErrorResponse:
    def test_valid(self):
        r = AuthorizeErrorResponse(error="access_denied")
        assert r.error == "access_denied"
        assert r.error_description is None
        assert r.state is None

    def test_full(self):
        r = AuthorizeErrorResponse(
            error="access_denied",
            error_description="User denied",
            state="xyz",
        )
        assert r.error_description == "User denied"


# ---------------------------------------------------------------------------
# ConsentRequest
# ---------------------------------------------------------------------------


class TestConsentRequest:
    def test_valid(self):
        r = ConsentRequest(
            consent="allow",
            client_id="c1",
            redirect_uri="https://app.example.com/cb",
        )
        assert r.consent == "allow"
        assert r.scope is None

    def test_deny(self):
        r = ConsentRequest(
            consent="deny",
            client_id="c1",
            redirect_uri="https://app.example.com/cb",
        )
        assert r.consent == "deny"

    def test_all_fields(self):
        r = ConsentRequest(
            consent="allow",
            client_id="c1",
            redirect_uri="https://app.example.com/cb",
            scope="openid",
            state="xyz",
            code_challenge="ch",
            code_challenge_method="S256",
            nonce="n1",
        )
        assert r.code_challenge == "ch"

    def test_missing_required_raises(self):
        with pytest.raises(ValidationError):
            ConsentRequest(consent="allow", client_id="c1")


# ---------------------------------------------------------------------------
# Device flow schemas
# ---------------------------------------------------------------------------


class TestDeviceAuthorizationRequest:
    def test_valid(self):
        r = DeviceAuthorizationRequest(client_id="c1")
        assert r.client_id == "c1"
        assert r.scope is None

    def test_with_scope(self):
        r = DeviceAuthorizationRequest(client_id="c1", scope="openid")
        assert r.scope == "openid"


class TestDeviceAuthorizationResponse:
    def test_valid(self):
        r = DeviceAuthorizationResponse(
            device_code="dc_123",
            user_code="ABCD-EFGH",
            verification_uri="https://auth.example.com/device",
            expires_in=600,
        )
        assert r.device_code == "dc_123"
        assert r.interval == 5  # default
        assert r.verification_uri_complete is None

    def test_custom_interval(self):
        r = DeviceAuthorizationResponse(
            device_code="dc_123",
            user_code="ABCD-EFGH",
            verification_uri="https://auth.example.com/device",
            expires_in=600,
            interval=10,
            verification_uri_complete="https://auth.example.com/device?code=ABCD-EFGH",
        )
        assert r.interval == 10
        assert r.verification_uri_complete is not None


class TestDeviceUserCodeRequest:
    def test_valid(self):
        r = DeviceUserCodeRequest(user_code="ABCD-EFGH")
        assert r.user_code == "ABCD-EFGH"

    def test_missing_raises(self):
        with pytest.raises(ValidationError):
            DeviceUserCodeRequest()


class TestDeviceConsentRequest:
    def test_valid(self):
        r = DeviceConsentRequest(user_code="ABCD-EFGH", consent="allow")
        assert r.user_code == "ABCD-EFGH"
        assert r.consent == "allow"


# ---------------------------------------------------------------------------
# OAuth2Error constants
# ---------------------------------------------------------------------------


class TestOAuth2Error:
    def test_authorization_errors(self):
        assert OAuth2Error.INVALID_REQUEST == "invalid_request"
        assert OAuth2Error.UNAUTHORIZED_CLIENT == "unauthorized_client"
        assert OAuth2Error.ACCESS_DENIED == "access_denied"
        assert OAuth2Error.UNSUPPORTED_RESPONSE_TYPE == "unsupported_response_type"
        assert OAuth2Error.INVALID_SCOPE == "invalid_scope"
        assert OAuth2Error.SERVER_ERROR == "server_error"
        assert OAuth2Error.TEMPORARILY_UNAVAILABLE == "temporarily_unavailable"

    def test_token_errors(self):
        assert OAuth2Error.INVALID_CLIENT == "invalid_client"
        assert OAuth2Error.INVALID_GRANT == "invalid_grant"
        assert OAuth2Error.UNSUPPORTED_GRANT_TYPE == "unsupported_grant_type"

    def test_device_flow_errors(self):
        assert OAuth2Error.AUTHORIZATION_PENDING == "authorization_pending"
        assert OAuth2Error.SLOW_DOWN == "slow_down"
        assert OAuth2Error.EXPIRED_TOKEN == "expired_token"

    def test_resource_errors(self):
        assert OAuth2Error.INSUFFICIENT_SCOPE == "insufficient_scope"


# ---------------------------------------------------------------------------
# PAR schemas
# ---------------------------------------------------------------------------


class TestPARRequest:
    def test_valid(self):
        r = PARRequest(
            response_type="code",
            client_id="c1",
            redirect_uri="https://app.example.com/cb",
        )
        assert r.response_type == "code"

    def test_all_fields(self):
        r = PARRequest(
            response_type="code",
            client_id="c1",
            redirect_uri="https://app.example.com/cb",
            scope="openid",
            state="xyz",
            code_challenge="ch",
            code_challenge_method="S256",
            nonce="n1",
            prompt="login",
        )
        assert r.prompt == "login"


class TestPARResponse:
    def test_valid(self):
        r = PARResponse(request_uri="urn:ietf:params:oauth:request_uri:abc", expires_in=60)
        assert r.request_uri.startswith("urn:")
        assert r.expires_in == 60


# ---------------------------------------------------------------------------
# Token Exchange schemas
# ---------------------------------------------------------------------------


class TestTokenExchangeRequest:
    def test_minimal(self):
        r = TokenExchangeRequest(
            grant_type="urn:ietf:params:oauth:grant-type:token-exchange",
            subject_token="st_abc",
            subject_token_type="urn:ietf:params:oauth:token-type:access_token",
        )
        assert r.actor_token is None
        assert r.audience is None
        assert r.resource is None

    def test_full(self):
        r = TokenExchangeRequest(
            grant_type="urn:ietf:params:oauth:grant-type:token-exchange",
            subject_token="st_abc",
            subject_token_type="urn:ietf:params:oauth:token-type:access_token",
            actor_token="at_xyz",
            actor_token_type="urn:ietf:params:oauth:token-type:access_token",
            requested_token_type="urn:ietf:params:oauth:token-type:access_token",
            audience="my-service",
            scope="openid",
            resource="https://api.example.com",
        )
        assert r.actor_token == "at_xyz"
        assert r.audience == "my-service"


class TestTokenExchangeResponse:
    def test_minimal(self):
        r = TokenExchangeResponse(
            access_token="at_123",
            issued_token_type="urn:ietf:params:oauth:token-type:access_token",
            expires_in=3600,
        )
        assert r.token_type == "Bearer"
        assert r.scope is None
        assert r.refresh_token is None

    def test_full(self):
        r = TokenExchangeResponse(
            access_token="at_123",
            issued_token_type="urn:ietf:params:oauth:token-type:access_token",
            expires_in=3600,
            scope="openid",
            refresh_token="rt_123",
        )
        assert r.refresh_token == "rt_123"


# ---------------------------------------------------------------------------
# PKCE constants
# ---------------------------------------------------------------------------


class TestPKCEConstants:
    def test_pkce_required_error(self):
        assert "PKCE" in PKCE_REQUIRED_ERROR

    def test_pkce_invalid_method_error(self):
        assert "S256" in PKCE_INVALID_METHOD_ERROR

    def test_pkce_missing_challenge_error(self):
        assert "code_challenge" in PKCE_MISSING_CHALLENGE_ERROR
