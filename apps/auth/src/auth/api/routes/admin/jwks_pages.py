# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Admin JWKS management HTML pages."""

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import (
    get_db,
    get_jwks_service,
    get_templates,
    get_user_admin_permissions,
    require_scope,
)
from auth.db.models.rbac import Role
from auth.db.models.user import User
from auth.services.jwks import JWKSService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jwks")

# Scope dependencies
require_jwks_read = require_scope("jwks:read", redirect_to_login=True)
require_jwks_write = require_scope("jwks:write", redirect_to_login=True)
require_jwks_revoke = require_scope("jwks:revoke", redirect_to_login=True)
require_jwks_delete = require_scope("jwks:delete", redirect_to_login=True)
require_jwks_rotate = require_scope("jwks:rotate", redirect_to_login=True)


def jwk_to_dict(jwk, jwks_service: JWKSService) -> dict:
    """Convert JWK model to dictionary format.

    Args:
        jwk: JWK database model.
        jwks_service: JWKS service for public key conversion.

    Returns:
        Dictionary with key information.
    """
    public_jwk = jwks_service.to_jwk_public(jwk)
    return {
        "kid": jwk.kid,
        "kty": jwk.kty,
        "alg": jwk.alg,
        "use": jwk.use,
        "is_active": jwk.is_active,
        "revoked_at": jwk.revoked_at.isoformat() if jwk.revoked_at else None,
        "created_at": jwk.created_at.isoformat() if jwk.created_at else None,
        "public_key": public_jwk,
    }


@router.get("", response_class=HTMLResponse)
async def jwks_list_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    jwks_service: Annotated[JWKSService, Depends(get_jwks_service)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_jwks_read)],
) -> HTMLResponse:
    """JWKS keys list page."""
    logger.debug("Admin page: listing JWKS keys")
    templates = get_templates()

    keys = await jwks_service.list(db, include_revoked=False)
    keys_list = [jwk_to_dict(k, jwks_service) for k in keys]

    # Get success/error from query params
    success = request.query_params.get("success")
    error = request.query_params.get("error")

    user, roles = auth
    permissions = get_user_admin_permissions(roles)

    return templates.TemplateResponse(
        request=request,
        name="admin/jwks/list.html",
        context={
            "active_section": "jwks",
            "keys": keys_list,
            "success": success,
            "error": error,
            "current_user": user,
            "permissions": permissions,
        },
    )


@router.get("/generate", response_class=HTMLResponse)
async def jwks_generate_page(
    request: Request,
    auth: Annotated[tuple[User, list[Role]], Depends(require_jwks_write)],
) -> HTMLResponse:
    """JWKS key generation form page."""
    logger.debug("Admin page: generate JWKS key form")
    templates = get_templates()

    error = request.query_params.get("error")
    user, roles = auth
    permissions = get_user_admin_permissions(roles)

    return templates.TemplateResponse(
        request=request,
        name="admin/jwks/generate.html",
        context={
            "active_section": "jwks",
            "error": error,
            "current_user": user,
            "permissions": permissions,
        },
    )


@router.post("/generate", response_class=RedirectResponse)
async def jwks_generate_submit(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    jwks_service: Annotated[JWKSService, Depends(get_jwks_service)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_jwks_write)],
    key_size: Annotated[int, Form()] = 2048,
    activate: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    """Handle JWKS key generation form submission."""
    logger.debug("Admin page: generating JWKS key (size=%d, activate=%s)", key_size, activate)

    if key_size not in (2048, 3072, 4096):
        return RedirectResponse(
            url="/admin/jwks/generate?error=Invalid+key+size",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        jwk = await jwks_service.generate_key(db, key_size=key_size, activate=activate == "true")
        logger.info("Admin page: generated JWKS key kid=%s", jwk.kid)
        return RedirectResponse(
            url=f"/admin/jwks/{jwk.kid}?success=Key+generated+successfully",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        logger.error("Admin page: failed to generate key: %s", e)
        return RedirectResponse(
            url=f"/admin/jwks/generate?error={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


@router.get("/{kid}", response_class=HTMLResponse)
async def jwks_detail_page(
    request: Request,
    kid: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    jwks_service: Annotated[JWKSService, Depends(get_jwks_service)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_jwks_read)],
) -> HTMLResponse:
    """JWKS key detail page."""
    logger.debug("Admin page: viewing JWKS key kid=%s", kid)
    templates = get_templates()

    jwk = await jwks_service.get_by_kid(db, kid)

    if not jwk:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Key not found",
        )

    key_dict = jwk_to_dict(jwk, jwks_service)
    public_key_json = json.dumps(key_dict["public_key"], indent=2)

    success = request.query_params.get("success")
    error = request.query_params.get("error")
    user, roles = auth
    permissions = get_user_admin_permissions(roles)

    return templates.TemplateResponse(
        request=request,
        name="admin/jwks/detail.html",
        context={
            "active_section": "jwks",
            "key": key_dict,
            "public_key_json": public_key_json,
            "success": success,
            "error": error,
            "current_user": user,
            "permissions": permissions,
        },
    )


@router.post("/{kid}/activate", response_class=RedirectResponse)
async def jwks_activate_submit(
    kid: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    jwks_service: Annotated[JWKSService, Depends(get_jwks_service)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_jwks_write)],
) -> RedirectResponse:
    """Handle JWKS key activation."""
    logger.debug("Admin page: activating JWKS key kid=%s", kid)

    try:
        jwk = await jwks_service.activate_key(db, kid)
        if not jwk:
            return RedirectResponse(
                url="/admin/jwks?error=Key+not+found",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        logger.info("Admin page: activated JWKS key kid=%s", kid)
        return RedirectResponse(
            url=f"/admin/jwks/{kid}?success=Key+activated+successfully",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except ValueError as e:
        return RedirectResponse(
            url=f"/admin/jwks/{kid}?error={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


@router.post("/{kid}/revoke", response_class=RedirectResponse)
async def jwks_revoke_submit(
    kid: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    jwks_service: Annotated[JWKSService, Depends(get_jwks_service)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_jwks_revoke)],
) -> RedirectResponse:
    """Handle JWKS key revocation."""
    logger.debug("Admin page: revoking JWKS key kid=%s", kid)

    jwk = await jwks_service.revoke_key(db, kid)

    if not jwk:
        return RedirectResponse(
            url="/admin/jwks?error=Key+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    logger.info("Admin page: revoked JWKS key kid=%s", kid)
    return RedirectResponse(
        url=f"/admin/jwks/{kid}?success=Key+revoked+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{kid}/delete", response_class=RedirectResponse)
async def jwks_delete_submit(
    kid: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    jwks_service: Annotated[JWKSService, Depends(get_jwks_service)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_jwks_delete)],
) -> RedirectResponse:
    """Handle JWKS key deletion."""
    logger.debug("Admin page: deleting JWKS key kid=%s", kid)

    deleted = await jwks_service.delete(db, kid)

    if not deleted:
        return RedirectResponse(
            url=f"/admin/jwks/{kid}?error=Key+not+found+or+not+revoked",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    logger.info("Admin page: deleted JWKS key kid=%s", kid)
    return RedirectResponse(
        url="/admin/jwks?success=Key+deleted+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/rotate", response_class=RedirectResponse)
async def jwks_rotate_submit(
    db: Annotated[AsyncSession, Depends(get_db)],
    jwks_service: Annotated[JWKSService, Depends(get_jwks_service)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_jwks_rotate)],
) -> RedirectResponse:
    """Handle JWKS key rotation."""
    logger.debug("Admin page: rotating JWKS keys")

    try:
        jwk = await jwks_service.rotate_keys(db)
        logger.info("Admin page: rotated JWKS keys, new active key kid=%s", jwk.kid)
        return RedirectResponse(
            url=f"/admin/jwks/{jwk.kid}?success=Keys+rotated+successfully",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        logger.error("Admin page: failed to rotate keys: %s", e)
        return RedirectResponse(
            url=f"/admin/jwks?error={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
