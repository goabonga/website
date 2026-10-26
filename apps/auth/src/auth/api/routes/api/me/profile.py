# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Profile API endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db, get_profile_service
from auth.api.routes.api.deps import get_current_user_bearer
from auth.api.schemas.api.me import ProfileResponse, ProfileUpdateRequest
from auth.db.models.user import User
from auth.services.profile import ProfileData, ProfileService

logger = logging.getLogger(__name__)

router = APIRouter()


def _user_to_profile_response(user: User, *, sub: str | None = None) -> ProfileResponse:
    """Convert user + profile to ProfileResponse.

    Args:
        user: The authenticated user.
        sub: The subject identifier to include in the response.
            When pairwise subjects are enabled this is the pairwise sub
            from the JWT; otherwise it falls back to ``str(user.id)``.
    """
    profile = user.profile
    return ProfileResponse(
        sub=sub or str(user.id),
        nickname=profile.nickname if profile else None,
        name=profile.name if profile else None,
        given_name=profile.given_name if profile else None,
        family_name=profile.family_name if profile else None,
        middle_name=profile.middle_name if profile else None,
        preferred_username=profile.preferred_username if profile else None,
        picture=profile.picture_url if profile else None,
        website=profile.website if profile else None,
        gender=profile.gender if profile else None,
        birthdate=profile.birthdate if profile else None,
        zoneinfo=profile.zoneinfo if profile else None,
        locale=profile.locale if profile else None,
        phone_number=profile.phone_number if profile else None,
    )


@router.get("/", response_model=ProfileResponse)
async def get_profile(
    request: Request,
    user: Annotated[User, Depends(get_current_user_bearer)],
) -> ProfileResponse:
    """Return the profile of the currently authenticated user.

    Reads OIDC standard claims (name, given_name, family_name, picture, etc.)
    from the user's stored profile record. When pairwise subject identifiers
    are enabled the returned `sub` is tenant-scoped rather than the raw user ID.

    **Required scope:** any valid Bearer token

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/me/
    ```
    """
    pairwise_sub: str = getattr(request.state, "pairwise_sub", str(user.id))
    return _user_to_profile_response(user, sub=pairwise_sub)


@router.put("/", response_model=ProfileResponse)
async def update_profile(
    request: Request,
    data: ProfileUpdateRequest,
    user: Annotated[User, Depends(get_current_user_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
    profile_service: Annotated[ProfileService, Depends(get_profile_service)],
) -> ProfileResponse:
    """Replace the profile of the currently authenticated user.

    Performs a full replacement of all OIDC standard profile claims. Fields
    omitted from the request body are set to null. After the update the
    refreshed profile is returned so the client can confirm persisted values.

    **Required scope:** any valid Bearer token

    **Example:**
    ```
    curl -X PUT \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"given_name": "Alice", "family_name": "Smith", "locale": "en-US"}' \\
      https://auth.example.com/api/v1/me/
    ```
    """
    profile_data = ProfileData(
        nickname=data.nickname,
        given_name=data.given_name,
        family_name=data.family_name,
        middle_name=data.middle_name,
        preferred_username=data.preferred_username,
        picture_url=data.picture,
        website=data.website,
        gender=data.gender,
        birthdate=data.birthdate,
        zoneinfo=data.zoneinfo,
        locale=data.locale,
        phone_number=data.phone_number,
    )

    await profile_service.update_profile(db, str(user.id), profile_data)
    await db.commit()
    await db.refresh(user, ["profile"])

    logger.info("ACTION: profile_update_api_v1, user_id=%s", user.id)

    pairwise_sub: str = getattr(request.state, "pairwise_sub", str(user.id))
    return _user_to_profile_response(user, sub=pairwise_sub)
