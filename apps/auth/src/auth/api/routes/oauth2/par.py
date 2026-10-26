# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Pushed Authorization Request (PAR) endpoint (RFC 9126)."""

import base64
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db, get_oauth2_client_service, get_par_service
from auth.api.schemas.oauth2 import OAuth2Error, PARResponse, TokenErrorResponse
from auth.services.oauth2_client import OAuth2ClientService
from auth.services.par import PARService
from auth.services.pkce import is_valid_code_challenge, is_valid_code_challenge_method

logger = logging.getLogger(__name__)

router = APIRouter()


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


def _par_error(error: str, description: str) -> HTTPException:
    """Create a PAR error response.

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
    "/par",
    response_model=PARResponse,
    responses={
        400: {"model": TokenErrorResponse, "description": "PAR error"},
        401: {"model": TokenErrorResponse, "description": "Invalid client"},
    },
)
async def pushed_authorization_request(
    response_type: Annotated[str, Form()],
    redirect_uri: Annotated[str, Form()],
    db: Annotated[AsyncSession, Depends(get_db)],
    oauth2_service: Annotated[OAuth2ClientService, Depends(get_oauth2_client_service)],
    par_service: Annotated[PARService, Depends(get_par_service)],
    authorization: Annotated[str | None, Header()] = None,
    client_id: Annotated[str | None, Form()] = None,
    client_secret: Annotated[str | None, Form()] = None,
    scope: Annotated[str | None, Form()] = None,
    state: Annotated[str | None, Form()] = None,
    code_challenge: Annotated[str | None, Form()] = None,
    code_challenge_method: Annotated[str | None, Form()] = None,
    nonce: Annotated[str | None, Form()] = None,
    prompt: Annotated[str | None, Form()] = None,
) -> PARResponse:
    """Push an authorization request to the server and receive a request_uri.

    Implements RFC 9126 Pushed Authorization Requests (PAR). Instead of passing
    all authorization parameters in the browser-visible front-channel redirect,
    the client submits them here via a confidential back-channel POST. The server
    stores the request and returns a short-lived `request_uri` (in
    `urn:ietf:params:oauth:request_uri:` format) that the client then passes to
    `/oauth2/authorize`. This prevents sensitive parameters (scopes, PKCE
    challenge, `state`, `nonce`) from appearing in browser history or server
    logs, enforces parameter integrity, and is required by the FAPI 2.0 security
    profile. The `request_uri` is single-use and expires after `expires_in`
    seconds (default 90 s per RFC 9126 §2.2).

    **Specification:**
    - RFC 9126 §2.1 — PAR request parameters (same as `/oauth2/authorize`)
    - RFC 9126 §2.2 — PAR response (`request_uri`, `expires_in`); status 201
    - RFC 6749 §2.3 — client authentication (Basic or form body)
    - RFC 7636 — PKCE parameters (`code_challenge`, `code_challenge_method`)

    **Authentication:** client credentials (HTTP Basic per RFC 6749 §2.3.1, or
    `client_id` + `client_secret` in the form body)

    **Example:**
    ```
    curl -X POST https://auth.example.com/oauth2/par \\
      -u "550e8400-e29b-41d4-a716-446655440000:my-client-secret" \\
      -H "Content-Type: application/x-www-form-urlencoded" \\
      -d "response_type=code" \\
      -d "client_id=550e8400-e29b-41d4-a716-446655440000" \\
      -d "redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback" \\
      -d "scope=openid+profile+email" \\
      -d "state=xyzABCrandom123" \\
      -d "code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM" \\
      -d "code_challenge_method=S256"
    # Returns: {"request_uri": "urn:ietf:params:oauth:request_uri:abc123", "expires_in": 90}
    # Then redirect the user to:
    # https://auth.example.com/oauth2/authorize?client_id=550e8400-e29b-41d4-a716-446655440000&request_uri=urn:ietf:params:oauth:request_uri:abc123
    ```

    **Responses:**
    - `201` — PAR request stored; `request_uri` and `expires_in` returned
    - `400` — invalid request parameters (bad `redirect_uri`, unsupported
      `response_type`, invalid PKCE, disallowed scope)
    - `401` — client authentication failed
    """
    logger.info("PAR request: client_id=%s", client_id)

    # Parse client credentials from header or form
    basic_client_id, basic_client_secret = _parse_basic_auth(authorization)
    effective_client_id = basic_client_id or client_id
    effective_client_secret = basic_client_secret or client_secret

    if not effective_client_id:
        logger.warning("PAR failed: client_id is required")
        raise _par_error(OAuth2Error.INVALID_REQUEST, "client_id is required")

    # Get and validate client
    client = await oauth2_service.get_client_by_client_id(db, effective_client_id)
    if not client or not client.is_active:
        logger.warning("PAR failed: invalid client %s", effective_client_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=TokenErrorResponse(
                error=OAuth2Error.INVALID_CLIENT,
                error_description="Invalid client",
            ).model_dump(),
            headers={"WWW-Authenticate": "Basic"},
        )

    # Confidential clients must authenticate
    if client.is_confidential:
        if not effective_client_secret:
            logger.warning("PAR failed: client authentication required for %s", effective_client_id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=TokenErrorResponse(
                    error=OAuth2Error.INVALID_CLIENT,
                    error_description="Client authentication required",
                ).model_dump(),
                headers={"WWW-Authenticate": "Basic"},
            )

        if not oauth2_service.verify_client_secret(client, effective_client_secret):
            logger.warning("PAR failed: invalid client credentials for %s", effective_client_id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=TokenErrorResponse(
                    error=OAuth2Error.INVALID_CLIENT,
                    error_description="Invalid client credentials",
                ).model_dump(),
                headers={"WWW-Authenticate": "Basic"},
            )

    # Validate response_type
    if response_type != "code":
        logger.warning("PAR failed: unsupported response_type %s", response_type)
        raise _par_error(
            OAuth2Error.UNSUPPORTED_RESPONSE_TYPE,
            "Only 'code' response type is supported",
        )

    # Validate redirect_uri
    if not oauth2_service.validate_redirect_uri(client, redirect_uri):
        logger.warning("PAR failed: redirect_uri not registered for client %s", effective_client_id)
        raise _par_error(
            OAuth2Error.INVALID_REQUEST,
            "redirect_uri not registered for this client",
        )

    # Parse scopes
    scopes = scope.split() if scope else ["openid"]

    # Validate scopes
    if not oauth2_service.validate_scopes(client, scopes):
        logger.warning("PAR failed: invalid scope for client %s", effective_client_id)
        raise _par_error(
            OAuth2Error.INVALID_SCOPE,
            "One or more requested scopes are not allowed",
        )

    # Validate PKCE if required or provided
    if client.require_pkce and not code_challenge:
        logger.warning("PAR failed: PKCE required for client %s", effective_client_id)
        raise _par_error(
            OAuth2Error.INVALID_REQUEST,
            "PKCE is required. Provide code_challenge.",
        )

    if code_challenge:
        # Default to S256 if not specified
        if not code_challenge_method:
            code_challenge_method = "S256"

        if not is_valid_code_challenge_method(code_challenge_method):
            logger.warning("PAR failed: invalid code_challenge_method")
            raise _par_error(
                OAuth2Error.INVALID_REQUEST,
                "Invalid code_challenge_method. Use S256.",
            )

        if not is_valid_code_challenge(code_challenge):
            logger.warning("PAR failed: invalid code_challenge format")
            raise _par_error(
                OAuth2Error.INVALID_REQUEST,
                "Invalid code_challenge format",
            )

    # Create PAR request
    request_uri, expires_in = await par_service.create_par_request(
        db=db,
        client=client,
        response_type=response_type,
        redirect_uri=redirect_uri,
        scopes=scopes,
        state=state,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        nonce=nonce,
        prompt=prompt,
    )

    await db.commit()

    logger.info(
        "PAR request created: client_id=%s, request_uri=%s", effective_client_id, request_uri
    )
    return PARResponse(
        request_uri=request_uri,
        expires_in=expires_in,
    )
