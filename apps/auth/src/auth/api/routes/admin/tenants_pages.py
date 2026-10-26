# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Admin tenant management HTML pages."""

import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import (
    get_db,
    get_encryption,
    get_templates,
    get_trust_service,
    get_user_admin_permissions,
    require_scope,
)
from auth.config import settings as app_settings
from auth.db.models.rbac import Role
from auth.db.models.tenant import (
    IdentityProvider,
    IdentityProviderType,
    Tenant,
    TenantBranding,
    TenantMember,
    TenantTrustMode,
    build_scope_groups_from_db,
)
from auth.db.models.user import User
from auth.services.branding import BrandingConfig, BrandingService
from auth.services.scope import scope_service as _scope_service
from auth.services.tenant import tenant_service as _tenant_service
from auth.services.tenant_role import tenant_role_service
from auth.services.trust import TrustPolicyService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/organisations")

# Scope dependencies
require_tenants_read = require_scope("org:read", redirect_to_login=True)
require_tenants_write = require_scope("org:write", redirect_to_login=True)
require_tenants_delete = require_scope("org:delete", redirect_to_login=True)


def tenant_to_dict(tenant: Tenant) -> dict:
    """Convert Tenant model to dictionary format.

    Uses SQLAlchemy inspect to check if relationships are loaded,
    avoiding async lazy loading issues.
    """
    from sqlalchemy import inspect

    insp = inspect(tenant)

    # Only access relationships if they were eagerly loaded
    members_loaded = "members" not in insp.unloaded
    idp_loaded = "identity_providers" not in insp.unloaded

    return {
        "id": str(tenant.id),
        "slug": tenant.slug,
        "display_name": tenant.display_name,
        "custom_domain": tenant.custom_domain,
        "is_active": tenant.is_active,
        "is_platform": tenant.is_platform,
        "settings": tenant.settings or {},
        "members_count": len(tenant.members) if members_loaded and tenant.members else 0,
        "idp_count": len(tenant.identity_providers)
        if idp_loaded and tenant.identity_providers
        else 0,
        "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
        "updated_at": tenant.updated_at.isoformat() if tenant.updated_at else None,
    }


def member_to_dict(member: TenantMember, user_email: str | None = None) -> dict:
    """Convert TenantMember model to dictionary format."""
    return {
        "id": str(member.id),
        "user_id": str(member.user_id),
        "user_email": user_email,
        "user_name": member.user.profile.name if member.user and member.user.profile else None,
        "role": member.role_name,
        "role_display_name": member.role_display_name,
        "joined_at": member.joined_at.isoformat() if member.joined_at else None,
        "invited_at": member.invited_at.isoformat() if member.invited_at else None,
        "created_at": member.created_at.isoformat() if member.created_at else None,
    }


def idp_to_dict(idp: IdentityProvider) -> dict:
    """Convert IdentityProvider model to dictionary format."""
    return {
        "id": str(idp.id),
        "name": idp.name,
        "provider_type": idp.provider_type.value,
        "client_id": idp.client_id,
        "discovery_url": idp.discovery_url,
        "scopes": idp.scopes,
        "is_active": idp.is_active,
        "is_default": idp.is_default,
        "auto_provision": idp.auto_provision,
        "allow_linking": idp.allow_linking,
        "icon_url": idp.icon_url,
        "button_text": idp.button_text,
        "display_order": idp.display_order,
        "federated_count": len(idp.federated_identities) if idp.federated_identities else 0,
        "created_at": idp.created_at.isoformat() if idp.created_at else None,
        "updated_at": idp.updated_at.isoformat() if idp.updated_at else None,
    }


def branding_to_dict(branding: TenantBranding | None) -> dict | None:
    """Convert TenantBranding model to dictionary format."""
    if not branding:
        return None
    return {
        "id": str(branding.id),
        "tenant_id": str(branding.tenant_id),
        "logo_url": branding.logo_url,
        "logo_dark_url": branding.logo_dark_url,
        "favicon_url": branding.favicon_url,
        "primary_color": branding.primary_color,
        "secondary_color": branding.secondary_color,
        "accent_color": branding.accent_color,
        "background_color": branding.background_color,
        "surface_color": branding.surface_color,
        "text_color": branding.text_color,
        "text_muted_color": branding.text_muted_color,
        "error_color": branding.error_color,
        "success_color": branding.success_color,
        "border_color": branding.border_color,
        "warning_color": branding.warning_color,
        "info_color": branding.info_color,
        "input_background_color": branding.input_background_color,
        "input_focus_background_color": branding.input_focus_background_color,
        "input_border_color": branding.input_border_color,
        "input_focus_border_color": branding.input_focus_border_color,
        "input_text_color": branding.input_text_color,
        "font_family": branding.font_family,
        "font_url": branding.font_url,
        "custom_css": branding.custom_css,
        "custom_js": branding.custom_js,
        "show_powered_by": branding.show_powered_by,
        "created_at": branding.created_at.isoformat() if branding.created_at else None,
        "updated_at": branding.updated_at.isoformat() if branding.updated_at else None,
    }


def template_to_dict(template) -> dict:
    """Convert TenantTemplate model to dictionary format."""
    return {
        "id": str(template.id),
        "tenant_id": str(template.tenant_id),
        "template_name": template.template_name,
        "content": template.content,
        "is_active": template.is_active,
        "description": template.description,
        "created_at": template.created_at.isoformat() if template.created_at else None,
        "updated_at": template.updated_at.isoformat() if template.updated_at else None,
    }


@router.get("", response_class=HTMLResponse)
async def tenants_list_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_read)],
    page: Annotated[int, Query(ge=1)] = 1,
    search: Annotated[str | None, Query(max_length=255)] = None,
) -> HTMLResponse:
    """Tenants list page."""
    logger.debug("Admin page: listing tenants")
    templates = get_templates()

    limit = 20

    tenants, total = await _tenant_service.list_tenants(
        db,
        page=page,
        page_size=limit,
        search=search,
        eager_members=True,
        eager_idps=True,
    )

    tenants_list = [tenant_to_dict(t) for t in tenants]
    total_pages = (total + limit - 1) // limit

    success = request.query_params.get("success")
    error = request.query_params.get("error")

    user, roles = auth
    permissions = get_user_admin_permissions(roles)

    return templates.TemplateResponse(
        request=request,
        name="admin/tenants/list.html",
        context={
            "active_section": "tenants",
            "tenants": tenants_list,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "search": search or "",
            "success": success,
            "error": error,
            "permissions": permissions,
        },
    )


@router.get("/create", response_class=HTMLResponse)
async def tenant_create_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> HTMLResponse:
    """Tenant creation form page."""
    logger.debug("Admin page: create tenant form")
    templates = get_templates()

    error = request.query_params.get("error")

    user, roles = auth
    permissions = get_user_admin_permissions(roles)

    return templates.TemplateResponse(
        request=request,
        name="admin/tenants/create.html",
        context={
            "active_section": "tenants",
            "error": error,
            "permissions": permissions,
        },
    )


@router.post("/create", response_class=RedirectResponse)
async def tenant_create_submit(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> RedirectResponse:
    """Handle tenant creation form submission."""
    form_data = await request.form()

    slug = str(form_data.get("slug", "")).strip().lower()
    display_name = str(form_data.get("display_name", "")).strip()
    custom_domain = str(form_data.get("custom_domain", "")).strip() or None

    logger.debug("Admin page: creating tenant slug=%s", slug)

    if not slug:
        return RedirectResponse(
            url="/admin/organisations/create?error=Slug+is+required",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if not display_name:
        return RedirectResponse(
            url="/admin/organisations/create?error=Display+name+is+required",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Validate slug format (alphanumeric and hyphens only)
    import re

    if not re.match(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$", slug):
        return RedirectResponse(
            url="/admin/organisations/create?error=Slug+must+contain+only+lowercase+letters,+numbers,+and+hyphens",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        # Check for duplicate slug
        if await _tenant_service.slug_exists(db, slug):
            return RedirectResponse(
                url="/admin/organisations/create?error=Slug+already+exists",
                status_code=status.HTTP_303_SEE_OTHER,
            )

        # The default roles (owner, admin, member...) are what members are attached to.
        tenant = await _tenant_service.create_tenant(
            db,
            slug=slug,
            display_name=display_name,
            custom_domain=custom_domain,
            is_active=form_data.get("is_active") == "true",
        )
        await db.commit()
        await db.refresh(tenant)

        logger.info("Admin page: created tenant id=%s slug=%s", tenant.id, slug)

        return RedirectResponse(
            url=f"/admin/organisations/{tenant.id}?success=Tenant+created+successfully",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        logger.error("Admin page: failed to create tenant: %s", e)
        return RedirectResponse(
            url=f"/admin/organisations/create?error={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


@router.get("/{tenant_id}", response_class=HTMLResponse)
async def tenant_detail_page(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_read)],
    trust_service: Annotated[TrustPolicyService, Depends(get_trust_service)],
) -> HTMLResponse:
    """Tenant detail page."""
    logger.debug("Admin page: viewing tenant id=%s", tenant_id)
    templates = get_templates()

    tenant = await _tenant_service.resolve_with_detail(db, tenant_id)

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    # Get member emails
    members_list = []
    for member in tenant.members:
        user_email = await _tenant_service.get_member_primary_email(db, member.user_id)
        members_list.append(member_to_dict(member, user_email))

    # Sort by role then name
    role_order = {"owner": 0, "admin": 1, "member": 2}
    members_list.sort(key=lambda m: (role_order.get(m["role"], 99), m.get("user_name") or ""))

    idps_list = [idp_to_dict(idp) for idp in tenant.identity_providers]
    idps_list.sort(key=lambda i: i["display_order"])

    success = request.query_params.get("success")
    error = request.query_params.get("error")

    user, roles = auth
    permissions = get_user_admin_permissions(roles)

    # Get trust policy data
    trust_config = await trust_service.get_tenant_trust_config(db, tenant.id)
    available_tenants = await trust_service.get_available_tenants_for_trust(db, tenant.id)

    # Prepare roles with member counts
    tenant_roles = []
    role_member_counts = {}
    for role in sorted(tenant.roles, key=lambda r: r.display_order):
        # Count members with this role
        member_count = sum(1 for m in tenant.members if m.role_id == role.id)
        role_member_counts[str(role.id)] = member_count
        tenant_roles.append(
            {
                "id": str(role.id),
                "name": role.name,
                "display_name": role.display_name,
                "description": role.description,
                "scopes": role.scopes,
                "is_system": role.is_system,
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="admin/tenants/detail.html",
        context={
            "active_section": "tenants",
            "tenant": tenant_to_dict(tenant),
            "tenant_base_domain": app_settings.tenant_base_domain,
            "members": members_list,
            "identity_providers": idps_list,
            "trust_mode": trust_config["trust_mode"] if trust_config else "none",
            "trusted_sources": trust_config["trusted_sources"] if trust_config else [],
            "available_tenants": available_tenants,
            "success": success,
            "error": error,
            "permissions": permissions,
            "tenant_roles": tenant_roles,
            "role_member_counts": role_member_counts,
            "idp_types": [t.value for t in IdentityProviderType],
        },
    )


@router.get("/{tenant_id}/edit", response_class=HTMLResponse)
async def tenant_edit_page(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> HTMLResponse:
    """Tenant edit form page."""
    logger.debug("Admin page: edit tenant form id=%s", tenant_id)
    templates = get_templates()

    tenant = await _tenant_service.resolve(db, tenant_id)

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    error = request.query_params.get("error")

    user, roles = auth
    permissions = get_user_admin_permissions(roles)

    return templates.TemplateResponse(
        request=request,
        name="admin/tenants/edit.html",
        context={
            "active_section": "tenants",
            "tenant": tenant_to_dict(tenant),
            "tenant_base_domain": app_settings.tenant_base_domain,
            "error": error,
            "permissions": permissions,
        },
    )


@router.post("/{tenant_id}/edit", response_class=RedirectResponse)
async def tenant_edit_submit(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> RedirectResponse:
    """Handle tenant edit form submission."""
    logger.debug("Admin page: updating tenant id=%s", tenant_id)

    form_data = await request.form()

    tenant = await _tenant_service.resolve(db, tenant_id)

    if not tenant:
        return RedirectResponse(
            url="/admin/organisations?error=Tenant+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    display_name = str(form_data.get("display_name", "")).strip()
    custom_domain = str(form_data.get("custom_domain", "")).strip() or None

    if not display_name:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}/edit?error=Display+name+is+required",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        tenant.display_name = display_name
        tenant.custom_domain = custom_domain
        tenant.is_active = form_data.get("is_active") == "true"

        await db.commit()

        logger.info("Admin page: updated tenant id=%s", tenant_id)

        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?success=Tenant+updated+successfully",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        logger.error("Admin page: failed to update tenant: %s", e)
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}/edit?error={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


@router.post("/{tenant_id}/disable", response_class=RedirectResponse)
async def tenant_disable_submit(
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> RedirectResponse:
    """Handle tenant disable."""
    logger.debug("Admin page: disabling tenant id=%s", tenant_id)

    tenant = await _tenant_service.resolve(db, tenant_id)

    if not tenant:
        return RedirectResponse(
            url="/admin/organisations?error=Tenant+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    tenant.is_active = False
    await db.commit()

    logger.info("Admin page: disabled tenant id=%s", tenant_id)
    return RedirectResponse(
        url=f"/admin/organisations/{tenant_id}?success=Tenant+disabled+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{tenant_id}/enable", response_class=RedirectResponse)
async def tenant_enable_submit(
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> RedirectResponse:
    """Handle tenant enable."""
    logger.debug("Admin page: enabling tenant id=%s", tenant_id)

    tenant = await _tenant_service.resolve(db, tenant_id)

    if not tenant:
        return RedirectResponse(
            url="/admin/organisations?error=Tenant+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    tenant.is_active = True
    await db.commit()

    logger.info("Admin page: enabled tenant id=%s", tenant_id)
    return RedirectResponse(
        url=f"/admin/organisations/{tenant_id}?success=Tenant+enabled+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{tenant_id}/delete", response_class=RedirectResponse)
async def tenant_delete_submit(
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_delete)],
) -> RedirectResponse:
    """Handle tenant deletion."""
    logger.debug("Admin page: deleting tenant id=%s", tenant_id)

    tenant = await _tenant_service.resolve(db, tenant_id)

    if not tenant:
        return RedirectResponse(
            url="/admin/organisations?error=Tenant+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    await _tenant_service.delete_tenant(db, tenant)
    await db.commit()

    logger.info("Admin page: deleted tenant id=%s", tenant_id)
    return RedirectResponse(
        url="/admin/organisations?success=Tenant+deleted+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ============================================================
# Member Management
# ============================================================


@router.post("/{tenant_id}/members/add", response_class=RedirectResponse)
async def tenant_add_member_submit(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> RedirectResponse:
    """Add a member to the tenant."""
    logger.debug("Admin page: adding member to tenant id=%s", tenant_id)

    form_data = await request.form()

    tenant = await _tenant_service.resolve(db, tenant_id)

    if not tenant:
        return RedirectResponse(
            url="/admin/organisations?error=Tenant+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    email = str(form_data.get("email", "")).strip().lower()
    role_str = str(form_data.get("role", "member"))

    if not email:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?error=Email+is+required",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Look up the role by ID or name
    role = await _tenant_service.get_custom_role_by_name(db, tenant.id, str(role_str))
    if not role:
        # Fallback to member role
        role = await _tenant_service.get_custom_role_by_name(db, tenant.id, "member")
    if not role:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?error=Role+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Find user by email
    user_email = await _tenant_service.get_user_email_row(db, email)

    if not user_email:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?error=User+not+found+with+email+{email}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Check if already a member
    existing = await _tenant_service.get_existing_membership(db, tenant.id, user_email.user_id)
    if existing:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?error=User+is+already+a+member",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    current_user, _ = auth
    member = TenantMember(
        tenant_id=tenant.id,
        user_id=user_email.user_id,
        role_id=role.id,
        invited_by=current_user.id,
        invited_at=datetime.now(UTC),
        joined_at=datetime.now(UTC),
    )
    await _tenant_service.add_member(db, member)
    await db.commit()

    logger.info(
        "Admin page: added member user_id=%s to tenant id=%s with role %s",
        user_email.user_id,
        tenant_id,
        role.name,
    )
    return RedirectResponse(
        url=f"/admin/organisations/{tenant_id}?success=Member+added+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{tenant_id}/members/{member_id}/update-role", response_class=RedirectResponse)
async def tenant_update_member_role_submit(
    request: Request,
    tenant_id: str,
    member_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> RedirectResponse:
    """Update a member's role."""
    logger.debug(
        "Admin page: updating member role member_id=%s in tenant id=%s", member_id, tenant_id
    )

    form_data = await request.form()

    try:
        member_uuid = uuid.UUID(member_id)
    except ValueError:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?error=Invalid+member+ID",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    member = await _tenant_service.get_member_by_id(db, member_uuid)

    if not member:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?error=Member+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    role_str = str(form_data.get("role", "member"))

    # Look up the role by name
    role = await _tenant_service.get_custom_role_by_name(db, member.tenant_id, str(role_str))
    if not role:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?error=Role+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    member.role_id = role.id
    await db.commit()

    logger.info("Admin page: updated member role member_id=%s to %s", member_id, role.name)
    return RedirectResponse(
        url=f"/admin/organisations/{tenant_id}?success=Member+role+updated",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{tenant_id}/members/{member_id}/remove", response_class=RedirectResponse)
async def tenant_remove_member_submit(
    tenant_id: str,
    member_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> RedirectResponse:
    """Remove a member from the tenant."""
    logger.debug("Admin page: removing member member_id=%s from tenant id=%s", member_id, tenant_id)

    try:
        member_uuid = uuid.UUID(member_id)
    except ValueError:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?error=Invalid+member+ID",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    member = await _tenant_service.get_member_by_id(db, member_uuid)

    if not member:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?error=Member+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    await _tenant_service.remove_member(db, member)
    await db.commit()

    logger.info("Admin page: removed member member_id=%s from tenant id=%s", member_id, tenant_id)
    return RedirectResponse(
        url=f"/admin/organisations/{tenant_id}?success=Member+removed",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ============================================================
# Identity Provider Management
# ============================================================


@router.get("/{tenant_id}/idp/create", response_class=HTMLResponse)
async def tenant_idp_create_page(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> HTMLResponse:
    """Identity provider creation form page."""
    logger.debug("Admin page: create IdP form for tenant id=%s", tenant_id)
    templates = get_templates()

    tenant = await _tenant_service.resolve(db, tenant_id)

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    error = request.query_params.get("error")

    user, roles = auth
    permissions = get_user_admin_permissions(roles)

    return templates.TemplateResponse(
        request=request,
        name="admin/tenants/idp_create.html",
        context={
            "active_section": "tenants",
            "tenant": tenant_to_dict(tenant),
            "idp_types": [{"value": t.value, "label": t.name} for t in IdentityProviderType],
            "error": error,
            "permissions": permissions,
        },
    )


@router.post("/{tenant_id}/idp/create", response_class=RedirectResponse)
async def tenant_idp_create_submit(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> RedirectResponse:
    """Handle IdP creation form submission."""
    form_data = await request.form()

    logger.debug("Admin page: creating IdP for tenant id=%s", tenant_id)

    tenant = await _tenant_service.resolve(db, tenant_id)

    if not tenant:
        return RedirectResponse(
            url="/admin/organisations?error=Tenant+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    name = str(form_data.get("name", "")).strip()
    provider_type_str = str(form_data.get("provider_type", "oidc"))
    client_id = str(form_data.get("client_id", "")).strip()
    client_secret = str(form_data.get("client_secret", "")).strip()
    discovery_url = str(form_data.get("discovery_url", "")).strip() or None
    scopes_str = str(form_data.get("scopes", "openid profile email")).strip()

    if not name or not client_id:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}/idp/create?error=Name+and+Client+ID+are+required",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        provider_type = IdentityProviderType(str(provider_type_str))
    except ValueError:
        provider_type = IdentityProviderType.OIDC

    # Encrypt client secret if provided
    client_secret_encrypted = None
    if client_secret:
        encryption = get_encryption()
        client_secret_encrypted = encryption.encrypt(client_secret.encode())

    scopes = [s.strip() for s in scopes_str.split() if s.strip()]

    try:
        idp = IdentityProvider(
            tenant_id=tenant.id,
            name=name,
            provider_type=provider_type,
            client_id=client_id,
            client_secret_encrypted=client_secret_encrypted,
            discovery_url=discovery_url,
            scopes=scopes,
            is_active=form_data.get("is_active") == "true",
            is_default=form_data.get("is_default") == "true",
            auto_provision=form_data.get("auto_provision") == "true",
            allow_linking=form_data.get("allow_linking") == "true",
            button_text=str(form_data.get("button_text", "")).strip() or None,
            icon_url=str(form_data.get("icon_url", "")).strip() or None,
        )
        await _tenant_service.add_idp(db, idp)
        await db.commit()
        await db.refresh(idp)

        logger.info("Admin page: created IdP id=%s for tenant id=%s", idp.id, tenant_id)

        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?success=Identity+provider+created+successfully",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        logger.error("Admin page: failed to create IdP: %s", e)
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}/idp/create?error={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


@router.get("/{tenant_id}/idp/{idp_id}/edit", response_class=HTMLResponse)
async def tenant_idp_edit_page(
    request: Request,
    tenant_id: str,
    idp_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> HTMLResponse:
    """Identity provider edit form page."""
    logger.debug("Admin page: edit IdP form idp_id=%s for tenant id=%s", idp_id, tenant_id)
    templates = get_templates()

    tenant = await _tenant_service.resolve(db, tenant_id)

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    try:
        idp_uuid = uuid.UUID(idp_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid IdP ID",
        ) from None

    idp = await _tenant_service.get_idp_scoped(db, idp_uuid, tenant.id)

    if not idp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Identity provider not found",
        )

    error = request.query_params.get("error")

    user, roles = auth
    permissions = get_user_admin_permissions(roles)

    idp_dict = idp_to_dict(idp)
    idp_dict["has_secret"] = idp.client_secret_encrypted is not None

    return templates.TemplateResponse(
        request=request,
        name="admin/tenants/idp_edit.html",
        context={
            "active_section": "tenants",
            "tenant": tenant_to_dict(tenant),
            "idp": idp_dict,
            "idp_types": [{"value": t.value, "label": t.name} for t in IdentityProviderType],
            "error": error,
            "permissions": permissions,
        },
    )


@router.post("/{tenant_id}/idp/{idp_id}/edit", response_class=RedirectResponse)
async def tenant_idp_edit_submit(
    request: Request,
    tenant_id: str,
    idp_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> RedirectResponse:
    """Handle IdP edit form submission."""
    logger.debug("Admin page: updating IdP idp_id=%s for tenant id=%s", idp_id, tenant_id)

    form_data = await request.form()

    tenant = await _tenant_service.resolve(db, tenant_id)

    if not tenant:
        return RedirectResponse(
            url="/admin/organisations?error=Tenant+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        idp_uuid = uuid.UUID(idp_id)
    except ValueError:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?error=Invalid+IdP+ID",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    idp = await _tenant_service.get_idp_scoped(db, idp_uuid, tenant.id)

    if not idp:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?error=Identity+provider+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    name = str(form_data.get("name", "")).strip()
    client_id = str(form_data.get("client_id", "")).strip()
    client_secret = str(form_data.get("client_secret", "")).strip()
    discovery_url = str(form_data.get("discovery_url", "")).strip() or None
    scopes_str = str(form_data.get("scopes", "openid profile email")).strip()

    if not name or not client_id:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}/idp/{idp_id}/edit?error=Name+and+Client+ID+are+required",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        idp.name = name
        idp.client_id = client_id
        idp.discovery_url = discovery_url
        idp.scopes = [s.strip() for s in scopes_str.split() if s.strip()]
        idp.is_active = form_data.get("is_active") == "true"
        idp.is_default = form_data.get("is_default") == "true"
        idp.auto_provision = form_data.get("auto_provision") == "true"
        idp.allow_linking = form_data.get("allow_linking") == "true"
        idp.button_text = str(form_data.get("button_text", "")).strip() or None
        idp.icon_url = str(form_data.get("icon_url", "")).strip() or None

        # Only update secret if a new one is provided
        if client_secret:
            encryption = get_encryption()
            idp.client_secret_encrypted = encryption.encrypt(client_secret.encode())

        await db.commit()

        logger.info("Admin page: updated IdP id=%s for tenant id=%s", idp_id, tenant_id)

        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?success=Identity+provider+updated+successfully",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        logger.error("Admin page: failed to update IdP: %s", e)
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}/idp/{idp_id}/edit?error={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


@router.post("/{tenant_id}/idp/{idp_id}/delete", response_class=RedirectResponse)
async def tenant_idp_delete_submit(
    tenant_id: str,
    idp_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> RedirectResponse:
    """Handle IdP deletion."""
    logger.debug("Admin page: deleting IdP idp_id=%s from tenant id=%s", idp_id, tenant_id)

    tenant = await _tenant_service.resolve(db, tenant_id)

    if not tenant:
        return RedirectResponse(
            url="/admin/organisations?error=Tenant+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        idp_uuid = uuid.UUID(idp_id)
    except ValueError:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?error=Invalid+IdP+ID",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    idp = await _tenant_service.get_idp_scoped(db, idp_uuid, tenant.id)

    if not idp:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?error=Identity+provider+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    await _tenant_service.delete_idp(db, idp)
    await db.commit()

    logger.info("Admin page: deleted IdP id=%s from tenant id=%s", idp_id, tenant_id)
    return RedirectResponse(
        url=f"/admin/organisations/{tenant_id}?success=Identity+provider+deleted",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{tenant_id}/idp/{idp_id}/toggle", response_class=RedirectResponse)
async def tenant_idp_toggle_submit(
    tenant_id: str,
    idp_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> RedirectResponse:
    """Toggle IdP active status."""
    logger.debug("Admin page: toggling IdP idp_id=%s for tenant id=%s", idp_id, tenant_id)

    tenant = await _tenant_service.resolve(db, tenant_id)

    if not tenant:
        return RedirectResponse(
            url="/admin/organisations?error=Tenant+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        idp_uuid = uuid.UUID(idp_id)
    except ValueError:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?error=Invalid+IdP+ID",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    idp = await _tenant_service.get_idp_scoped(db, idp_uuid, tenant.id)

    if not idp:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?error=Identity+provider+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    idp.is_active = not idp.is_active
    await db.commit()

    action = "enabled" if idp.is_active else "disabled"
    logger.info("Admin page: %s IdP id=%s for tenant id=%s", action, idp_id, tenant_id)
    return RedirectResponse(
        url=f"/admin/organisations/{tenant_id}?success=Identity+provider+{action}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ============================================================
# Registration Fields Configuration
# ============================================================

_REGISTRATION_FIELD_KEYS = [
    "profile",
    "nickname",
    "firstname",
    "lastname",
    "middle_name",
    "preferred_username",
    "personal_details",
    "gender",
    "birthdate",
    "locale",
    "zoneinfo",
    "phone_number",
    "address",
    "picture",
    "web_presence",
]


@router.get("/{tenant_id}/registration-fields", response_class=HTMLResponse)
async def tenant_registration_fields_page(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_read)],
) -> HTMLResponse:
    """Registration fields configuration page."""
    logger.debug("Admin page: registration fields for tenant id=%s", tenant_id)
    templates = get_templates()

    tenant = await _tenant_service.resolve(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    tenant_settings = tenant.settings or {}
    fields = dict.fromkeys(_REGISTRATION_FIELD_KEYS, True)
    overrides = tenant_settings.get("registration_fields", {})
    for k in fields:
        if k in overrides:
            fields[k] = bool(overrides[k])

    success = request.query_params.get("success")
    error = request.query_params.get("error")

    user, roles = auth
    permissions = get_user_admin_permissions(roles)

    return templates.TemplateResponse(
        request=request,
        name="admin/tenants/registration_fields.html",
        context={
            "active_section": "tenants",
            "tenant": tenant_to_dict(tenant),
            "fields": fields,
            "success": success,
            "error": error,
            "permissions": permissions,
        },
    )


@router.post("/{tenant_id}/registration-fields", response_class=RedirectResponse)
async def tenant_registration_fields_submit(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> RedirectResponse:
    """Save registration fields configuration."""
    logger.debug("Admin page: saving registration fields for tenant id=%s", tenant_id)

    form_data = await request.form()

    tenant = await _tenant_service.resolve(db, tenant_id)
    if not tenant:
        return RedirectResponse(
            url="/admin/organisations?error=Tenant+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        reg_fields = {}
        for key in _REGISTRATION_FIELD_KEYS:
            reg_fields[key] = form_data.get(key) == "true"

        current_settings = dict(tenant.settings or {})
        current_settings["registration_fields"] = reg_fields
        tenant.settings = current_settings

        await db.commit()
        logger.info("Admin page: updated registration fields for tenant id=%s", tenant_id)

        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}/registration-fields?success=Registration+fields+updated",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        logger.error("Admin page: failed to update registration fields: %s", e)
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}/registration-fields?error={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


# ============================================================
# Email Sender Configuration
# ============================================================


@router.post("/{tenant_id}/email-sender", response_class=RedirectResponse)
async def tenant_email_sender_submit(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> RedirectResponse:
    """Save email sender configuration."""
    logger.debug("Admin page: saving email sender for tenant id=%s", tenant_id)

    form_data = await request.form()

    tenant = await _tenant_service.resolve(db, tenant_id)
    if not tenant:
        return RedirectResponse(
            url="/admin/organisations?error=Tenant+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        sender_address = str(form_data.get("email_sender_address", "")).strip() or None
        sender_name = str(form_data.get("email_sender_name", "")).strip() or None

        current_settings = dict(tenant.settings or {})
        current_settings["email_sender_address"] = sender_address
        current_settings["email_sender_name"] = sender_name
        tenant.settings = current_settings

        await db.commit()

        # Invalidate the Celery worker sender cache
        from auth.tasks.email import invalidate_platform_sender_cache

        invalidate_platform_sender_cache()

        logger.info("Admin page: updated email sender for tenant id=%s", tenant_id)

        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?success=Email+sender+updated",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        logger.error("Admin page: failed to update email sender: %s", e)
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?error={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


# ============================================================
# Profile Fields Configuration
# ============================================================

_PROFILE_FIELD_KEYS = [
    "avatar",
    "identity",
    "nickname",
    "preferred_username",
    "given_name",
    "middle_name",
    "family_name",
    "personal_info",
    "gender",
    "birthdate",
    "locale",
    "zoneinfo",
    "contact",
    "phone_number",
    "website",
    "profile_url",
    "picture_url",
    "address",
    "roles_permissions",
]


@router.get("/{tenant_id}/profile-fields", response_class=HTMLResponse)
async def tenant_profile_fields_page(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_read)],
) -> HTMLResponse:
    """Profile fields configuration page."""
    logger.debug("Admin page: profile fields for tenant id=%s", tenant_id)
    templates = get_templates()

    tenant = await _tenant_service.resolve(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    tenant_settings = tenant.settings or {}
    fields = dict.fromkeys(_PROFILE_FIELD_KEYS, True)
    overrides = tenant_settings.get("profile_fields", {})
    for k in fields:
        if k in overrides:
            fields[k] = bool(overrides[k])

    success = request.query_params.get("success")
    error = request.query_params.get("error")
    user, roles = auth
    permissions = get_user_admin_permissions(roles)

    return templates.TemplateResponse(
        request=request,
        name="admin/tenants/profile_fields.html",
        context={
            "active_section": "tenants",
            "tenant": tenant_to_dict(tenant),
            "fields": fields,
            "success": success,
            "error": error,
            "permissions": permissions,
        },
    )


@router.post("/{tenant_id}/profile-fields", response_class=RedirectResponse)
async def tenant_profile_fields_submit(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> RedirectResponse:
    """Save profile fields configuration."""
    logger.debug("Admin page: saving profile fields for tenant id=%s", tenant_id)

    form_data = await request.form()

    tenant = await _tenant_service.resolve(db, tenant_id)
    if not tenant:
        return RedirectResponse(
            url="/admin/organisations?error=Tenant+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        pf = {}
        for key in _PROFILE_FIELD_KEYS:
            pf[key] = form_data.get(key) == "true"

        current_settings = dict(tenant.settings or {})
        current_settings["profile_fields"] = pf
        tenant.settings = current_settings

        await db.commit()
        logger.info("Admin page: updated profile fields for tenant id=%s", tenant_id)

        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}/profile-fields?success=Profile+fields+updated",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        logger.error("Admin page: failed to update profile fields: %s", e)
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}/profile-fields?error={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


# ============================================================
# Allowed Scopes Configuration
# ============================================================


@router.get("/{tenant_id}/allowed-scopes", response_class=HTMLResponse)
async def tenant_allowed_scopes_page(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_read)],
) -> HTMLResponse:
    """Allowed scopes configuration page."""
    logger.debug("Admin page: allowed scopes for tenant id=%s", tenant_id)
    templates = get_templates()

    tenant = await _tenant_service.resolve(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    # Load all active scopes from DB
    all_db_scopes = await _scope_service.list_active(db)

    tenant_settings = tenant.settings or {}
    allowed_list = tenant_settings.get("allowed_scopes")
    current_allowed = set(allowed_list) if allowed_list else set()

    success = request.query_params.get("success")
    error = request.query_params.get("error")

    user, roles = auth
    permissions = get_user_admin_permissions(roles)

    return templates.TemplateResponse(
        request=request,
        name="admin/tenants/allowed_scopes.html",
        context={
            "active_section": "tenants",
            "tenant": tenant_to_dict(tenant),
            "scope_groups": build_scope_groups_from_db(all_db_scopes),
            "current_allowed": current_allowed,
            "success": success,
            "error": error,
            "permissions": permissions,
        },
    )


@router.post("/{tenant_id}/allowed-scopes", response_class=RedirectResponse)
async def tenant_allowed_scopes_submit(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> RedirectResponse:
    """Save allowed scopes configuration."""
    logger.debug("Admin page: saving allowed scopes for tenant id=%s", tenant_id)

    form_data = await request.form()

    tenant = await _tenant_service.resolve(db, tenant_id)
    if not tenant:
        return RedirectResponse(
            url="/admin/organisations?error=Tenant+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        selected = form_data.getlist("allowed_scopes")

        # Validate against DB scopes
        active_scopes = await _scope_service.list_active(db)
        valid = {s.name for s in active_scopes}
        scopes_list = [s for s in selected if s in valid]

        current_settings = dict(tenant.settings or {})
        current_settings["allowed_scopes"] = sorted(scopes_list) if scopes_list else None
        tenant.settings = current_settings

        await db.commit()
        logger.info("Admin page: updated allowed scopes for tenant id=%s", tenant_id)

        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}/allowed-scopes?success=Allowed+scopes+updated",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        logger.error("Admin page: failed to update allowed scopes: %s", e)
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}/allowed-scopes?error={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


# ============================================================
# Branding Management
# ============================================================


@router.get("/{tenant_id}/branding", response_class=HTMLResponse)
async def tenant_branding_page(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_read)],
) -> HTMLResponse:
    """Tenant branding edit page."""
    logger.debug("Admin page: branding for tenant id=%s", tenant_id)
    templates = get_templates()

    tenant = await _tenant_service.resolve_with_branding(db, tenant_id)

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    success = request.query_params.get("success")
    error = request.query_params.get("error")

    user, roles = auth
    permissions = get_user_admin_permissions(roles)

    # Get branding or use defaults
    branding_dict = branding_to_dict(tenant.branding)
    if not branding_dict:
        # Use BrandingConfig defaults
        defaults = BrandingConfig()
        branding_dict = {
            "primary_color": defaults.primary_color,
            "secondary_color": defaults.secondary_color,
            "accent_color": defaults.accent_color,
            "background_color": defaults.background_color,
            "surface_color": defaults.surface_color,
            "text_color": defaults.text_color,
            "text_muted_color": defaults.text_muted_color,
            "error_color": defaults.error_color,
            "success_color": defaults.success_color,
            "border_color": defaults.border_color,
            "warning_color": defaults.warning_color,
            "info_color": defaults.info_color,
            "font_family": defaults.font_family,
            "show_powered_by": defaults.show_powered_by,
        }

    return templates.TemplateResponse(
        request=request,
        name="admin/tenants/branding.html",
        context={
            "active_section": "tenants",
            "tenant": tenant_to_dict(tenant),
            "branding": branding_dict,
            "has_branding": tenant.branding is not None,
            "success": success,
            "error": error,
            "permissions": permissions,
        },
    )


@router.post("/{tenant_id}/branding", response_class=RedirectResponse)
async def tenant_branding_submit(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> RedirectResponse:
    """Handle branding form submission."""
    logger.debug("Admin page: updating branding for tenant id=%s", tenant_id)

    form_data = await request.form()

    tenant = await _tenant_service.resolve_with_branding(db, tenant_id)

    if not tenant:
        return RedirectResponse(
            url="/admin/organisations?error=Tenant+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        branding = tenant.branding
        if not branding:
            branding = TenantBranding(tenant_id=tenant.id)
            await _tenant_service.add_branding(db, branding)

        # Update branding fields
        branding.logo_url = str(form_data.get("logo_url", "")).strip() or None
        branding.logo_dark_url = str(form_data.get("logo_dark_url", "")).strip() or None
        branding.favicon_url = str(form_data.get("favicon_url", "")).strip() or None
        branding.primary_color = str(form_data.get("primary_color", "#007bff")).strip()
        branding.secondary_color = str(form_data.get("secondary_color", "#6c757d")).strip()
        branding.accent_color = str(form_data.get("accent_color", "#28a745")).strip()
        branding.background_color = str(form_data.get("background_color", "#f5f5f5")).strip()
        branding.surface_color = str(form_data.get("surface_color", "#ffffff")).strip()
        branding.text_color = str(form_data.get("text_color", "#333333")).strip()
        branding.text_muted_color = str(form_data.get("text_muted_color", "#6c757d")).strip()
        branding.error_color = str(form_data.get("error_color", "#dc3545")).strip()
        branding.success_color = str(form_data.get("success_color", "#28a745")).strip()
        branding.border_color = str(form_data.get("border_color", "#0f3460")).strip()
        branding.warning_color = str(form_data.get("warning_color", "#fdcb6e")).strip()
        branding.info_color = str(form_data.get("info_color", "#74b9ff")).strip()
        branding.input_background_color = (
            str(form_data.get("input_background_color", "")).strip() or None
        )
        branding.input_focus_background_color = (
            str(form_data.get("input_focus_background_color", "")).strip() or None
        )
        branding.input_border_color = str(form_data.get("input_border_color", "")).strip() or None
        branding.input_focus_border_color = (
            str(form_data.get("input_focus_border_color", "")).strip() or None
        )
        branding.input_text_color = str(form_data.get("input_text_color", "")).strip() or None
        branding.font_family = (
            str(form_data.get("font_family", "")).strip()
            or "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
        )
        branding.font_url = str(form_data.get("font_url", "")).strip() or None
        branding.custom_css = str(form_data.get("custom_css", "")).strip() or None
        branding.custom_js = str(form_data.get("custom_js", "")).strip() or None
        branding.show_powered_by = form_data.get("show_powered_by") == "true"

        await db.commit()

        logger.info("Admin page: updated branding for tenant id=%s", tenant_id)

        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}/branding?success=Branding+updated+successfully",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        logger.error("Admin page: failed to update branding: %s", e)
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}/branding?error={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


@router.post("/{tenant_id}/branding/reset", response_class=RedirectResponse)
async def tenant_branding_reset(
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> RedirectResponse:
    """Reset branding to defaults (delete branding record)."""
    logger.debug("Admin page: resetting branding for tenant id=%s", tenant_id)

    tenant = await _tenant_service.resolve(db, tenant_id)

    if not tenant:
        return RedirectResponse(
            url="/admin/organisations?error=Tenant+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    branding = await _tenant_service.get_branding(db, tenant.id)

    if branding:
        await _tenant_service.delete_branding(db, branding)
        await db.commit()
        logger.info("Admin page: reset branding for tenant id=%s", tenant_id)

    return RedirectResponse(
        url=f"/admin/organisations/{tenant_id}/branding?success=Branding+reset+to+defaults",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ============================================================
# Templates Management
# ============================================================


@router.get("/{tenant_id}/templates", response_class=HTMLResponse)
async def tenant_templates_page(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_read)],
) -> HTMLResponse:
    """Tenant templates list page."""
    logger.debug("Admin page: templates for tenant id=%s", tenant_id)
    templates = get_templates()

    tenant = await _tenant_service.resolve_with_templates(db, tenant_id)

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    success = request.query_params.get("success")
    error = request.query_params.get("error")

    user, roles = auth
    permissions = get_user_admin_permissions(roles)

    # Get existing templates
    tenant_templates = [template_to_dict(t) for t in tenant.templates]
    tenant_templates.sort(key=lambda t: t["template_name"])

    # List of customizable templates
    customizable = BrandingService.CUSTOMIZABLE_TEMPLATES

    return templates.TemplateResponse(
        request=request,
        name="admin/tenants/templates.html",
        context={
            "active_section": "tenants",
            "tenant": tenant_to_dict(tenant),
            "tenant_templates": tenant_templates,
            "customizable_templates": customizable,
            "success": success,
            "error": error,
            "permissions": permissions,
        },
    )


@router.get("/{tenant_id}/templates/{template_name:path}/edit", response_class=HTMLResponse)
async def tenant_template_edit_page(
    request: Request,
    tenant_id: str,
    template_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> HTMLResponse:
    """Template edit page."""
    logger.debug("Admin page: edit template %s for tenant id=%s", template_name, tenant_id)
    templates = get_templates()

    tenant = await _tenant_service.resolve(db, tenant_id)

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    # Check if template is customizable
    if template_name not in BrandingService.CUSTOMIZABLE_TEMPLATES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Template is not customizable",
        )

    # Get existing template if any
    tenant_template = await _tenant_service.get_template(db, tenant.id, template_name)

    # Get default template content
    from pathlib import Path

    templates_dir = Path(__file__).parent.parent.parent.parent / "templates"
    default_path = templates_dir / template_name
    default_content = ""
    if default_path.exists():
        default_content = default_path.read_text(encoding="utf-8")

    success = request.query_params.get("success")
    error = request.query_params.get("error")

    user, roles = auth
    permissions = get_user_admin_permissions(roles)

    return templates.TemplateResponse(
        request=request,
        name="admin/tenants/template_edit.html",
        context={
            "active_section": "tenants",
            "tenant": tenant_to_dict(tenant),
            "template_name": template_name,
            "template": template_to_dict(tenant_template) if tenant_template else None,
            "default_content": default_content,
            "success": success,
            "error": error,
            "permissions": permissions,
        },
    )


@router.post("/{tenant_id}/templates/{template_name:path}/edit", response_class=RedirectResponse)
async def tenant_template_edit_submit(
    request: Request,
    tenant_id: str,
    template_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> RedirectResponse:
    """Handle template edit form submission."""
    logger.debug("Admin page: saving template %s for tenant id=%s", template_name, tenant_id)

    form_data = await request.form()

    tenant = await _tenant_service.resolve(db, tenant_id)

    if not tenant:
        return RedirectResponse(
            url="/admin/organisations?error=Tenant+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Check if template is customizable
    if template_name not in BrandingService.CUSTOMIZABLE_TEMPLATES:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}/templates?error=Template+is+not+customizable",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    content = str(form_data.get("content", "")).strip()
    description = str(form_data.get("description", "")).strip() or None
    is_active = form_data.get("is_active") == "true"

    if not content:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}/templates/{template_name}/edit?error=Content+is+required",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        # Validate syntax: MJML or Jinja2
        if template_name.endswith(".mjml"):
            import mrml

            mrml.to_html(content)
        else:
            from jinja2 import Environment

            env = Environment(autoescape=True)  # nosec B701
            env.parse(content)
    except Exception as e:
        syntax_type = "MJML" if template_name.endswith(".mjml") else "Jinja2"
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}/templates/{template_name}/edit?error=Invalid+{syntax_type}+syntax:+{str(e)[:50]}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        # Get or create template
        await _tenant_service.upsert_template(
            db,
            tenant.id,
            template_name,
            content=content,
            description=description,
            is_active=is_active,
        )

        await db.commit()

        # Invalidate email renderer cache for MJML templates
        if template_name.endswith(".mjml"):
            from auth.services.email_renderer import get_email_renderer

            renderer = get_email_renderer()
            renderer.invalidate_tenant_cache(str(tenant.id), template_name)

        logger.info("Admin page: saved template %s for tenant id=%s", template_name, tenant_id)

        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}/templates?success=Template+saved+successfully",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        logger.error("Admin page: failed to save template: %s", e)
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}/templates/{template_name}/edit?error={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


@router.post("/{tenant_id}/templates/{template_name:path}/delete", response_class=RedirectResponse)
async def tenant_template_delete(
    tenant_id: str,
    template_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> RedirectResponse:
    """Delete a custom template (reverts to default)."""
    logger.debug("Admin page: deleting template %s for tenant id=%s", template_name, tenant_id)

    tenant = await _tenant_service.resolve(db, tenant_id)

    if not tenant:
        return RedirectResponse(
            url="/admin/organisations?error=Tenant+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    tenant_template = await _tenant_service.get_template(db, tenant.id, template_name)

    if tenant_template:
        await _tenant_service.delete_template(db, tenant_template)
        await db.commit()
        logger.info("Admin page: deleted template %s for tenant id=%s", template_name, tenant_id)

    return RedirectResponse(
        url=f"/admin/organisations/{tenant_id}/templates?success=Template+deleted+(reverted+to+default)",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{tenant_id}/templates/{template_name:path}/toggle", response_class=RedirectResponse)
async def tenant_template_toggle(
    tenant_id: str,
    template_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> RedirectResponse:
    """Toggle template active status."""
    logger.debug("Admin page: toggling template %s for tenant id=%s", template_name, tenant_id)

    tenant = await _tenant_service.resolve(db, tenant_id)

    if not tenant:
        return RedirectResponse(
            url="/admin/organisations?error=Tenant+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    tenant_template = await _tenant_service.get_template(db, tenant.id, template_name)

    if not tenant_template:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}/templates?error=Template+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    await _tenant_service.toggle_template(db, tenant_template)
    await db.commit()

    action = "enabled" if tenant_template.is_active else "disabled"
    logger.info("Admin page: %s template %s for tenant id=%s", action, template_name, tenant_id)

    return RedirectResponse(
        url=f"/admin/organisations/{tenant_id}/templates?success=Template+{action}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ============================================================
# Trust Policy Management
# ============================================================


@router.post("/{tenant_id}/trust/mode", response_class=RedirectResponse)
async def tenant_trust_mode_submit(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
    trust_service: Annotated[TrustPolicyService, Depends(get_trust_service)],
) -> RedirectResponse:
    """Update trust mode for a tenant."""
    logger.debug("Admin page: updating trust mode for tenant id=%s", tenant_id)

    tenant = await _tenant_service.resolve(db, tenant_id)
    if not tenant:
        return RedirectResponse(
            url="/admin/organisations?error=Tenant+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    form_data = await request.form()
    trust_mode_str = str(form_data.get("trust_mode", "none"))

    try:
        trust_mode = TenantTrustMode(str(trust_mode_str))
    except ValueError:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?error=Invalid+trust+mode",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    await trust_service.update_trust_mode(db, tenant.id, trust_mode)
    await db.commit()

    logger.info(
        "Admin page: updated trust mode for tenant id=%s to %s", tenant_id, trust_mode.value
    )

    return RedirectResponse(
        url=f"/admin/organisations/{tenant_id}?success=Trust+mode+updated+to+{trust_mode.value}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{tenant_id}/trust/add-source", response_class=RedirectResponse)
async def tenant_trust_add_source(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
    trust_service: Annotated[TrustPolicyService, Depends(get_trust_service)],
) -> RedirectResponse:
    """Add a trusted source tenant."""
    logger.debug("Admin page: adding trusted source for tenant id=%s", tenant_id)

    tenant = await _tenant_service.resolve(db, tenant_id)
    if not tenant:
        return RedirectResponse(
            url="/admin/organisations?error=Tenant+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    form_data = await request.form()
    trusted_tenant_id_str = str(form_data.get("trusted_tenant_id", ""))
    description = str(form_data.get("description", "")).strip() or None

    if not trusted_tenant_id_str:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?error=Please+select+an+organization",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        trusted_tenant_uuid = uuid.UUID(str(trusted_tenant_id_str))
    except ValueError:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?error=Invalid+organization+ID",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    source = await trust_service.add_trusted_source(db, tenant.id, trusted_tenant_uuid, description)

    if not source:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?error=This+organization+is+already+trusted",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    await db.commit()

    logger.info(
        "Admin page: added trusted source %s to tenant id=%s", trusted_tenant_id_str, tenant_id
    )

    return RedirectResponse(
        url=f"/admin/organisations/{tenant_id}?success=Trusted+source+added",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{tenant_id}/trust/remove-source/{source_id}", response_class=RedirectResponse)
async def tenant_trust_remove_source(
    request: Request,
    tenant_id: str,
    source_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
    trust_service: Annotated[TrustPolicyService, Depends(get_trust_service)],
) -> RedirectResponse:
    """Remove a trusted source."""
    logger.debug("Admin page: removing trusted source %s from tenant id=%s", source_id, tenant_id)

    tenant = await _tenant_service.resolve(db, tenant_id)
    if not tenant:
        return RedirectResponse(
            url="/admin/organisations?error=Tenant+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        source_uuid = uuid.UUID(source_id)
    except ValueError:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?error=Invalid+source+ID",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    removed = await trust_service.remove_trusted_source(db, tenant.id, source_uuid)

    if not removed:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?error=Trusted+source+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    await db.commit()

    logger.info("Admin page: removed trusted source %s from tenant id=%s", source_id, tenant_id)

    return RedirectResponse(
        url=f"/admin/organisations/{tenant_id}?success=Trusted+source+removed",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ============================================================
# Role Management
# ============================================================


@router.get("/{tenant_id}/roles/create", response_class=HTMLResponse)
async def tenant_role_create_page(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> HTMLResponse:
    """Role creation form page."""
    logger.debug("Admin page: create role form for tenant id=%s", tenant_id)
    templates = get_templates()

    tenant = await _tenant_service.resolve(db, tenant_id)

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    return templates.TemplateResponse(
        request=request,
        name="admin/tenants/role_form.html",
        context={
            "active_section": "tenants",
            "tenant": tenant_to_dict(tenant),
            "role": None,
            "available_scopes": tenant_role_service.get_tenant_allowed_scopes(tenant),
            "form_action": f"/admin/organisations/{tenant_id}/roles/create",
            "form_title": "Create Role",
        },
    )


@router.post("/{tenant_id}/roles/create", response_class=RedirectResponse)
async def tenant_role_create_submit(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> RedirectResponse:
    """Create a new role."""
    logger.debug("Admin page: creating role for tenant id=%s", tenant_id)

    tenant = await _tenant_service.resolve(db, tenant_id)

    if not tenant:
        return RedirectResponse(
            url="/admin/organisations?error=Tenant+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    form_data = await request.form()
    name = str(form_data.get("name", "")).strip().lower()
    display_name = str(form_data.get("display_name", "")).strip()
    description = str(form_data.get("description", "")).strip() or None
    scopes = [str(s) for s in form_data.getlist("scopes")]

    if not name:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}/roles/create?error=Name+is+required",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if not display_name:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}/roles/create?error=Display+name+is+required",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        await tenant_role_service.create_role(
            db, tenant.id, name, display_name, scopes, description, tenant=tenant
        )
        await db.commit()
        logger.info("Admin page: created role %s for tenant id=%s", name, tenant_id)
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?success=Role+created+successfully",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except ValueError as e:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}/roles/create?error={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


@router.get("/{tenant_id}/roles/{role_id}/edit", response_class=HTMLResponse)
async def tenant_role_edit_page(
    request: Request,
    tenant_id: str,
    role_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> HTMLResponse:
    """Role edit form page."""
    logger.debug("Admin page: edit role form role_id=%s for tenant id=%s", role_id, tenant_id)
    templates = get_templates()

    tenant = await _tenant_service.resolve(db, tenant_id)

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    try:
        role_uuid = uuid.UUID(role_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role ID",
        ) from None

    role = await _tenant_service.get_custom_role_scoped(db, role_uuid, tenant.id)

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )

    return templates.TemplateResponse(
        request=request,
        name="admin/tenants/role_form.html",
        context={
            "active_section": "tenants",
            "tenant": tenant_to_dict(tenant),
            "role": role,
            "available_scopes": tenant_role_service.get_tenant_allowed_scopes(tenant),
            "form_action": f"/admin/organisations/{tenant_id}/roles/{role_id}/edit",
            "form_title": f"Edit Role: {role.display_name}",
        },
    )


@router.post("/{tenant_id}/roles/{role_id}/edit", response_class=RedirectResponse)
async def tenant_role_edit_submit(
    request: Request,
    tenant_id: str,
    role_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> RedirectResponse:
    """Update a role."""
    logger.debug("Admin page: updating role role_id=%s for tenant id=%s", role_id, tenant_id)

    tenant = await _tenant_service.resolve(db, tenant_id)

    if not tenant:
        return RedirectResponse(
            url="/admin/organisations?error=Tenant+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        role_uuid = uuid.UUID(role_id)
    except ValueError:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?error=Invalid+role+ID",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    role = await _tenant_service.get_custom_role_scoped(db, role_uuid, tenant.id)

    if not role:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?error=Role+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    form_data = await request.form()
    display_name = str(form_data.get("display_name", "")).strip()
    description = str(form_data.get("description", "")).strip() or None
    scopes = [str(s) for s in form_data.getlist("scopes")]

    if not display_name:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}/roles/{role_id}/edit?error=Display+name+is+required",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        scopes_to_update = scopes if not role.is_system else None
        await tenant_role_service.update_role(
            db, role, display_name, scopes_to_update, description, tenant=tenant
        )
        await db.commit()
        logger.info("Admin page: updated role %s for tenant id=%s", role.name, tenant_id)
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?success=Role+updated+successfully",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except ValueError as e:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}/roles/{role_id}/edit?error={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


@router.post("/{tenant_id}/roles/{role_id}/delete", response_class=RedirectResponse)
async def tenant_role_delete_submit(
    tenant_id: str,
    role_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_tenants_write)],
) -> RedirectResponse:
    """Delete a role."""
    logger.debug("Admin page: deleting role role_id=%s for tenant id=%s", role_id, tenant_id)

    tenant = await _tenant_service.resolve(db, tenant_id)

    if not tenant:
        return RedirectResponse(
            url="/admin/organisations?error=Tenant+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        role_uuid = uuid.UUID(role_id)
    except ValueError:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?error=Invalid+role+ID",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    role = await _tenant_service.get_custom_role_scoped(db, role_uuid, tenant.id)

    if not role:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?error=Role+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if role.is_system:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?error=Cannot+delete+system+roles",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Check if any members have this role
    member_count = await _tenant_service.count_members_for_role(db, role.id)

    if member_count > 0:
        return RedirectResponse(
            url=f"/admin/organisations/{tenant_id}?error=Cannot+delete+role+with+{member_count}+assigned+members",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    await _tenant_service.delete_custom_role(db, role)
    await db.commit()

    logger.info("Admin page: deleted role %s from tenant id=%s", role.name, tenant_id)
    return RedirectResponse(
        url=f"/admin/organisations/{tenant_id}?success=Role+deleted+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )
