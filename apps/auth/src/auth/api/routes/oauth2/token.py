# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""OAuth2 token endpoint."""

import base64
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import (
    get_auth_service,
    get_db,
    get_device_code_service,
    get_mfa_service,
    get_oauth2_client_service,
    get_token_exchange_service,
    get_token_service,
)
from auth.api.schemas.oauth2 import OAuth2Error, TokenErrorResponse, TokenResponse
from auth.db.models.oauth2 import DeviceCodeStatus
from auth.db.models.tenant import WebhookEvent
from auth.services.auth import AuthService
from auth.services.device_code import DeviceCodeService
from auth.services.issuer import get_issuer_from_context
from auth.services.mfa import MFAService
from auth.services.oauth2_client import OAuth2ClientService
from auth.services.pkce import is_valid_code_verifier, verify_code_challenge
from auth.services.token import TokenService
from auth.services.token_exchange import (
    TOKEN_EXCHANGE_GRANT_TYPE,
    TokenExchangeError,
    TokenExchangeService,
)
from auth.services.webhook import safe_dispatch as dispatch_webhook_event

logger = logging.getLogger(__name__)

router = APIRouter()

# Device authorization grant type
DEVICE_CODE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"


def _parse_basic_auth(authorization: str | None) -> tuple[str | None, str | None]:
    """Parse Basic authentication header.

    Args:
        authorization: Authorization header value.

    Returns:
        Tuple of (client_id, client_secret) or (None, None).
    """
    if not authorization or not authorization.startswith("Basic "):
        return None, None

    try:
        encoded = authorization[6:]
        decoded = base64.b64decode(encoded).decode("utf-8")
        client_id, client_secret = decoded.split(":", 1)
        return client_id, client_secret
    except (ValueError, UnicodeDecodeError):
        return None, None


def _token_error(error: str, description: str) -> HTTPException:
    """Create a token error response.

    Args:
        error: Error code.
        description: Error description.

    Returns:
        HTTPException with error details.
    """
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=TokenErrorResponse(
            error=error,
            error_description=description,
        ).model_dump(),
    )


@router.post(
    "/token",
    response_model=TokenResponse,
    responses={
        400: {"model": TokenErrorResponse, "description": "Token error"},
        401: {"model": TokenErrorResponse, "description": "Invalid client"},
    },
)
async def token_endpoint(
    grant_type: Annotated[str, Form()],
    db: Annotated[AsyncSession, Depends(get_db)],
    oauth2_service: Annotated[OAuth2ClientService, Depends(get_oauth2_client_service)],
    token_service: Annotated[TokenService, Depends(get_token_service)],
    device_service: Annotated[DeviceCodeService, Depends(get_device_code_service)],
    token_exchange_service: Annotated[TokenExchangeService, Depends(get_token_exchange_service)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    mfa_service: Annotated[MFAService | None, Depends(get_mfa_service)] = None,
    authorization: Annotated[str | None, Header()] = None,
    client_id: Annotated[str | None, Form()] = None,
    client_secret: Annotated[str | None, Form()] = None,
    code: Annotated[str | None, Form()] = None,
    redirect_uri: Annotated[str | None, Form()] = None,
    code_verifier: Annotated[str | None, Form()] = None,
    refresh_token: Annotated[str | None, Form()] = None,
    scope: Annotated[str | None, Form()] = None,
    device_code: Annotated[str | None, Form()] = None,
    # Resource Owner Password Credentials (RFC 6749) parameters
    username: Annotated[str | None, Form()] = None,
    password: Annotated[str | None, Form()] = None,
    otp: Annotated[str | None, Form()] = None,
    # Token Exchange (RFC 8693) parameters
    subject_token: Annotated[str | None, Form()] = None,
    subject_token_type: Annotated[str | None, Form()] = None,
    actor_token: Annotated[str | None, Form()] = None,
    actor_token_type: Annotated[str | None, Form()] = None,
    requested_token_type: Annotated[str | None, Form()] = None,
    audience: Annotated[str | None, Form()] = None,
    resource: Annotated[str | None, Form()] = None,
) -> TokenResponse:
    """Issue OAuth2 access tokens for all supported grant types.

    This is the central token endpoint of the authorization server. It accepts
    `application/x-www-form-urlencoded` POST bodies and dispatches to the
    appropriate grant-type handler. Confidential clients authenticate via HTTP
    Basic (RFC 6749 §2.3.1) or by sending `client_id` and `client_secret` as
    form parameters. Public clients omit the secret and MUST use PKCE
    (`code_verifier`) with the `authorization_code` grant. A successful response
    always contains `access_token`, `token_type`, and `expires_in`; an
    `id_token` is added when the `openid` scope was granted (OpenID Connect
    Core §3.1.3.3). Errors follow RFC 6749 §5.2 (`invalid_grant`,
    `invalid_client`, `unsupported_grant_type`, etc.) and are returned as JSON
    with HTTP 400 or 401.

    **Specification:**
    - RFC 6749 §3.2 / §4.1.3 — Token endpoint / Authorization Code grant
    - RFC 6749 §6 — Refresh Token grant
    - RFC 6749 §4.4 — Client Credentials grant
    - RFC 6749 §4.3 — Resource Owner Password Credentials (ROPC) grant
    - RFC 6749 §2.3 — Client Authentication (Basic + body params)
    - RFC 7636 §4.5 — PKCE `code_verifier` / `code_challenge`
    - RFC 8628 §3.4 — Device Authorization grant (polling)
    - RFC 8693 §2 — Token Exchange grant
    - OpenID Connect Core §3.1.3.3 — ID Token issuance

    **Authentication:** client credentials (HTTP Basic per RFC 6749 §2.3.1, or
    `client_id` + `client_secret` in the form body; public clients authenticate
    via PKCE with `client_id` only)

    **Example (authorization_code + PKCE):**
    ```
    curl -X POST https://auth.example.com/oauth2/token \\
      -u "my-client-id:my-client-secret" \\
      -d "grant_type=authorization_code" \\
      -d "code=SplxlOBeZQQYbYS6WxSbIA" \\
      -d "redirect_uri=https://app.example.com/callback" \\
      -d "code_verifier=dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    ```

    **Example (refresh_token):**
    ```
    curl -X POST https://auth.example.com/oauth2/token \\
      -u "my-client-id:my-client-secret" \\
      -d "grant_type=refresh_token" \\
      -d "refresh_token=tGzv3JOkF0XG5Qx2TlKWIA" \\
      -d "scope=openid profile email"
    ```

    **Example (client_credentials):**
    ```
    curl -X POST https://auth.example.com/oauth2/token \\
      -u "my-client-id:my-client-secret" \\
      -d "grant_type=client_credentials" \\
      -d "scope=api:read api:write"
    ```

    **Example (password / ROPC — legacy, avoid for new integrations):**
    ```
    curl -X POST https://auth.example.com/oauth2/token \\
      -u "my-client-id:my-client-secret" \\
      -d "grant_type=password" \\
      -d "username=alice@example.com" \\
      -d "password=s3cr3t" \\
      -d "otp=123456" \\
      -d "scope=openid profile"
    ```

    **Example (device_code — polling after device authorization):**
    ```
    curl -X POST https://auth.example.com/oauth2/token \\
      -d "grant_type=urn:ietf:params:oauth:grant-type:device_code" \\
      -d "client_id=my-public-client-id" \\
      -d "device_code=GmRhmhcxhwAzkoEqiMEg_DnyEysNkuNhszIySk9eS"
    ```

    **Example (token_exchange):**
    ```
    curl -X POST https://auth.example.com/oauth2/token \\
      -u "my-client-id:my-client-secret" \\
      -d "grant_type=urn:ietf:params:oauth:grant-type:token-exchange" \\
      -d "subject_token=eyJhbGciOiJSUzI1NiJ9..." \\
      -d "subject_token_type=urn:ietf:params:oauth:token-type:access_token" \\
      -d "audience=https://api.example.com" \\
      -d "scope=api:read"
    ```

    **Responses:**
    - `200` — token issued; body contains `access_token`, `token_type`,
      `expires_in`, and optionally `refresh_token`, `id_token`, `scope`
    - `400` — request error (`invalid_grant`, `invalid_request`,
      `invalid_scope`, `unsupported_grant_type`, `authorization_pending`,
      `slow_down`, `expired_token`)
    - `401` — client authentication failed (`invalid_client`)
    """
    logger.info("Token endpoint called: grant_type=%s, client_id=%s", grant_type, client_id)

    # Parse client credentials
    basic_client_id, basic_client_secret = _parse_basic_auth(authorization)

    # Use Basic auth if provided, otherwise form parameters
    effective_client_id = basic_client_id or client_id
    effective_client_secret = basic_client_secret or client_secret

    if not effective_client_id:
        logger.warning("Token request failed: client_id is required")
        raise _token_error(OAuth2Error.INVALID_REQUEST, "client_id is required")

    # Get client
    client = await oauth2_service.get_client_by_client_id(db, effective_client_id)
    if not client or not client.is_active:
        logger.warning("Token request failed: invalid or inactive client %s", effective_client_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=TokenErrorResponse(
                error=OAuth2Error.INVALID_CLIENT,
                error_description="Invalid client",
            ).model_dump(),
            headers={"WWW-Authenticate": "Basic"},
        )

    # Verify client secret for confidential clients
    if client.is_confidential:
        if not effective_client_secret:
            logger.warning(
                "Token request failed: client authentication required for %s", effective_client_id
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=TokenErrorResponse(
                    error=OAuth2Error.INVALID_CLIENT,
                    error_description="Client authentication required",
                ).model_dump(),
                headers={"WWW-Authenticate": "Basic"},
            )

        if not oauth2_service.verify_client_secret(client, effective_client_secret):
            logger.warning(
                "Token request failed: invalid client credentials for %s", effective_client_id
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=TokenErrorResponse(
                    error=OAuth2Error.INVALID_CLIENT,
                    error_description="Invalid client credentials",
                ).model_dump(),
                headers={"WWW-Authenticate": "Basic"},
            )

    # Validate grant type
    if not oauth2_service.validate_grant_type(client, grant_type):
        logger.warning(
            "Token request failed: unauthorized grant type %s for client %s",
            grant_type,
            effective_client_id,
        )
        raise _token_error(
            OAuth2Error.UNAUTHORIZED_CLIENT,
            f"Client is not authorized for grant_type '{grant_type}'",
        )

    logger.info(
        "Token request validated for client %s, processing grant_type=%s",
        effective_client_id,
        grant_type,
    )

    # Get issuer from tenant context (secure - derived from DB config, not Host header)
    issuer = await get_issuer_from_context(db)

    # Handle grant types
    if grant_type == "authorization_code":
        return await _handle_authorization_code(
            db=db,
            oauth2_service=oauth2_service,
            token_service=token_service,
            client=client,
            code=code,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            issuer=issuer,
        )
    elif grant_type == "refresh_token":
        return await _handle_refresh_token(
            db=db,
            token_service=token_service,
            client=client,
            refresh_token=refresh_token,
            scope=scope,
            issuer=issuer,
        )
    elif grant_type == "client_credentials":
        return await _handle_client_credentials(
            db=db,
            oauth2_service=oauth2_service,
            token_service=token_service,
            client=client,
            scope=scope,
            issuer=issuer,
        )
    elif grant_type == "password":
        return await _handle_password(
            db=db,
            oauth2_service=oauth2_service,
            auth_service=auth_service,
            token_service=token_service,
            client=client,
            username=username,
            password=password,
            otp=otp,
            scope=scope,
            issuer=issuer,
            mfa_service=mfa_service,
        )
    elif grant_type == DEVICE_CODE_GRANT_TYPE:
        return await _handle_device_code(
            db=db,
            device_service=device_service,
            token_service=token_service,
            client=client,
            device_code=device_code,
            issuer=issuer,
        )
    elif grant_type == TOKEN_EXCHANGE_GRANT_TYPE:
        return await _handle_token_exchange(
            db=db,
            token_exchange_service=token_exchange_service,
            token_service=token_service,
            client=client,
            subject_token=subject_token,
            subject_token_type=subject_token_type,
            actor_token=actor_token,
            actor_token_type=actor_token_type,
            requested_token_type=requested_token_type,
            audience=audience,
            resource=resource,
            scope=scope,
            issuer=issuer,
        )
    else:
        raise _token_error(
            OAuth2Error.UNSUPPORTED_GRANT_TYPE,
            f"Unsupported grant_type: {grant_type}",
        )


async def _handle_authorization_code(
    db: AsyncSession,
    oauth2_service: OAuth2ClientService,
    token_service: TokenService,
    client,
    code: str | None,
    redirect_uri: str | None,
    code_verifier: str | None,
    issuer: str,
) -> TokenResponse:
    """Exchange an authorization code for access, refresh, and optional ID tokens.

    Validates that the code has not expired, belongs to the requesting client,
    and that the `redirect_uri` matches the one used at authorization time. When
    the original authorization request included a `code_challenge`, the
    `code_verifier` is verified using the stored challenge method (S256 by
    default) per RFC 7636. The code is consumed (one-time use) before tokens
    are issued. An ID token is included in the response when the granted scopes
    contain `openid` (OpenID Connect Core §3.1.3.3).
    """
    logger.info("Processing authorization_code grant for client %s", client.client_id)

    if not code:
        logger.warning("Authorization code grant failed: code is required")
        raise _token_error(OAuth2Error.INVALID_REQUEST, "code is required")

    if not redirect_uri:
        logger.warning("Authorization code grant failed: redirect_uri is required")
        raise _token_error(OAuth2Error.INVALID_REQUEST, "redirect_uri is required")

    # Get authorization code
    auth_code = await oauth2_service.get_authorization_code(db, code)
    if not auth_code:
        logger.warning("Authorization code grant failed: invalid or expired code")
        raise _token_error(OAuth2Error.INVALID_GRANT, "Invalid or expired authorization code")

    # Verify client matches
    if auth_code.client_id != client.id:
        logger.warning(
            "Authorization code grant failed: code not issued to client %s", client.client_id
        )
        raise _token_error(
            OAuth2Error.INVALID_GRANT, "Authorization code was not issued to this client"
        )

    # Verify redirect_uri matches
    if auth_code.redirect_uri != redirect_uri:
        logger.warning(
            "Authorization code grant failed: redirect_uri mismatch for client %s", client.client_id
        )
        raise _token_error(OAuth2Error.INVALID_GRANT, "redirect_uri does not match")

    # Verify PKCE if code_challenge was used
    if auth_code.code_challenge:
        if not code_verifier:
            logger.warning("Authorization code grant failed: code_verifier required for PKCE")
            raise _token_error(OAuth2Error.INVALID_REQUEST, "code_verifier is required")

        if not is_valid_code_verifier(code_verifier):
            logger.warning("Authorization code grant failed: invalid code_verifier format")
            raise _token_error(OAuth2Error.INVALID_REQUEST, "Invalid code_verifier format")

        method = auth_code.code_challenge_method or "S256"
        if not verify_code_challenge(code_verifier, auth_code.code_challenge, method):
            logger.warning(
                "Authorization code grant failed: PKCE verification failed for client %s",
                client.client_id,
            )
            raise _token_error(OAuth2Error.INVALID_GRANT, "PKCE verification failed")

    # Mark code as used
    await oauth2_service.consume_authorization_code(db, auth_code)

    # Create tokens
    try:
        access_token, refresh_token, expires_in = await token_service.create_token_pair(
            db=db,
            client=client,
            scopes=auth_code.scopes,
            user_id=auth_code.user_id,
            nonce=auth_code.nonce,
            issuer=issuer,
        )
    except ValueError as e:
        logger.error("Authorization code grant failed: token creation error: %s", e)
        raise _token_error(OAuth2Error.SERVER_ERROR, str(e))

    # Create ID token if openid scope requested
    id_token = None
    if "openid" in auth_code.scopes:
        try:
            id_token = await token_service.create_id_token(
                db=db,
                client=client,
                user_id=auth_code.user_id,
                nonce=auth_code.nonce,
                access_token=access_token,
                issuer=issuer,
            )
        except ValueError:
            logger.warning(
                "ID token creation failed for client %s, continuing without it", client.client_id
            )

    logger.info(
        "ACTION: oauth2_token_authcode, user_id=%s, client_id=%s",
        auth_code.user_id,
        client.client_id,
    )

    await dispatch_webhook_event(
        db,
        tenant_id=client.tenant_id,
        event=WebhookEvent.OAUTH2_TOKEN_ISSUED,
        data={
            "grant_type": "authorization_code",
            "client_id": client.client_id,
            "client_uuid": str(client.id),
            "user_id": str(auth_code.user_id),
            "scopes": list(auth_code.scopes) if auth_code.scopes else [],
            "tenant_id": str(client.tenant_id) if client.tenant_id else None,
        },
    )

    return TokenResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=expires_in,
        refresh_token=refresh_token,
        scope=" ".join(auth_code.scopes) if auth_code.scopes else None,
        id_token=id_token,
    )


async def _handle_refresh_token(
    db: AsyncSession,
    token_service: TokenService,
    client,
    refresh_token: str | None,
    scope: str | None,
    issuer: str,
) -> TokenResponse:
    """Rotate a refresh token and issue a new access token (RFC 6749 §6).

    Validates that the refresh token is active and was issued to the requesting
    client. The caller may downscope the new token by passing a narrower `scope`
    value; requesting scopes beyond those originally granted raises
    `invalid_scope`. The old refresh token is rotated: a new refresh token is
    returned and the previous one is invalidated.
    """
    if not refresh_token:
        raise _token_error(OAuth2Error.INVALID_REQUEST, "refresh_token is required")

    # Get refresh token
    token_record = await token_service.get_refresh_token(db, refresh_token)
    if not token_record:
        raise _token_error(OAuth2Error.INVALID_GRANT, "Invalid or expired refresh token")

    # Verify client matches
    if token_record.client_id != client.id:
        raise _token_error(OAuth2Error.INVALID_GRANT, "Refresh token was not issued to this client")

    # Parse requested scopes
    requested_scopes = scope.split() if scope else None

    # Refresh tokens
    try:
        new_access_token, new_refresh_token, expires_in = await token_service.refresh_tokens(
            db=db,
            refresh_token=token_record,
            client=client,
            scopes=requested_scopes,
            issuer=issuer,
        )
    except ValueError as e:
        raise _token_error(OAuth2Error.INVALID_SCOPE, str(e))

    # Determine final scopes
    final_scopes = requested_scopes or token_record.scopes

    logger.info(
        "ACTION: oauth2_token_refresh, user_id=%s, client_id=%s",
        token_record.user_id,
        client.client_id,
    )

    await dispatch_webhook_event(
        db,
        tenant_id=client.tenant_id,
        event=WebhookEvent.OAUTH2_TOKEN_ISSUED,
        data={
            "grant_type": "refresh_token",
            "client_id": client.client_id,
            "client_uuid": str(client.id),
            "user_id": str(token_record.user_id) if token_record.user_id else None,
            "scopes": list(final_scopes) if final_scopes else [],
            "tenant_id": str(client.tenant_id) if client.tenant_id else None,
        },
    )

    return TokenResponse(
        access_token=new_access_token,
        token_type="Bearer",
        expires_in=expires_in,
        refresh_token=new_refresh_token,
        scope=" ".join(final_scopes) if final_scopes else None,
    )


async def _handle_client_credentials(
    db: AsyncSession,
    oauth2_service: OAuth2ClientService,
    token_service: TokenService,
    client,
    scope: str | None,
    issuer: str,
) -> TokenResponse:
    """Issue an access token for machine-to-machine calls (RFC 6749 §4.4).

    Only confidential clients (those with a secret) may use this grant. No user
    is associated with the resulting token. If `scope` is omitted, all scopes
    configured on the client are granted. No refresh token is issued per
    RFC 6749 §4.4.3.
    """
    # Client credentials requires a confidential client
    if not client.is_confidential:
        raise _token_error(
            OAuth2Error.UNAUTHORIZED_CLIENT,
            "client_credentials grant requires a confidential client",
        )

    # Parse and validate requested scopes
    requested_scopes = scope.split() if scope else []

    # If no scopes requested, use all allowed scopes for the client
    if not requested_scopes:
        requested_scopes = list(client.allowed_scopes)

    # Validate requested scopes against allowed scopes
    if not oauth2_service.validate_scopes(client, requested_scopes):
        raise _token_error(
            OAuth2Error.INVALID_SCOPE,
            "Requested scope exceeds client's allowed scopes",
        )

    # Create access token (no user_id for client credentials)
    try:
        access_token, _, expires_in = await token_service.create_token_pair(
            db=db,
            client=client,
            scopes=requested_scopes,
            user_id=None,  # No user for client credentials
            issuer=issuer,
        )
    except ValueError as e:
        raise _token_error(OAuth2Error.SERVER_ERROR, str(e))

    logger.info("ACTION: oauth2_token_client_credentials, client_id=%s", client.client_id)

    await dispatch_webhook_event(
        db,
        tenant_id=client.tenant_id,
        event=WebhookEvent.OAUTH2_TOKEN_ISSUED,
        data={
            "grant_type": "client_credentials",
            "client_id": client.client_id,
            "client_uuid": str(client.id),
            "user_id": None,
            "scopes": list(requested_scopes) if requested_scopes else [],
            "tenant_id": str(client.tenant_id) if client.tenant_id else None,
        },
    )

    # Client credentials does not issue refresh tokens per RFC 6749
    return TokenResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=expires_in,
        refresh_token=None,  # No refresh token for client credentials
        scope=" ".join(requested_scopes) if requested_scopes else None,
    )


async def _handle_password(
    db: AsyncSession,
    oauth2_service: OAuth2ClientService,
    auth_service: AuthService,
    token_service: TokenService,
    client,
    username: str | None,
    password: str | None,
    scope: str | None,
    issuer: str,
    otp: str | None = None,
    mfa_service: MFAService | None = None,
) -> TokenResponse:
    """Issue tokens by directly authenticating a resource owner (RFC 6749 §4.3).

    The user's credentials are validated server-side. When TOTP MFA is enabled
    for the account, the caller must also supply a valid `otp` value; omitting
    it returns `invalid_grant: mfa_required`. This grant is considered legacy
    (deprecated in OAuth 2.1) — use the `authorization_code` grant with PKCE
    for new integrations. An ID token is included when `openid` is among the
    granted scopes.
    """
    logger.info("Processing password grant for client %s", client.client_id)

    if not username:
        logger.warning("Password grant failed: username is required")
        raise _token_error(OAuth2Error.INVALID_REQUEST, "username is required")

    if not password:
        logger.warning("Password grant failed: password is required")
        raise _token_error(OAuth2Error.INVALID_REQUEST, "password is required")

    # Authenticate the user
    user = await auth_service.authenticate(db, username, password)
    if not user:
        logger.warning("Password grant failed: invalid credentials for username %s", username)
        raise _token_error(OAuth2Error.INVALID_GRANT, "Invalid username or password")

    # Enforce MFA when TOTP is enabled for this user.
    if mfa_service is not None:
        user_mfa = await mfa_service.get_user_mfa(db, str(user.id))
        if user_mfa and user_mfa.totp_enabled:
            if not otp:
                logger.warning("Password grant failed: MFA required for user_id=%s", user.id)
                raise _token_error(OAuth2Error.INVALID_GRANT, "mfa_required")

            if not await mfa_service.verify_mfa_code_with_email(db, str(user.id), otp):
                logger.warning("Password grant failed: invalid OTP for user_id=%s", user.id)
                raise _token_error(OAuth2Error.INVALID_GRANT, "invalid_otp")

    # Parse and validate requested scopes
    requested_scopes = scope.split() if scope else []

    # If no scopes requested, use all allowed scopes for the client
    if not requested_scopes:
        requested_scopes = list(client.allowed_scopes)

    # Validate requested scopes against allowed scopes
    if not oauth2_service.validate_scopes(client, requested_scopes):
        raise _token_error(
            OAuth2Error.INVALID_SCOPE,
            "Requested scope exceeds client's allowed scopes",
        )

    # Create tokens with user_id
    try:
        access_token, refresh_token, expires_in = await token_service.create_token_pair(
            db=db,
            client=client,
            scopes=requested_scopes,
            user_id=user.id,
            issuer=issuer,
        )
    except ValueError as e:
        logger.error("Password grant failed: token creation error: %s", e)
        raise _token_error(OAuth2Error.SERVER_ERROR, str(e))

    # Create ID token if openid scope requested
    id_token = None
    if "openid" in requested_scopes:
        try:
            id_token = await token_service.create_id_token(
                db=db,
                client=client,
                user_id=user.id,
                nonce=None,
                access_token=access_token,
                issuer=issuer,
            )
        except ValueError:
            logger.warning(
                "ID token creation failed for client %s, continuing without it", client.client_id
            )

    logger.info(
        "ACTION: oauth2_token_password, user_id=%s, client_id=%s", user.id, client.client_id
    )

    await dispatch_webhook_event(
        db,
        tenant_id=client.tenant_id,
        event=WebhookEvent.OAUTH2_TOKEN_ISSUED,
        data={
            "grant_type": "password",
            "client_id": client.client_id,
            "client_uuid": str(client.id),
            "user_id": str(user.id),
            "scopes": list(requested_scopes) if requested_scopes else [],
            "tenant_id": str(client.tenant_id) if client.tenant_id else None,
        },
    )

    return TokenResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=expires_in,
        refresh_token=refresh_token,
        scope=" ".join(requested_scopes) if requested_scopes else None,
        id_token=id_token,
    )


async def _handle_device_code(
    db: AsyncSession,
    device_service: DeviceCodeService,
    token_service: TokenService,
    client,
    device_code: str | None,
    issuer: str,
) -> TokenResponse:
    """Poll for tokens after a device authorization request (RFC 8628 §3.4).

    The device calls this endpoint repeatedly using the `device_code` obtained
    from the device authorization endpoint. Responses follow the RFC 8628
    polling protocol: `authorization_pending` means the user has not yet
    acted, `slow_down` signals the device is polling too frequently, and
    `access_denied` means the user rejected the request. On success the device
    code is consumed (one-time use) and tokens are returned.
    """
    if not device_code:
        raise _token_error(OAuth2Error.INVALID_REQUEST, "device_code is required")

    # Get device authorization
    device = await device_service.get_by_device_code(db, device_code)

    if not device:
        raise _token_error(OAuth2Error.INVALID_GRANT, "Invalid device code")

    # Verify client matches
    if device.client_id != client.id:
        raise _token_error(OAuth2Error.INVALID_GRANT, "Device code was not issued to this client")

    # Check if expired
    if device_service.is_expired(device):
        raise _token_error(OAuth2Error.EXPIRED_TOKEN, "Device code has expired")

    # Check polling rate
    if device_service.is_slow_down_required(device):
        raise _token_error(OAuth2Error.SLOW_DOWN, "Polling too frequently")

    # Update last poll time
    await device_service.update_poll_time(db, device)

    # Check authorization status
    if device.status == DeviceCodeStatus.PENDING.value:
        raise _token_error(
            OAuth2Error.AUTHORIZATION_PENDING,
            "Authorization pending. User has not yet completed authorization.",
        )

    if device.status == DeviceCodeStatus.DENIED.value:
        raise _token_error(OAuth2Error.ACCESS_DENIED, "User denied the authorization request")

    if device.status != DeviceCodeStatus.AUTHORIZED.value:
        raise _token_error(OAuth2Error.INVALID_GRANT, "Invalid device code status")

    # User has authorized - create tokens
    try:
        access_token, refresh_token, expires_in = await token_service.create_token_pair(
            db=db,
            client=client,
            scopes=device.scopes,
            user_id=device.user_id,
            issuer=issuer,
        )
    except ValueError as e:
        raise _token_error(OAuth2Error.SERVER_ERROR, str(e))

    # Delete the device code (one-time use)
    await device_service.delete(db, device)

    logger.info(
        "ACTION: oauth2_token_device_code, user_id=%s, client_id=%s",
        device.user_id,
        client.client_id,
    )

    await dispatch_webhook_event(
        db,
        tenant_id=client.tenant_id,
        event=WebhookEvent.OAUTH2_TOKEN_ISSUED,
        data={
            "grant_type": "device_code",
            "client_id": client.client_id,
            "client_uuid": str(client.id),
            "user_id": str(device.user_id) if device.user_id else None,
            "scopes": list(device.scopes) if device.scopes else [],
            "tenant_id": str(client.tenant_id) if client.tenant_id else None,
        },
    )

    return TokenResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=expires_in,
        refresh_token=refresh_token,
        scope=" ".join(device.scopes) if device.scopes else None,
    )


async def _handle_token_exchange(
    db: AsyncSession,
    token_exchange_service: TokenExchangeService,
    token_service: TokenService,
    client,
    subject_token: str | None,
    subject_token_type: str | None,
    actor_token: str | None,
    actor_token_type: str | None,
    requested_token_type: str | None,
    audience: str | None,
    resource: str | None,
    scope: str | None,
    issuer: str,
) -> TokenResponse:
    """Exchange an existing token for a new token with different scopes or audience (RFC 8693 §2).

    Only confidential clients may use this grant. The `subject_token` and
    `subject_token_type` are required; `actor_token`/`actor_token_type` are
    optional and enable delegation semantics (the actor claim is embedded in
    the new token). Granted scopes are derived from the subject token's scopes
    filtered through the client's allowed scopes and the caller's RBAC roles.
    No refresh token is issued for exchanged tokens.
    """
    # Validate required parameters
    if not subject_token:
        raise _token_error(OAuth2Error.INVALID_REQUEST, "subject_token is required")

    if not subject_token_type:
        raise _token_error(OAuth2Error.INVALID_REQUEST, "subject_token_type is required")

    # Token exchange requires a confidential client
    if not client.is_confidential:
        raise _token_error(
            OAuth2Error.UNAUTHORIZED_CLIENT,
            "token-exchange grant requires a confidential client",
        )

    try:
        # Validate subject token
        token_record, user_id, subject_scopes = await token_exchange_service.validate_subject_token(
            db=db,
            subject_token=subject_token,
            subject_token_type=subject_token_type,
            client=client,
        )

        # Validate actor token (optional)
        actor_claims = token_exchange_service.validate_actor_token(
            actor_token=actor_token,
            actor_token_type=actor_token_type,
        )

        # Determine scopes for the new token (with RBAC-based scope escalation)
        granted_scopes = await token_exchange_service.determine_scopes(
            db=db,
            requested_scope=scope,
            subject_scopes=subject_scopes,
            client=client,
            user_id=user_id,
        )

        # Validate audience/resource
        target_audience = token_exchange_service.validate_audience(
            audience=audience,
            resource=resource,
        )

    except TokenExchangeError as e:
        raise _token_error(e.error, e.description)

    # Create the exchanged token
    try:
        access_token, _, expires_in = await token_service.create_token_pair(
            db=db,
            client=client,
            scopes=granted_scopes,
            user_id=user_id,
            audience=target_audience,
            actor=actor_claims,
            issuer=issuer,
        )
    except ValueError as e:
        raise _token_error(OAuth2Error.SERVER_ERROR, str(e))

    logger.info(
        "ACTION: oauth2_token_exchange, user_id=%s, client_id=%s", user_id, client.client_id
    )

    await dispatch_webhook_event(
        db,
        tenant_id=client.tenant_id,
        event=WebhookEvent.OAUTH2_TOKEN_ISSUED,
        data={
            "grant_type": "token_exchange",
            "client_id": client.client_id,
            "client_uuid": str(client.id),
            "user_id": str(user_id) if user_id else None,
            "scopes": list(granted_scopes) if granted_scopes else [],
            "tenant_id": str(client.tenant_id) if client.tenant_id else None,
        },
    )

    # Token exchange typically doesn't issue refresh tokens
    return TokenResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=expires_in,
        refresh_token=None,
        scope=" ".join(granted_scopes) if granted_scopes else None,
    )
