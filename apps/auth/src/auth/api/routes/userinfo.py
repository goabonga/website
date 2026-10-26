# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""OIDC UserInfo endpoint."""

import logging
from datetime import UTC, datetime
from typing import Annotated, Any

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db, get_token_service
from auth.api.schemas.userinfo import UserInfoResponse
from auth.services.oauth2_client import OAuth2ClientService
from auth.services.pairwise import PairwiseSubjectService
from auth.services.token import TokenService
from auth.services.user import UserService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["oidc"])


def _extract_bearer_token(authorization: str | None) -> str | None:
    """Extract bearer token from Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization[7:]


async def _get_userinfo(
    db: AsyncSession,
    token_service: TokenService,
    access_token: str,
) -> dict[str, Any]:
    """Get user info from access token.

    Args:
        db: Database session.
        token_service: Token service.
        access_token: Bearer access token.

    Returns:
        UserInfo claims dict.

    Raises:
        HTTPException: If token is invalid or user not found.
    """
    logger.info("UserInfo request received")

    # Decode token without verification to get claims
    try:
        unverified = jwt.decode(access_token, options={"verify_signature": False})
    except jwt.DecodeError:
        logger.warning("UserInfo failed: invalid access token format")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )

    jti = unverified.get("jti")
    if not jti:
        logger.warning("UserInfo failed: access token missing jti")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )

    # Verify token is valid in database
    token_record = await token_service.get_access_token_by_jti(db, jti)
    if not token_record:
        logger.warning("UserInfo failed: access token not found jti=%s", jti)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token not found",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )

    # Check if revoked
    if token_record.revoked_at is not None:
        logger.warning("UserInfo failed: access token has been revoked jti=%s", jti)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has been revoked",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )

    # Check if expired
    now = datetime.now(UTC)
    if token_record.expires_at < now:
        logger.warning("UserInfo failed: access token has expired jti=%s", jti)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has expired",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )

    # Check if openid scope is present
    scopes = unverified.get("scope", "").split()
    if "openid" not in scopes:
        logger.warning("UserInfo failed: access token missing openid scope jti=%s", jti)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access token does not have openid scope",
            headers={"WWW-Authenticate": 'Bearer error="insufficient_scope"'},
        )

    # Get user_id from token
    user_id = token_record.user_id
    if not user_id:
        logger.warning("UserInfo failed: access token has no associated user jti=%s", jti)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has no associated user",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )

    # Load user with profile and emails via service
    user_service = UserService()
    user = await user_service.get_by_id(db, user_id)

    if not user or not user.is_active:
        logger.warning("UserInfo failed: user not found or inactive user_id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )

    logger.info("UserInfo succeeded for user_id=%s, scopes=%s", user_id, scopes)

    # Build response based on scopes — always use pairwise sub
    pairwise_service = PairwiseSubjectService()
    oauth2_client_service = OAuth2ClientService()
    client = await oauth2_client_service.get_by_id(db, token_record.client_id)
    pairwise_sub = (
        await pairwise_service.get_sub_for_client(db, user.id, client)
        if client is not None
        else str(user.id)
    )
    claims: dict[str, Any] = {
        "sub": pairwise_sub,
    }

    # Profile scope claims
    if "profile" in scopes and user.profile:
        profile = user.profile
        if profile.name:
            claims["name"] = profile.name
        if profile.given_name:
            claims["given_name"] = profile.given_name
        if profile.family_name:
            claims["family_name"] = profile.family_name
        if profile.middle_name:
            claims["middle_name"] = profile.middle_name
        if profile.nickname:
            claims["nickname"] = profile.nickname
        if profile.preferred_username:
            claims["preferred_username"] = profile.preferred_username
        if profile.profile_url:
            claims["profile"] = profile.profile_url
        if profile.picture_url:
            claims["picture"] = profile.picture_url
        if profile.website:
            claims["website"] = profile.website
        if profile.gender:
            claims["gender"] = profile.gender
        if profile.birthdate:
            claims["birthdate"] = profile.birthdate
        if profile.zoneinfo:
            claims["zoneinfo"] = profile.zoneinfo
        if profile.locale:
            claims["locale"] = profile.locale
        if profile.updated_at:
            claims["updated_at"] = int(profile.updated_at.timestamp())

    # Email scope claims
    if "email" in scopes:
        primary_email = next(
            (e for e in user.emails if e.is_primary),
            user.emails[0] if user.emails else None,
        )
        if primary_email:
            claims["email"] = primary_email.email
            claims["email_verified"] = primary_email.is_verified

    # Phone scope claims
    if "phone" in scopes and user.profile and user.profile.phone_number:
        claims["phone_number"] = user.profile.phone_number
        claims["phone_number_verified"] = user.profile.phone_number_verified

    # Address scope claims
    if "address" in scopes and user.profile:
        address = {}
        if user.profile.address_formatted:
            address["formatted"] = user.profile.address_formatted
        if user.profile.address_street:
            address["street_address"] = user.profile.address_street
        if user.profile.address_locality:
            address["locality"] = user.profile.address_locality
        if user.profile.address_region:
            address["region"] = user.profile.address_region
        if user.profile.address_postal_code:
            address["postal_code"] = user.profile.address_postal_code
        if user.profile.address_country:
            address["country"] = user.profile.address_country
        if address:
            claims["address"] = address

    return claims


@router.get("/userinfo", response_model=UserInfoResponse)
async def get_userinfo(
    db: Annotated[AsyncSession, Depends(get_db)],
    token_service: Annotated[TokenService, Depends(get_token_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Return OIDC claims for the authenticated end-user (GET).

    Validates the Bearer access token and returns a JSON object containing
    claims about the authenticated user. The `sub` claim is always present and
    is a pairwise subject identifier — it matches the `sub` in the ID token
    issued to the same client (OIDC Core §8.1). Additional claims are
    scope-gated: `profile` adds name/picture/locale/updated_at, `email` adds
    email/email_verified, `phone` adds phone_number/phone_number_verified, and
    `address` adds the structured address claim. Tokens that are expired,
    revoked, or missing the `openid` scope are rejected with
    `WWW-Authenticate: Bearer error="invalid_token"` (401) or
    `error="insufficient_scope"` (403) per RFC 6750 §3.

    **Specification:** OpenID Connect Core 1.0 §5.3 (UserInfo Endpoint),
    §5.3.1 (UserInfo Request), §5.3.2 (Successful UserInfo Response),
    §5.4 (Requesting Claims), §8.1 (Pairwise Subject Identifiers);
    RFC 6750 §2.1 (Bearer token in Authorization header),
    RFC 6750 §3 (WWW-Authenticate error responses).

    **Authentication:** Bearer access token issued with `openid` scope
    (RFC 6750 §2.1)

    **Responses:**
    - `200` — JSON claims object; `sub` is always present
    - `401` — missing, expired, revoked, or malformed access token
    - `403` — token lacks the `openid` scope

    **Example:**
    ```
    curl -H "Authorization: Bearer <access_token>" \\
      https://auth.example.com/userinfo
    ```
    """
    access_token = _extract_bearer_token(authorization)
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return await _get_userinfo(db, token_service, access_token)


@router.post("/userinfo", response_model=UserInfoResponse)
async def post_userinfo(
    db: Annotated[AsyncSession, Depends(get_db)],
    token_service: Annotated[TokenService, Depends(get_token_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Return OIDC claims for the authenticated end-user (POST).

    Identical in behaviour to the GET variant — validates the Bearer access
    token and returns scope-gated claims about the authenticated user. The POST
    method is required by OIDC Core §5.3.1 to support clients or proxies that
    cannot attach custom request headers to a GET; the access token MUST still
    be passed in the `Authorization: Bearer` header (RFC 6750 §2.1). The `sub`
    claim is always present as a pairwise subject identifier (OIDC Core §8.1),
    matching the `sub` of the corresponding ID token. Claim filtering rules and
    error responses are the same as for the GET endpoint.

    **Specification:** OpenID Connect Core 1.0 §5.3 (UserInfo Endpoint),
    §5.3.1 (UserInfo Request — both GET and POST MUST be supported),
    §5.3.2 (Successful UserInfo Response), §5.4 (Requesting Claims),
    §8.1 (Pairwise Subject Identifiers);
    RFC 6750 §2.1 (Bearer token in Authorization header),
    RFC 6750 §3 (WWW-Authenticate error responses).

    **Authentication:** Bearer access token issued with `openid` scope
    (RFC 6750 §2.1)

    **Responses:**
    - `200` — JSON claims object; `sub` is always present
    - `401` — missing, expired, revoked, or malformed access token
    - `403` — token lacks the `openid` scope

    **Example:**
    ```
    curl -X POST -H "Authorization: Bearer <access_token>" \\
      https://auth.example.com/userinfo
    ```
    """
    access_token = _extract_bearer_token(authorization)
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return await _get_userinfo(db, token_service, access_token)
