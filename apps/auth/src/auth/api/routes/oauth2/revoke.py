# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""OAuth2 token revocation endpoint (RFC 7009)."""

import base64
import logging
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, Form, Header, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db, get_oauth2_client_service, get_token_service
from auth.api.schemas.oauth2 import OAuth2Error, TokenErrorResponse
from auth.db.models.tenant import WebhookEvent
from auth.services.oauth2_client import OAuth2ClientService
from auth.services.token import TokenService
from auth.services.webhook import safe_dispatch as dispatch_webhook_event

logger = logging.getLogger(__name__)

router = APIRouter()


def _parse_basic_auth(authorization: str | None) -> tuple[str | None, str | None]:
    """Parse Basic authentication header."""
    if not authorization or not authorization.startswith("Basic "):
        return None, None

    try:
        encoded = authorization[6:]
        decoded = base64.b64decode(encoded).decode("utf-8")
        client_id, client_secret = decoded.split(":", 1)
        return client_id, client_secret
    except (ValueError, UnicodeDecodeError):
        return None, None


@router.post(
    "/revoke",
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": TokenErrorResponse, "description": "Invalid client"},
    },
)
async def revoke_token(
    token: Annotated[str, Form()],
    db: Annotated[AsyncSession, Depends(get_db)],
    oauth2_service: Annotated[OAuth2ClientService, Depends(get_oauth2_client_service)],
    token_service: Annotated[TokenService, Depends(get_token_service)],
    authorization: Annotated[str | None, Header()] = None,
    client_id: Annotated[str | None, Form()] = None,
    client_secret: Annotated[str | None, Form()] = None,
    token_type_hint: Annotated[str | None, Form()] = None,
) -> Response:
    """Revoke an OAuth2 access token or refresh token (RFC 7009).

    Notifies the authorization server that a previously issued token is no
    longer needed, allowing the server to clean up associated state (e.g. on
    user logout or credential rotation). The response is always HTTP 200 OK
    regardless of whether the token existed or was already revoked — this
    intentional opaqueness prevents information leakage per RFC 7009 §2.2.
    Revoking a refresh token also revokes all access tokens derived from it
    (cascade per RFC 7009 §2.1 last paragraph). Clients may only revoke tokens
    they originally issued; presenting a token belonging to a different client
    is silently ignored.

    **Specification:** RFC 7009 §2.1 (request), §2.2 (response); client
    authentication follows RFC 6749 §2.3.

    **Authentication:** client credentials (HTTP Basic per RFC 6749 §2.3.1,
    or `client_id` + `client_secret` in the form body)

    **Example:**
    ```
    curl -X POST \\
      -u "s6BhdRkqt3:7Fjfp0ZBr1KtDRbnfVdmIw" \\
      -H "Content-Type: application/x-www-form-urlencoded" \\
      -d "token=8xLOxBtZp8&token_type_hint=refresh_token" \\
      https://auth.example.com/oauth2/revoke
    ```
    """
    logger.info(
        "Token revocation request: client_id=%s, token_type_hint=%s", client_id, token_type_hint
    )

    # Parse client credentials
    basic_client_id, basic_client_secret = _parse_basic_auth(authorization)
    effective_client_id = basic_client_id or client_id
    effective_client_secret = basic_client_secret or client_secret

    if not effective_client_id:
        logger.warning("Token revocation failed: client authentication required")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=TokenErrorResponse(
                error=OAuth2Error.INVALID_CLIENT,
                error_description="Client authentication required",
            ).model_dump(),
            headers={"WWW-Authenticate": "Basic"},
        )

    # Get and verify client
    client = await oauth2_service.get_client_by_client_id(db, effective_client_id)
    if not client or not client.is_active:
        logger.warning("Token revocation failed: invalid client %s", effective_client_id)
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
                "Token revocation failed: client secret required for %s", effective_client_id
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
                "Token revocation failed: invalid client credentials for %s", effective_client_id
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=TokenErrorResponse(
                    error=OAuth2Error.INVALID_CLIENT,
                    error_description="Invalid client credentials",
                ).model_dump(),
                headers={"WWW-Authenticate": "Basic"},
            )

    # Try to revoke based on token_type_hint or try both
    revoked = False

    if token_type_hint == "refresh_token":
        # Try refresh token first
        revoked = await token_service.revoke_refresh_token(db, token)
        if not revoked:
            # Try as access token (extract JTI from JWT)
            jti = _extract_jti_from_token(token)
            if jti:
                revoked = await token_service.revoke_access_token(db, jti)
    else:
        # Try access token first (default or token_type_hint=access_token)
        jti = _extract_jti_from_token(token)
        if jti:
            revoked = await token_service.revoke_access_token(db, jti)
        if not revoked:
            # Try as refresh token
            revoked = await token_service.revoke_refresh_token(db, token)

    if revoked:
        logger.info("ACTION: oauth2_token_revoke, client_id=%s", effective_client_id)
        await dispatch_webhook_event(
            db,
            tenant_id=client.tenant_id,
            event=WebhookEvent.OAUTH2_TOKEN_REVOKED,
            data={
                "client_id": effective_client_id,
                "client_uuid": str(client.id),
                "token_type_hint": token_type_hint,
                "tenant_id": str(client.tenant_id) if client.tenant_id else None,
            },
        )
    else:
        logger.debug(
            "Token revocation: token not found or already revoked for client %s",
            effective_client_id,
        )

    # Per RFC 7009, always return 200 OK regardless of whether token was found
    return Response(status_code=status.HTTP_200_OK)


def _extract_jti_from_token(token: str) -> str | None:
    """Extract JTI from a JWT token without verification.

    Args:
        token: JWT token string.

    Returns:
        JTI claim value or None if extraction fails.
    """
    try:
        # Decode without verification to get the JTI
        unverified = jwt.decode(token, options={"verify_signature": False})
        return unverified.get("jti")
    except jwt.DecodeError:
        return None
