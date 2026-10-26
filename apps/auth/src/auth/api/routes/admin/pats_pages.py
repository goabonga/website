# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Admin Personal Access Token management HTML pages."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import (
    get_db,
    get_pat_service,
    get_templates,
    get_user_admin_permissions,
    require_scope,
)
from auth.db.models.pat import PersonalAccessToken
from auth.db.models.rbac import Role
from auth.db.models.user import User
from auth.services.pat import PersonalAccessTokenService
from auth.services.user import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pats")

_user_service = UserService()

# Scope dependencies
require_pats_read = require_scope("pats:read", redirect_to_login=True)
require_pats_revoke = require_scope("pats:revoke", redirect_to_login=True)


def pat_to_dict(pat: PersonalAccessToken, user_email: str | None = None) -> dict:
    """Convert PAT model to dictionary format.

    Args:
        pat: PersonalAccessToken database model.
        user_email: Optional user email.

    Returns:
        Dictionary with PAT information.
    """
    return {
        "id": str(pat.id),
        "user_id": str(pat.user_id),
        "user_email": user_email,
        "name": pat.name,
        "description": pat.description,
        "scopes": list(pat.scopes),
        "token_suffix": pat.token_suffix,
        "created_at": pat.created_at.isoformat() if pat.created_at else None,
        "expires_at": pat.expires_at.isoformat() if pat.expires_at else None,
        "last_used_at": pat.last_used_at.isoformat() if pat.last_used_at else None,
        "last_used_ip": pat.last_used_ip,
        "use_count": pat.use_count,
        "is_expired": pat.is_expired,
        "is_revoked": pat.revoked_at is not None,
        "revoked_at": pat.revoked_at.isoformat() if pat.revoked_at else None,
        "tenant_id": str(pat.tenant_id) if pat.tenant_id else None,
        "target_client_id": str(pat.target_client_id) if pat.target_client_id else None,
    }


def _primary_email(user: User | None) -> str | None:
    """Return the primary email for a user loaded with its ``emails``."""
    if user is None:
        return None
    for email in user.emails or []:
        if email.is_primary:
            return email.email
    return None


@router.get("", response_class=HTMLResponse)
async def pats_list_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_pats_read)],
    pat_service: Annotated[PersonalAccessTokenService, Depends(get_pat_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    include_revoked: Annotated[bool, Query()] = False,
    user_id: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    """PATs list page."""
    logger.debug("Admin page: listing PATs")
    templates = get_templates()

    limit = 20
    offset = (page - 1) * limit

    # Parse user_id filter
    user_uuid = None
    if user_id:
        try:
            user_uuid = uuid.UUID(user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID format",
            )

    tokens, total = await pat_service.list_all_tokens(db, user_uuid, include_revoked, offset, limit)

    # Get user emails and build PAT list
    pats_list = []
    email_cache: dict[uuid.UUID, str | None] = {}
    for pat in tokens:
        if pat.user_id not in email_cache:
            owner = await _user_service.get_by_id(db, pat.user_id)
            email_cache[pat.user_id] = _primary_email(owner)
        pats_list.append(pat_to_dict(pat, email_cache[pat.user_id]))

    # Calculate pagination
    total_pages = (total + limit - 1) // limit

    success = request.query_params.get("success")
    error = request.query_params.get("error")

    user, roles = auth
    permissions = get_user_admin_permissions(roles)

    return templates.TemplateResponse(
        request=request,
        name="admin/pats/list.html",
        context={
            "active_section": "pats",
            "pats": pats_list,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "include_revoked": include_revoked,
            "filter_user_id": user_id,
            "success": success,
            "error": error,
            "permissions": permissions,
        },
    )


@router.get("/{token_id}", response_class=HTMLResponse)
async def pat_detail_page(
    request: Request,
    token_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_pats_read)],
    pat_service: Annotated[PersonalAccessTokenService, Depends(get_pat_service)],
) -> HTMLResponse:
    """PAT detail page."""
    logger.debug("Admin page: viewing PAT id=%s", token_id)
    templates = get_templates()

    try:
        pat_uuid = uuid.UUID(token_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid token ID format",
        )

    pat = await pat_service.get_token_by_id(db, pat_uuid)

    if not pat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found",
        )

    # Get user email via the user service (eager-loads emails/profile)
    owner = await _user_service.get_by_id(db, pat.user_id)
    user_email = _primary_email(owner)

    pat_dict = pat_to_dict(pat, user_email)

    success = request.query_params.get("success")
    error = request.query_params.get("error")

    user, roles = auth
    permissions = get_user_admin_permissions(roles)

    return templates.TemplateResponse(
        request=request,
        name="admin/pats/detail.html",
        context={
            "active_section": "pats",
            "pat": pat_dict,
            "success": success,
            "error": error,
            "permissions": permissions,
        },
    )


@router.post("/{token_id}/revoke", response_class=RedirectResponse)
async def pat_revoke_submit(
    token_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_pats_revoke)],
    pat_service: Annotated[PersonalAccessTokenService, Depends(get_pat_service)],
    reason: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    """Handle PAT revocation."""
    logger.debug("Admin page: revoking PAT id=%s", token_id)

    try:
        pat_uuid = uuid.UUID(token_id)
    except ValueError:
        return RedirectResponse(
            url="/admin/pats?error=Invalid+token+ID",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    user, _ = auth
    success = await pat_service.revoke_token(
        db,
        pat_uuid,
        user_id=None,  # No ownership check for admin
        revoked_by=user.id,
        reason=reason or "Revoked by administrator",
    )

    if not success:
        return RedirectResponse(
            url="/admin/pats?error=Token+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    await db.commit()

    logger.info("Admin page: revoked PAT id=%s", token_id)
    return RedirectResponse(
        url="/admin/pats?success=Token+revoked+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/revoke-all", response_class=RedirectResponse)
async def pats_revoke_all_submit(
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_pats_revoke)],
    pat_service: Annotated[PersonalAccessTokenService, Depends(get_pat_service)],
    user_id: Annotated[str, Form()],
    reason: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    """Handle bulk PAT revocation for a user."""
    logger.debug("Admin page: revoking all PATs for user_id=%s", user_id)

    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        return RedirectResponse(
            url="/admin/pats?error=Invalid+user+ID",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    user, _ = auth
    count = await pat_service.bulk_revoke(
        db,
        user_uuid,
        revoked_by=user.id,
        reason=reason or "Bulk revoked by administrator",
    )

    await db.commit()

    logger.info("Admin page: revoked %d PATs for user_id=%s", count, user_id)
    return RedirectResponse(
        url=f"/admin/pats?success=Revoked+{count}+token(s)",
        status_code=status.HTTP_303_SEE_OTHER,
    )
