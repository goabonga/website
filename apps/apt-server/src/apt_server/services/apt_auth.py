# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Resolve APT clients: anonymous, basic-auth + PAT, or bearer token.

Unlike the JSON API where every request carries a bearer, ``apt`` clients only
know how to send ``Authorization: Basic``. This helper inspects a FastAPI
request, introspects the credentials against ``auth``, and returns a
:class:`Caller` (or ``None`` for valid anonymous access to public components).
"""

import base64
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from apt_server.acl.packages import Caller
from apt_server.acl.scopes import parse_scopes
from apt_server.auth.introspection import TokenRevokedError, introspection_client
from apt_server.auth.jwks import jwks_manager
from apt_server.logging import get_logger, set_request_context

logger = get_logger(__name__)

BASIC_REALM = 'Basic realm="apt", charset="UTF-8"'


def _unauthorized(detail: str = "authentication required") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": BASIC_REALM},
    )


def _extract_credentials(authorization: str | None) -> tuple[str | None, str | None]:
    """Return the username/password from an ``Authorization`` header.

    Supports both ``Basic`` (returns the decoded username and password) and
    ``Bearer`` (returns ``(None, token)`` so upstream can introspect it as a
    PAT or JWT).
    """
    if not authorization:
        return None, None
    scheme, _, value = authorization.partition(" ")
    if not value:
        return None, None
    if scheme.lower() == "basic":
        try:
            decoded = base64.b64decode(value, validate=True).decode("utf-8", errors="replace")
        except (ValueError, UnicodeDecodeError):
            return None, None
        username, _, password = decoded.partition(":")
        return username or None, password or None
    if scheme.lower() == "bearer":
        return None, value
    return None, None


async def resolve_caller(
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> Caller | None:
    """Dependency: return the authenticated :class:`Caller` or ``None``.

    - No credentials → ``None``.
    - Invalid credentials → HTTP 401 with ``WWW-Authenticate: Basic``.
    """
    # 1. Try Authorization header (Basic or Bearer — used by apt clients and API)
    username, password = _extract_credentials(authorization)

    session_display_name = ""
    session_name = ""
    session_avatar_url = ""
    from_session = False
    if password is None:
        return None
    if not jwks_manager.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth2 not configured",
        )
    try:
        # JWT tokens (3 dot-separated segments) are validated via JWKS + introspection.
        # Opaque tokens (PATs: gab_pat_*) go through introspection only.
        is_jwt = len(password.split(".")) == 3
        if is_jwt:
            claims = await introspection_client.validate_token_with_introspection(password)
        else:
            claims = await introspection_client.validate_opaque_token(password)
    except TokenRevokedError:
        if from_session:
            logger.warning("session token revoked, falling back to anonymous")
            return None
        raise _unauthorized("token revoked")
    except Exception as exc:
        if from_session:
            logger.warning(
                "session auth failed (%s: %s), falling back to anonymous", type(exc).__name__, exc
            )
            return None
        logger.info("APT auth failed: %s", exc)
        raise _unauthorized("invalid credentials")

    sub = str(claims.get("sub") or claims.get("user_id") or "")
    if not sub:
        raise _unauthorized("token has no subject")

    scopes = parse_scopes(claims.get("scope") or claims.get("scopes"))
    groups_claim = claims.get("groups") or claims.get("roles") or []
    if isinstance(groups_claim, str):
        groups_claim = groups_claim.split()

    display_name = str(
        session_display_name
        or claims.get("username")
        or claims.get("preferred_username")
        or claims.get("email")
        or claims.get("name")
        or sub
    )

    caller = Caller(
        sub=sub,
        scopes=frozenset(scopes),
        groups=frozenset(groups_claim),
        display_name=display_name,
        name=session_name or claims.get("name", ""),
        avatar_url=session_avatar_url,
        is_session=from_session,
    )

    client_id = claims.get("client_id") or claims.get("azp")
    set_request_context(user_id=sub, client_id=client_id)
    request.state.user_id = sub
    request.state.client_id = client_id
    if username:
        request.state.apt_login = username

    return caller


Caller_ = Annotated[Caller | None, Depends(resolve_caller)]
