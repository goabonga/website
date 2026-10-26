# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Admin OAuth2 clients management HTML pages."""

import logging
import secrets
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db, get_templates, get_user_admin_permissions, require_scope
from auth.core.security import hash_password
from auth.db.models.oauth2 import AccessToken, OAuth2Client
from auth.db.models.rbac import Role
from auth.db.models.user import User
from auth.services.oauth2_client import OAuth2ClientService
from auth.services.scope import scope_service as _scope_service
from auth.services.tenant import tenant_service as _tenant_service
from auth.services.token_admin import token_admin_service as _token_admin_service
from auth.services.user import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clients")

_client_service = OAuth2ClientService()
_user_service = UserService()

# Scope dependencies
require_clients_read = require_scope("clients:read", redirect_to_login=True)
require_clients_write = require_scope("clients:write", redirect_to_login=True)
require_clients_delete = require_scope("clients:delete", redirect_to_login=True)
require_clients_rotate = require_scope("clients:rotate", redirect_to_login=True)


def generate_client_id() -> str:
    """Generate a unique client ID."""
    return secrets.token_urlsafe(24)


def generate_client_secret() -> str:
    """Generate a secure client secret."""
    return secrets.token_urlsafe(32)


def client_to_dict(client: OAuth2Client, tenant_name: str | None = None) -> dict:
    """Convert OAuth2Client model to dictionary format."""
    return {
        "id": str(client.id),
        "client_id": client.client_id,
        "name": client.name,
        "description": client.description,
        "homepage_url": client.homepage_url,
        "redirect_uris": client.redirect_uris,
        "allowed_scopes": client.allowed_scopes,
        "allowed_grant_types": client.allowed_grant_types,
        "token_endpoint_auth_method": client.token_endpoint_auth_method,
        "is_confidential": client.is_confidential,
        "is_active": client.is_active,
        "require_pkce": client.require_pkce,
        "require_consent": client.require_consent,
        "allowed_origins": client.allowed_origins,
        "jwks_uri": client.jwks_uri,
        "access_token_expiry_seconds": client.access_token_expiry_seconds,
        "refresh_token_expiry_seconds": client.refresh_token_expiry_seconds,
        "tenant_id": str(client.tenant_id) if client.tenant_id else None,
        "tenant_name": tenant_name,
        "created_at": client.created_at.isoformat() if client.created_at else None,
        "updated_at": client.updated_at.isoformat() if client.updated_at else None,
    }


# Standard OIDC scopes (always available)
OIDC_SCOPES = [
    {"name": "openid", "description": "OpenID Connect authentication", "category": "oidc"},
    {
        "name": "profile",
        "description": "User profile information (name, picture, etc.)",
        "category": "oidc",
    },
    {"name": "email", "description": "User email address", "category": "oidc"},
    {
        "name": "offline_access",
        "description": "Refresh tokens for offline access",
        "category": "oidc",
    },
]

# System scopes for internal OAuth2 operations
SYSTEM_SCOPES = [
    {"name": "introspect", "description": "Introspect tokens (RFC 7662)", "category": "system"},
]


async def get_available_scopes(db: AsyncSession) -> dict[str, list[dict]]:
    """Get all available scopes grouped by resource.

    For OIDC scopes (openid, profile, email, offline_access), they are grouped under 'oidc'.
    For system scopes (introspect), they are grouped under 'system'.
    For other scopes, they are grouped by their resource prefix (e.g., 'users', 'clients', etc.).
    """
    # Start with OIDC scopes under 'oidc' group and system scopes under 'system' group
    scopes_by_resource: dict[str, list[dict]] = {
        "oidc": OIDC_SCOPES.copy(),
        "system": SYSTEM_SCOPES.copy(),
    }

    # Fetch custom/admin scopes from database
    db_scopes = await _scope_service.list_active_ordered_by_resource_action(db)

    for scope in db_scopes:
        # Group by resource (e.g., 'users', 'clients', 'sessions', etc.)
        resource = scope.resource
        if resource not in scopes_by_resource:
            scopes_by_resource[resource] = []
        scopes_by_resource[resource].append(
            {
                "name": scope.name,
                "description": scope.description or f"{scope.resource}:{scope.action}",
                "resource": resource,
                "action": scope.action,
            }
        )

    return scopes_by_resource


@router.get("", response_class=HTMLResponse)
async def clients_list_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_clients_read)],
    page: Annotated[int, Query(ge=1)] = 1,
    search: Annotated[str | None, Query(max_length=255)] = None,
    tenant_filter: Annotated[str | None, Query(alias="tenant")] = None,
) -> HTMLResponse:
    """Clients list page."""
    logger.debug("Admin page: listing clients")
    templates = get_templates()

    limit = 20

    filter_no_tenant = False
    tenant_uuid: uuid.UUID | None = None
    if tenant_filter == "global":
        filter_no_tenant = True
    elif tenant_filter:
        try:
            tenant_uuid = uuid.UUID(tenant_filter)
        except ValueError:
            tenant_uuid = None

    clients, total = await _client_service.list(
        db,
        page=page,
        page_size=limit,
        tenant_id=tenant_uuid,
        filter_no_tenant=filter_no_tenant,
        search=search,
    )

    # Build tenant name lookup
    tenant_ids = {c.tenant_id for c in clients if c.tenant_id}
    tenant_names: dict[str, str] = {}
    if tenant_ids:
        pairs = await _tenant_service.list_id_name_pairs(db, ids=tenant_ids)
        tenant_names = {str(tid): name for tid, name in pairs}

    clients_list = [client_to_dict(c, tenant_names.get(str(c.tenant_id))) for c in clients]
    total_pages = (total + limit - 1) // limit

    # Get all tenants for filter dropdown
    all_tenant_pairs = await _tenant_service.list_id_name_pairs(db)
    all_tenants = [{"id": str(tid), "name": name} for tid, name in all_tenant_pairs]

    success = request.query_params.get("success")
    error = request.query_params.get("error")
    new_secret = request.query_params.get("new_secret")

    user, roles = auth
    permissions = get_user_admin_permissions(roles)

    return templates.TemplateResponse(
        request=request,
        name="admin/clients/list.html",
        context={
            "active_section": "clients",
            "clients": clients_list,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "search": search or "",
            "tenant_filter": tenant_filter or "",
            "tenants": all_tenants,
            "success": success,
            "error": error,
            "new_secret": new_secret,
            "permissions": permissions,
        },
    )


@router.get("/create", response_class=HTMLResponse)
async def client_create_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_clients_write)],
) -> HTMLResponse:
    """Client creation form page."""
    logger.debug("Admin page: create client form")
    templates = get_templates()

    error = request.query_params.get("error")
    available_scopes = await get_available_scopes(db)

    # Get tenants for dropdown
    all_tenant_pairs = await _tenant_service.list_id_name_pairs(db)
    all_tenants = [{"id": str(tid), "name": name} for tid, name in all_tenant_pairs]

    user, roles = auth
    permissions = get_user_admin_permissions(roles)

    return templates.TemplateResponse(
        request=request,
        name="admin/clients/create.html",
        context={
            "active_section": "clients",
            "error": error,
            "available_scopes": available_scopes,
            "tenants": all_tenants,
            "permissions": permissions,
        },
    )


# Grant types that require redirect URIs
GRANT_TYPES_REQUIRING_REDIRECT = {"authorization_code"}


@router.post("/create", response_class=RedirectResponse)
async def client_create_submit(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_clients_write)],
) -> RedirectResponse:
    """Handle client creation form submission."""
    form_data = await request.form()

    name = form_data.get("name", "")
    description = form_data.get("description") or None
    homepage_url = form_data.get("homepage_url") or None
    redirect_uris = form_data.get("redirect_uris", "")

    logger.debug("Admin page: creating client name=%s", name)

    # Parse redirect URIs (newline-separated)
    uris = [u.strip() for u in str(redirect_uris).split("\n") if u.strip()]

    # Build scopes list from form fields starting with "scope_"
    scopes = []
    for key, value in form_data.items():
        if key.startswith("scope_") and value == "true":
            scope_name = key[6:]  # Remove "scope_" prefix
            scopes.append(scope_name)

    # Build grant types list from checkboxes
    grants = []
    if form_data.get("grant_authorization_code") == "true":
        grants.append("authorization_code")
    if form_data.get("grant_refresh_token") == "true":
        grants.append("refresh_token")
    if form_data.get("grant_client_credentials") == "true":
        grants.append("client_credentials")
    if form_data.get("grant_device_code") == "true":
        grants.append("urn:ietf:params:oauth:grant-type:device_code")
    if form_data.get("grant_token_exchange") == "true":
        grants.append("urn:ietf:params:oauth:grant-type:token-exchange")
    if form_data.get("grant_password") == "true":
        grants.append("password")

    # Validate at least one grant type is selected
    if not grants:
        return RedirectResponse(
            url="/admin/clients/create?error=At+least+one+grant+type+required",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Check if redirect URIs are required based on selected grant types
    requires_redirect = bool(set(grants) & GRANT_TYPES_REQUIRING_REDIRECT)

    if requires_redirect and not uris:
        return RedirectResponse(
            url="/admin/clients/create?error=Redirect+URI+required+for+authorization_code+grant+type",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        client_id = generate_client_id()
        client_secret = None
        client_secret_hash = None
        is_conf = form_data.get("is_confidential") == "true"

        if is_conf:
            client_secret = generate_client_secret()
            client_secret_hash = hash_password(client_secret)
            token_endpoint_auth_method = "client_secret_basic"
        else:
            token_endpoint_auth_method = "none"

        # Parse custom token expiry settings
        access_token_expiry = form_data.get("access_token_expiry_seconds")
        refresh_token_expiry = form_data.get("refresh_token_expiry_seconds")

        # Parse allowed origins (newline-separated)
        allowed_origins_raw = form_data.get("allowed_origins", "")
        origins = [o.strip() for o in str(allowed_origins_raw).split("\n") if o.strip()]

        # Parse tenant_id
        tenant_id_raw = str(form_data.get("tenant_id", "")).strip()
        client_tenant_id = uuid.UUID(tenant_id_raw) if tenant_id_raw else None

        client = OAuth2Client(
            client_id=client_id,
            client_secret_hash=client_secret_hash,
            name=name,
            description=description,
            homepage_url=homepage_url,
            redirect_uris=uris,
            allowed_scopes=scopes,
            allowed_grant_types=grants,
            allowed_origins=origins or None,
            token_endpoint_auth_method=token_endpoint_auth_method,
            is_confidential=is_conf,
            is_active=True,
            require_pkce=form_data.get("require_pkce") == "true",
            require_consent=form_data.get("require_consent") == "true",
            tenant_id=client_tenant_id,
            access_token_expiry_seconds=int(str(access_token_expiry))
            if access_token_expiry
            else None,
            refresh_token_expiry_seconds=int(str(refresh_token_expiry))
            if refresh_token_expiry
            else None,
        )
        await _client_service.add(db, client)
        await db.commit()
        await db.refresh(client)

        logger.info("Admin page: created client id=%s client_id=%s", client.id, client_id)

        # Redirect with secret shown once
        if client_secret:
            return RedirectResponse(
                url=f"/admin/clients/{client.id}?success=Client+created+successfully&new_secret={client_secret}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        return RedirectResponse(
            url=f"/admin/clients/{client.id}?success=Client+created+successfully",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        logger.error("Admin page: failed to create client: %s", e)
        return RedirectResponse(
            url=f"/admin/clients/create?error={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


@router.get("/{client_id}", response_class=HTMLResponse)
async def client_detail_page(
    request: Request,
    client_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_clients_read)],
    tokens_page: Annotated[int, Query(ge=1)] = 1,
) -> HTMLResponse:
    """Client detail page."""
    logger.debug("Admin page: viewing client id=%s", client_id)
    templates = get_templates()

    client = await _client_service.get_by_id_or_client_id(db, client_id)

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )

    # Pagination settings for tokens
    tokens_limit = 10
    now = datetime.now(UTC)

    # Get paginated tokens for this client
    tokens = await _token_admin_service.list_access_tokens_for_client(
        db, client.id, page=tokens_page, page_size=tokens_limit
    )

    # Build tokens list with user emails
    tokens_list = []
    for token in tokens:
        user_email = None
        if token.user_id:
            user_email = await _user_service.get_primary_email(db, token.user_id)
        tokens_list.append(token_to_dict(token, user_email))

    # Count total and active tokens
    total_tokens = await _token_admin_service.count_access_tokens_for_client(db, client.id)
    active_tokens = await _token_admin_service.count_active_access_tokens_for_client(
        db, client.id, now=now
    )

    # Calculate pagination for tokens
    tokens_total_pages = (
        (total_tokens + tokens_limit - 1) // tokens_limit if total_tokens > 0 else 1
    )

    success = request.query_params.get("success")
    error = request.query_params.get("error")
    new_secret = request.query_params.get("new_secret")

    # Get tenant name
    tenant_name = None
    if client.tenant_id:
        tenant_name = await _tenant_service.get_display_name(db, client.tenant_id)

    user, roles = auth
    permissions = get_user_admin_permissions(roles)

    return templates.TemplateResponse(
        request=request,
        name="admin/clients/detail.html",
        context={
            "active_section": "clients",
            "client": client_to_dict(client, tenant_name),
            "tokens": tokens_list,
            "total_tokens": total_tokens,
            "active_tokens": active_tokens,
            "tokens_page": tokens_page,
            "tokens_total_pages": tokens_total_pages,
            "success": success,
            "error": error,
            "new_secret": new_secret,
            "permissions": permissions,
        },
    )


@router.get("/{client_id}/edit", response_class=HTMLResponse)
async def client_edit_page(
    request: Request,
    client_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_clients_write)],
) -> HTMLResponse:
    """Client edit form page."""
    logger.debug("Admin page: edit client form id=%s", client_id)
    templates = get_templates()

    client = await _client_service.get_by_id_or_client_id(db, client_id)

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )

    error = request.query_params.get("error")
    available_scopes = await get_available_scopes(db)

    # Get tenant name for current client
    tenant_name = None
    if client.tenant_id:
        tenant_name = await _tenant_service.get_display_name(db, client.tenant_id)

    # Get tenants for dropdown
    all_tenant_pairs = await _tenant_service.list_id_name_pairs(db)
    all_tenants = [{"id": str(tid), "name": name} for tid, name in all_tenant_pairs]

    user, roles = auth
    permissions = get_user_admin_permissions(roles)

    return templates.TemplateResponse(
        request=request,
        name="admin/clients/edit.html",
        context={
            "active_section": "clients",
            "client": client_to_dict(client, tenant_name),
            "error": error,
            "available_scopes": available_scopes,
            "tenants": all_tenants,
            "permissions": permissions,
        },
    )


@router.post("/{client_id}/edit", response_class=RedirectResponse)
async def client_edit_submit(
    request: Request,
    client_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_clients_write)],
) -> RedirectResponse:
    """Handle client edit form submission."""
    logger.debug("Admin page: updating client id=%s", client_id)

    form_data = await request.form()

    client = await _client_service.get_by_id_or_client_id(db, client_id)

    if not client:
        return RedirectResponse(
            url="/admin/clients?error=Client+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    name = str(form_data.get("name", ""))
    description = form_data.get("description") or None
    homepage_url = form_data.get("homepage_url") or None
    redirect_uris = form_data.get("redirect_uris", "")

    # Parse redirect URIs (newline-separated)
    uris = [u.strip() for u in str(redirect_uris).split("\n") if u.strip()]

    # Build scopes list from form fields starting with "scope_"
    scopes = []
    for key, value in form_data.items():
        if key.startswith("scope_") and value == "true":
            scope_name = key[6:]  # Remove "scope_" prefix
            scopes.append(scope_name)

    # Build grant types list from checkboxes
    grants = []
    if form_data.get("grant_authorization_code") == "true":
        grants.append("authorization_code")
    if form_data.get("grant_refresh_token") == "true":
        grants.append("refresh_token")
    if form_data.get("grant_client_credentials") == "true":
        grants.append("client_credentials")
    if form_data.get("grant_device_code") == "true":
        grants.append("urn:ietf:params:oauth:grant-type:device_code")
    if form_data.get("grant_token_exchange") == "true":
        grants.append("urn:ietf:params:oauth:grant-type:token-exchange")
    if form_data.get("grant_password") == "true":
        grants.append("password")

    # Validate at least one grant type is selected
    if not grants:
        return RedirectResponse(
            url=f"/admin/clients/{client_id}/edit?error=At+least+one+grant+type+required",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Check if redirect URIs are required based on selected grant types
    requires_redirect = bool(set(grants) & GRANT_TYPES_REQUIRING_REDIRECT)

    if requires_redirect and not uris:
        return RedirectResponse(
            url=f"/admin/clients/{client_id}/edit?error=Redirect+URI+required+for+authorization_code+grant+type",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        # Parse custom token expiry settings
        access_token_expiry = form_data.get("access_token_expiry_seconds")
        refresh_token_expiry = form_data.get("refresh_token_expiry_seconds")

        # Handle client type change (confidential <-> public)
        new_is_confidential = form_data.get("is_confidential") == "true"
        new_secret = None

        if new_is_confidential != client.is_confidential:
            if new_is_confidential:
                # Changing from public to confidential: generate a new secret
                new_secret = generate_client_secret()
                client.client_secret_hash = hash_password(new_secret)
                client.token_endpoint_auth_method = "client_secret_basic"
                logger.info(
                    "Admin page: client id=%s changed from public to confidential", client_id
                )
            else:
                # Changing from confidential to public: remove the secret
                client.client_secret_hash = None
                client.token_endpoint_auth_method = "none"
                # Force PKCE for public clients
                client.require_pkce = True
                logger.info(
                    "Admin page: client id=%s changed from confidential to public", client_id
                )
            client.is_confidential = new_is_confidential

        # Parse allowed origins (newline-separated)
        allowed_origins_raw = form_data.get("allowed_origins", "")
        origins = [o.strip() for o in str(allowed_origins_raw).split("\n") if o.strip()]

        # Parse tenant_id
        tenant_id_raw = str(form_data.get("tenant_id", "")).strip()
        client.tenant_id = uuid.UUID(tenant_id_raw) if tenant_id_raw else None

        client.name = str(name)
        client.description = str(description) if description else None
        client.homepage_url = str(homepage_url) if homepage_url else None
        client.redirect_uris = uris
        client.allowed_scopes = scopes
        client.allowed_grant_types = grants
        client.allowed_origins = origins or None
        client.require_pkce = form_data.get("require_pkce") == "true" or not new_is_confidential
        client.require_consent = form_data.get("require_consent") == "true"
        client.access_token_expiry_seconds = (
            int(str(access_token_expiry)) if access_token_expiry else None
        )
        client.refresh_token_expiry_seconds = (
            int(str(refresh_token_expiry)) if refresh_token_expiry else None
        )

        await db.commit()

        logger.info("Admin page: updated client id=%s", client_id)

        # If a new secret was generated, show it to the user
        if new_secret:
            return RedirectResponse(
                url=f"/admin/clients/{client_id}?success=Client+updated+successfully.+New+secret+generated.&new_secret={new_secret}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        return RedirectResponse(
            url=f"/admin/clients/{client_id}?success=Client+updated+successfully",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        logger.error("Admin page: failed to update client: %s", e)
        return RedirectResponse(
            url=f"/admin/clients/{client_id}/edit?error={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


@router.post("/{client_id}/disable", response_class=RedirectResponse)
async def client_disable_submit(
    client_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_clients_write)],
) -> RedirectResponse:
    """Handle client disable."""
    logger.debug("Admin page: disabling client id=%s", client_id)

    client = await _client_service.get_by_id_or_client_id(db, client_id)

    if not client:
        return RedirectResponse(
            url="/admin/clients?error=Client+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    client.is_active = False
    await db.commit()

    logger.info("Admin page: disabled client id=%s", client_id)
    return RedirectResponse(
        url=f"/admin/clients/{client_id}?success=Client+disabled+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{client_id}/enable", response_class=RedirectResponse)
async def client_enable_submit(
    client_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_clients_write)],
) -> RedirectResponse:
    """Handle client enable."""
    logger.debug("Admin page: enabling client id=%s", client_id)

    client = await _client_service.get_by_id_or_client_id(db, client_id)

    if not client:
        return RedirectResponse(
            url="/admin/clients?error=Client+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    client.is_active = True
    await db.commit()

    logger.info("Admin page: enabled client id=%s", client_id)
    return RedirectResponse(
        url=f"/admin/clients/{client_id}?success=Client+enabled+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{client_id}/rotate-secret", response_class=RedirectResponse)
async def client_rotate_secret_submit(
    client_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_clients_rotate)],
) -> RedirectResponse:
    """Handle client secret rotation."""
    logger.debug("Admin page: rotating secret for client id=%s", client_id)

    client = await _client_service.get_by_id_or_client_id(db, client_id)

    if not client:
        return RedirectResponse(
            url="/admin/clients?error=Client+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if not client.is_confidential:
        return RedirectResponse(
            url=f"/admin/clients/{client_id}?error=Cannot+rotate+secret+for+public+clients",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    new_secret = generate_client_secret()
    client.client_secret_hash = hash_password(new_secret)
    await db.commit()

    logger.info("Admin page: rotated secret for client id=%s", client_id)
    return RedirectResponse(
        url=f"/admin/clients/{client_id}?success=Secret+rotated+successfully&new_secret={new_secret}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{client_id}/delete", response_class=RedirectResponse)
async def client_delete_submit(
    client_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_clients_delete)],
) -> RedirectResponse:
    """Handle client deletion."""
    logger.debug("Admin page: deleting client id=%s", client_id)

    client = await _client_service.get_by_id_or_client_id(db, client_id)

    if not client:
        return RedirectResponse(
            url="/admin/clients?error=Client+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    await _client_service.delete(db, client)
    await db.commit()

    logger.info("Admin page: deleted client id=%s", client_id)
    return RedirectResponse(
        url="/admin/clients?success=Client+deleted+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def token_to_dict(token: AccessToken, user_email: str | None = None) -> dict:
    """Convert AccessToken model to dictionary format."""
    now = datetime.now(UTC)
    is_active = token.revoked_at is None and token.expires_at > now

    return {
        "id": str(token.id),
        "jti": token.jti,
        "user_id": str(token.user_id) if token.user_id else None,
        "user_email": user_email,
        "scopes": token.scopes,
        "is_active": is_active,
        "is_revoked": token.revoked_at is not None,
        "is_expired": token.expires_at <= now,
        "created_at": token.created_at.isoformat() if token.created_at else None,
        "expires_at": token.expires_at.isoformat() if token.expires_at else None,
        "revoked_at": token.revoked_at.isoformat() if token.revoked_at else None,
    }


@router.get("/{client_id}/tokens", response_class=HTMLResponse)
async def client_tokens_page(
    request: Request,
    client_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_clients_read)],
    page: Annotated[int, Query(ge=1)] = 1,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    user_search: Annotated[str | None, Query(alias="user", max_length=255)] = None,
    scope_filter: Annotated[str | None, Query(alias="scope", max_length=64)] = None,
) -> HTMLResponse:
    """Client tokens list page with advanced filters."""
    logger.debug("Admin page: viewing tokens for client id=%s", client_id)
    templates = get_templates()

    # Get the client
    client = await _client_service.get_by_id_or_client_id(db, client_id)

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )

    limit = 20
    now = datetime.now(UTC)

    # Resolve user-email filter to matching user IDs (if requested).
    matching_user_ids: list[uuid.UUID] | None = None
    if user_search:
        matching_user_ids = await _token_admin_service.list_user_ids_by_email_search(
            db, user_search
        )

    # Paginated, filtered tokens + total count
    tokens, total = await _token_admin_service.search_access_tokens_for_client(
        db,
        client.id,
        page=page,
        page_size=limit,
        status_filter=status_filter,
        user_ids=matching_user_ids,
        scope_filter=scope_filter,
        now=now,
    )

    # Build tokens list with user emails
    tokens_list = []
    token: Any
    for token in tokens:
        user_email: str | None = None
        if token.user_id:
            user_email = await _user_service.get_primary_email(db, token.user_id)
        tokens_list.append(token_to_dict(token, user_email))

    total_pages = (total + limit - 1) // limit if total > 0 else 1

    # Get counts for status badges
    active_count = await _token_admin_service.count_active_access_tokens_for_client(
        db, client.id, now=now
    )
    revoked_count = await _token_admin_service.count_revoked_access_tokens_for_client(db, client.id)
    expired_count = await _token_admin_service.count_expired_access_tokens_for_client(
        db, client.id, now=now
    )
    total_all = await _token_admin_service.count_access_tokens_for_client(db, client.id)

    # Get unique scopes for filter dropdown
    available_scopes = await _token_admin_service.list_distinct_scopes_for_client(db, client.id)

    success = request.query_params.get("success")
    error = request.query_params.get("error")

    user, roles = auth
    permissions = get_user_admin_permissions(roles)

    return templates.TemplateResponse(
        request=request,
        name="admin/clients/tokens.html",
        context={
            "active_section": "clients",
            "client": client_to_dict(client),
            "tokens": tokens_list,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "status_filter": status_filter or "",
            "user_search": user_search or "",
            "scope_filter": scope_filter or "",
            "active_count": active_count,
            "revoked_count": revoked_count,
            "expired_count": expired_count,
            "total_all": total_all,
            "available_scopes": available_scopes,
            "success": success,
            "error": error,
            "permissions": permissions,
        },
    )


@router.post("/{client_id}/tokens/{token_id}/revoke", response_class=RedirectResponse)
async def client_token_revoke_submit(
    client_id: str,
    token_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_clients_write)],
) -> RedirectResponse:
    """Handle token revocation."""
    logger.debug("Admin page: revoking token id=%s for client id=%s", token_id, client_id)

    # Get the client
    client = await _client_service.get_by_id_or_client_id(db, client_id)

    if not client:
        return RedirectResponse(
            url="/admin/clients?error=Client+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Get the token
    try:
        token_uuid = uuid.UUID(token_id)
    except ValueError:
        return RedirectResponse(
            url=f"/admin/clients/{client_id}/tokens?error=Invalid+token+ID",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    token = await _token_admin_service.get_access_token_for_client(db, token_uuid, client.id)

    if not token:
        return RedirectResponse(
            url=f"/admin/clients/{client_id}/tokens?error=Token+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if token.revoked_at is not None:
        return RedirectResponse(
            url=f"/admin/clients/{client_id}/tokens?error=Token+already+revoked",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Revoke the token
    now = datetime.now(UTC)
    token.revoked_at = now

    # Also revoke associated refresh tokens
    refresh_tokens = await _token_admin_service.list_refresh_tokens_for_access_token(db, token.id)
    for rt in refresh_tokens:
        if rt.revoked_at is None:
            rt.revoked_at = now

    await db.commit()

    logger.info("Admin page: revoked token id=%s for client id=%s", token_id, client_id)
    return RedirectResponse(
        url=f"/admin/clients/{client_id}/tokens?success=Token+revoked+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{client_id}/tokens/revoke-all", response_class=RedirectResponse)
async def client_tokens_revoke_all_submit(
    client_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_clients_write)],
) -> RedirectResponse:
    """Handle bulk token revocation for a client."""
    logger.debug("Admin page: revoking all tokens for client id=%s", client_id)

    # Get the client
    client = await _client_service.get_by_id_or_client_id(db, client_id)

    if not client:
        return RedirectResponse(
            url="/admin/clients?error=Client+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    now = datetime.now(UTC)

    # Revoke all active access tokens for this client
    tokens = await _token_admin_service.list_active_access_tokens_for_client(db, client.id, now=now)

    revoked_count = 0
    for token in tokens:
        token.revoked_at = now
        revoked_count += 1

    # Also revoke associated refresh tokens
    refresh_tokens = await _token_admin_service.list_active_refresh_tokens_for_client(
        db, client.id, now=now
    )
    for rt in refresh_tokens:
        rt.revoked_at = now

    await db.commit()

    logger.info("Admin page: revoked %d tokens for client id=%s", revoked_count, client_id)
    return RedirectResponse(
        url=f"/admin/clients/{client_id}/tokens?success=Revoked+{revoked_count}+token(s)",
        status_code=status.HTTP_303_SEE_OTHER,
    )
