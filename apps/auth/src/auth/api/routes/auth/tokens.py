# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""User Personal Access Token management endpoints."""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import (
    get_branding_service,
    get_current_user,
    get_db,
    get_pat_service,
    get_user_admin_permissions,
)
from auth.api.schemas.pat import (
    CreatePATRequest,
    CreatePATResponse,
    PATListResponse,
    PATResponse,
    RevokePATRequest,
    UpdatePATScopesRequest,
)
from auth.db.models.pat import PATExpirationPreset, PersonalAccessToken
from auth.db.models.user import User
from auth.middlewares.tenant import get_tenant_context
from auth.services.branding import BrandingService
from auth.services.pat import PersonalAccessTokenService
from auth.services.role import role_service
from auth.services.scope import scope_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings/tokens")


def get_tenant_prefix() -> str:
    """Get the URL prefix for the current tenant if resolved via path."""
    tenant_ctx = get_tenant_context()
    if tenant_ctx and tenant_ctx.tenant_slug and tenant_ctx.resolution_method == "path":
        return f"/t/{tenant_ctx.tenant_slug}"
    return ""


def get_current_tenant_id():
    """Get the current tenant ID from context."""
    tenant_ctx = get_tenant_context()
    return tenant_ctx.tenant_id if tenant_ctx else None


def pat_to_response(pat: PersonalAccessToken) -> PATResponse:
    """Convert PAT model to response."""
    return PATResponse(
        id=str(pat.id),
        name=pat.name,
        description=pat.description,
        scopes=list(pat.scopes),
        token_suffix=pat.token_suffix,
        created_at=pat.created_at,
        expires_at=pat.expires_at,
        last_used_at=pat.last_used_at,
        last_used_ip=pat.last_used_ip,
        use_count=pat.use_count,
        is_expired=pat.is_expired,
        is_revoked=pat.revoked_at is not None,
        tenant_id=str(pat.tenant_id) if pat.tenant_id else None,
        target_client_id=str(pat.target_client_id) if pat.target_client_id else None,
    )


async def get_user_available_scopes(
    db: AsyncSession, user: User
) -> dict[str, dict[str, list[tuple[str, str]]]]:
    """Get scopes available to the user based on their roles.

    Returns scopes grouped by category for the UI.
    """
    # Get user's roles with their scopes
    roles = await role_service.list_user_roles_with_scopes(db, user.id)

    # Collect all scope names the user has
    user_scope_names: set[str] = set()
    has_wildcard = False
    for role in roles:
        for rs in role.role_scopes:
            if rs.scope and rs.scope.is_active:
                if rs.scope.name == "*":
                    has_wildcard = True
                user_scope_names.add(rs.scope.name)

    # If user has wildcard, get all scopes; otherwise restrict to the user's own scopes.
    names_filter = None if has_wildcard else user_scope_names
    all_scopes = await scope_service.list_active(db, names=names_filter)

    # Group by category then resource
    from auth.db.models.tenant import build_scope_groups_from_db

    return build_scope_groups_from_db(list(all_scopes))


# HTML page for token management
@router.get("", response_class=HTMLResponse)
async def tokens_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    branding_service: Annotated[BrandingService, Depends(get_branding_service)],
):
    """Render the Personal Access Token management settings page.

    Returns the full HTML settings page where an authenticated user can view
    their active PATs (shown with a suffix only — never the full secret), create
    new tokens by selecting a name, expiration preset, and a subset of their
    own scopes, and revoke individual or all tokens. Unauthenticated requests
    are redirected to the login page with a `next` parameter so the user lands
    back here after signing in.

    **Specification:** RFC 6750 (tokens issued here are consumed as Bearer
    credentials against the REST API); RFC 6265 (session cookie used to
    authenticate this UI request).

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -b cookies.txt https://auth.example.com/auth/settings/tokens
    ```
    """
    user = await get_current_user(request, db)
    if not user:
        tenant_prefix = get_tenant_prefix()
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get(
            "x-forwarded-host", request.headers.get("host", request.url.netloc)
        )
        path = f"{tenant_prefix}{request.url.path}"
        next_url = f"{scheme}://{host}{path}"
        if request.url.query:
            next_url += f"?{request.url.query}"
        return RedirectResponse(
            url=f"{tenant_prefix}/auth/login?next={next_url}",
            status_code=status.HTTP_302_FOUND,
        )

    # Get available scopes for the UI
    available_scopes = await get_user_available_scopes(db, user)

    # Get user's tokens
    pat_service = get_pat_service()
    tokens, total = await pat_service.list_user_tokens(db, user.id, include_revoked=False)

    # Check if user is admin (for sidebar nav)
    user_roles = await role_service.list_user_roles_with_scopes(db, user.id)
    admin_permissions = get_user_admin_permissions(user_roles)
    is_admin = any(admin_permissions.values())

    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()

    html = await branding_service.render_template(
        db,
        "auth/settings/tokens.html",
        {
            "request": request,
            "user": user,
            "tokens": [pat_to_response(t) for t in tokens],
            "total_tokens": total,
            "active_section": "tokens",
            "available_scopes": available_scopes,
            "is_admin": is_admin,
            "admin_permissions": admin_permissions,
            "tenant_prefix": tenant_prefix,
            "expiration_presets": [
                {"value": "7_days", "label": "7 days"},
                {"value": "30_days", "label": "30 days"},
                {"value": "60_days", "label": "60 days"},
                {"value": "90_days", "label": "90 days (recommended)"},
                {"value": "365_days", "label": "1 year"},
                {"value": "no_expiration", "label": "No expiration"},
                {"value": "custom", "label": "Custom..."},
            ],
        },
        tenant_id=tenant_id,
    )
    return HTMLResponse(content=html)


# JSON API endpoints
@router.get("/api", response_class=JSONResponse)
async def list_tokens(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    pat_service: Annotated[PersonalAccessTokenService, Depends(get_pat_service)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    include_revoked: bool = False,
) -> JSONResponse:
    """List all Personal Access Tokens belonging to the current user.

    Returns a paginated list of the caller's PATs. Each entry exposes metadata
    (name, scopes, expiry, last-used IP and timestamp, use count) plus a
    `token_suffix` for visual identification; the full token secret is never
    returned after creation. Revoked tokens are excluded by default; pass
    `include_revoked=true` to include them for audit purposes.

    **Specification:** RFC 6750 (tokens listed here are Bearer credentials);
    RFC 6265 (session cookie authenticates this request).

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -b cookies.txt \
      "https://auth.example.com/auth/settings/tokens/api?offset=0&limit=20&include_revoked=false"
    ```
    """
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    tokens, total = await pat_service.list_user_tokens(db, user.id, include_revoked, offset, limit)

    response = PATListResponse(
        tokens=[pat_to_response(t) for t in tokens],
        total=total,
        offset=offset,
        limit=limit,
    )

    return JSONResponse(content=response.model_dump(mode="json"))


@router.post("/api", response_class=JSONResponse)
async def create_token(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    pat_service: Annotated[PersonalAccessTokenService, Depends(get_pat_service)],
    data: CreatePATRequest,
) -> JSONResponse:
    """Create a new Personal Access Token for the current user.

    Issues a new PAT scoped to a subset of the caller's own permissions —
    requested scopes that exceed the user's current access are rejected with
    `400`. The full plaintext token secret is returned **once** in the
    `token` field of the response and is never stored or retrievable again;
    the caller must copy it immediately. Subsequent reads via `GET
    /auth/settings/tokens/api/{id}` expose only a `token_suffix` for
    identification.

    **Specification:** RFC 6750 (the issued token is a Bearer credential for
    use against the REST API); RFC 6265 (session cookie authenticates this
    request).

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      -H "Content-Type: application/json" \
      -d '{"name": "CI token", "scopes": ["pats:read"], "expiration": "90_days"}' \
      https://auth.example.com/auth/settings/tokens/api
    ```
    """
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Validate scopes (user can only request scopes they have access to)
    available_scopes = await get_user_available_scopes(db, user)
    available_scope_names: set[str] = set()
    for _cat, resources in available_scopes.items():
        for _res, scope_pairs in resources.items():
            for scope_name, _desc in scope_pairs:
                available_scope_names.add(scope_name)

    # Check all requested scopes are available
    for scope in data.scopes:
        if scope not in available_scope_names:
            raise HTTPException(
                status_code=400,
                detail=f"Scope '{scope}' is not available to you",
            )

    # Parse optional UUIDs
    tenant_id = uuid.UUID(data.tenant_id) if data.tenant_id else None
    target_client_id = uuid.UUID(data.target_client_id) if data.target_client_id else None

    # Map schema expiration to model expiration
    expiration_mapping = {
        "7_days": PATExpirationPreset.DAYS_7,
        "30_days": PATExpirationPreset.DAYS_30,
        "60_days": PATExpirationPreset.DAYS_60,
        "90_days": PATExpirationPreset.DAYS_90,
        "365_days": PATExpirationPreset.DAYS_365,
        "no_expiration": PATExpirationPreset.NO_EXPIRATION,
        "custom": PATExpirationPreset.CUSTOM,
    }
    expiration_preset = expiration_mapping.get(data.expiration.value, PATExpirationPreset.DAYS_90)

    pat, plain_token = await pat_service.create_token(
        db=db,
        user_id=user.id,
        name=data.name,
        scopes=data.scopes,
        description=data.description,
        expiration_preset=expiration_preset,
        custom_expiration_days=data.custom_expiration_days,
        tenant_id=tenant_id,
        target_client_id=target_client_id,
    )

    await db.commit()

    response = CreatePATResponse(
        token=plain_token,  # Only time the token is shown!
        pat=pat_to_response(pat),
    )

    return JSONResponse(
        status_code=201,
        content=response.model_dump(mode="json"),
    )


@router.get("/api/{token_id}", response_class=JSONResponse)
async def get_token(
    token_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    pat_service: Annotated[PersonalAccessTokenService, Depends(get_pat_service)],
) -> JSONResponse:
    """Retrieve metadata for a single Personal Access Token.

    Returns all stored metadata for one of the caller's PATs identified by
    its UUID. The full token secret is never included in this response —
    only the `token_suffix` is returned for visual identification. Returns
    `404` if the token does not exist or belongs to a different user.

    **Specification:** RFC 6750 (the token described here is a Bearer
    credential); RFC 6265 (session cookie authenticates this request).

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -b cookies.txt \
      https://auth.example.com/auth/settings/tokens/api/550e8400-e29b-41d4-a716-446655440000
    ```
    """
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        pat_uuid = uuid.UUID(token_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid token ID")

    pat = await pat_service.get_token_by_id(db, pat_uuid, user.id)

    if not pat:
        raise HTTPException(status_code=404, detail="Token not found")

    return JSONResponse(content=pat_to_response(pat).model_dump(mode="json"))


@router.patch("/api/{token_id}", response_class=JSONResponse)
async def update_token_scopes(
    token_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    pat_service: Annotated[PersonalAccessTokenService, Depends(get_pat_service)],
    data: UpdatePATScopesRequest,
) -> JSONResponse:
    """Update the scope set assigned to an existing Personal Access Token.

    Replaces the current scopes of a PAT with the provided list. The new
    scopes must be a strict subset of the caller's own permissions; any scope
    not held by the user is rejected with `400`. Revoked tokens cannot be
    updated and return `404`. The token secret itself is unchanged and is
    not returned in this response.

    **Specification:** RFC 6750 (the token modified here is a Bearer
    credential); RFC 6265 (session cookie authenticates this request).

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -X PATCH -b cookies.txt \
      -H "Content-Type: application/json" \
      -d '{"scopes": ["pats:read", "pats:write"]}' \
      https://auth.example.com/auth/settings/tokens/api/550e8400-e29b-41d4-a716-446655440000
    ```
    """
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        pat_uuid = uuid.UUID(token_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid token ID")

    # Validate scopes
    available_scopes = await get_user_available_scopes(db, user)
    available_scope_names: set[str] = set()
    for _cat, resources in available_scopes.items():
        for _res, scope_pairs in resources.items():
            for scope_name, _desc in scope_pairs:
                available_scope_names.add(scope_name)

    for scope in data.scopes:
        if scope not in available_scope_names:
            raise HTTPException(
                status_code=400,
                detail=f"Scope '{scope}' is not available to you",
            )

    pat = await pat_service.update_token_scopes(db, pat_uuid, user.id, data.scopes)

    if not pat:
        raise HTTPException(status_code=404, detail="Token not found or revoked")

    await db.commit()

    return JSONResponse(content=pat_to_response(pat).model_dump(mode="json"))


@router.delete("/api/{token_id}", response_class=JSONResponse)
async def revoke_token(
    token_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    pat_service: Annotated[PersonalAccessTokenService, Depends(get_pat_service)],
    data: RevokePATRequest | None = None,
) -> JSONResponse:
    """Permanently revoke a single Personal Access Token.

    Marks the specified PAT as revoked; it can no longer be used as a Bearer
    credential against any API endpoint. Revocation is irreversible — the
    token cannot be re-activated. An optional `reason` string may be provided
    in the request body for audit-log purposes. Returns `404` if the token
    does not exist or belongs to a different user.

    **Specification:** RFC 6750 (the token revoked here is a Bearer
    credential); RFC 6265 (session cookie authenticates this request).

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -X DELETE -b cookies.txt \
      https://auth.example.com/auth/settings/tokens/api/550e8400-e29b-41d4-a716-446655440000
    ```
    """
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        pat_uuid = uuid.UUID(token_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid token ID")

    reason = data.reason if data else None
    success = await pat_service.revoke_token(
        db,
        pat_uuid,
        user.id,
        revoked_by=user.id,
        reason=reason,
    )

    if not success:
        raise HTTPException(status_code=404, detail="Token not found")

    await db.commit()

    return JSONResponse(content={"message": "Token revoked successfully"})


@router.post("/api/{token_id}/regenerate", response_class=JSONResponse)
async def regenerate_token(
    token_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    pat_service: Annotated[PersonalAccessTokenService, Depends(get_pat_service)],
) -> JSONResponse:
    """Regenerate a Personal Access Token, preserving its name and scopes.

    Atomically revokes the existing PAT and issues a replacement that inherits
    the original token's name, scopes, and expiration settings. The new
    plaintext token secret is returned **once** in the `token` field and is
    never stored or retrievable again; the caller must copy it immediately.
    Use this endpoint to rotate a compromised or expiring token without
    reconfiguring its permissions.

    **Specification:** RFC 6750 (the reissued token is a Bearer credential);
    RFC 6265 (session cookie authenticates this request).

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      https://auth.example.com/auth/settings/tokens/api/550e8400-e29b-41d4-a716-446655440000/regenerate
    ```
    """
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        pat_uuid = uuid.UUID(token_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid token ID")

    result = await pat_service.regenerate_token(db, pat_uuid, user.id)

    if not result:
        raise HTTPException(status_code=404, detail="Token not found")

    new_pat, plain_token = result
    await db.commit()

    response = CreatePATResponse(
        token=plain_token,
        pat=pat_to_response(new_pat),
    )

    return JSONResponse(
        status_code=201,
        content=response.model_dump(mode="json"),
    )


@router.delete("/api", response_class=JSONResponse)
async def revoke_all_tokens(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    pat_service: Annotated[PersonalAccessTokenService, Depends(get_pat_service)],
    reason: str | None = None,
) -> JSONResponse:
    """Revoke all Personal Access Tokens belonging to the current user.

    Bulk-revokes every active PAT owned by the authenticated user in a single
    operation. An optional `reason` query parameter is recorded in the
    audit log for each revoked token; if omitted, a default message is used.
    Returns the count of tokens actually revoked. This action is irreversible
    and immediately invalidates all affected Bearer credentials.

    **Specification:** RFC 6750 (all tokens revoked here are Bearer
    credentials); RFC 6265 (session cookie authenticates this request).

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -X DELETE -b cookies.txt \
      "https://auth.example.com/auth/settings/tokens/api?reason=account+compromise"
    ```
    """
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    count = await pat_service.bulk_revoke(
        db,
        user.id,
        revoked_by=user.id,
        reason=reason or "User requested revocation of all tokens",
    )

    await db.commit()

    return JSONResponse(
        content={
            "message": f"Revoked {count} token(s)",
            "revoked_count": count,
        }
    )
