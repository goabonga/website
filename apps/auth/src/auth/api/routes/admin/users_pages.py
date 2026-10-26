# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Admin users management HTML pages."""

import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import (
    get_db,
    get_mfa_service,
    get_oauth2_client_service,
    get_profile_service,
    get_session_service,
    get_templates,
    get_user_admin_permissions,
    require_scope,
)
from auth.db.models.rbac import Role
from auth.db.models.user import (
    User,
    UserProfile,
)
from auth.services.mfa import MFAService
from auth.services.oauth2_client import OAuth2ClientService
from auth.services.profile import ProfileData, ProfileService
from auth.services.session import SessionService
from auth.services.tenant import tenant_service as _tenant_service
from auth.services.upload import UploadError, upload_service
from auth.services.user import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users")

_user_service = UserService()

# Scope dependencies
require_users_read = require_scope("users:read", redirect_to_login=True)
require_users_write = require_scope("users:write", redirect_to_login=True)
require_users_delete = require_scope("users:delete", redirect_to_login=True)
require_users_disable = require_scope("users:disable", redirect_to_login=True)


def user_to_dict(user: User) -> dict:
    """Convert User model to dictionary format.

    Args:
        user: User database model.

    Returns:
        Dictionary with user information.
    """
    primary_email = None
    email_verified = False
    for email in user.emails:
        if email.is_primary:
            primary_email = email.email
            email_verified = email.is_verified
            break

    profile = None
    if user.profile:
        profile = {
            "name": user.profile.name,
            "given_name": user.profile.given_name,
            "family_name": user.profile.family_name,
            "middle_name": user.profile.middle_name,
            "nickname": user.profile.nickname,
            "preferred_username": user.profile.preferred_username,
            "picture_url": user.profile.picture_url,
            "profile_url": user.profile.profile_url,
            "website": user.profile.website,
            "gender": user.profile.gender,
            "birthdate": user.profile.birthdate,
            "zoneinfo": user.profile.zoneinfo,
            "locale": user.profile.locale,
            "phone_number": user.profile.phone_number,
            "address_street": user.profile.address_street,
            "address_locality": user.profile.address_locality,
            "address_region": user.profile.address_region,
            "address_postal_code": user.profile.address_postal_code,
            "address_country": user.profile.address_country,
        }

    return {
        "id": str(user.id),
        "is_active": user.is_active,
        "email": primary_email,
        "email_verified": email_verified,
        "profile": profile,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        "registration_source": user.registration_source,
        "registration_client_id": user.registration_client_id,
        "registration_tenant_id": str(user.registration_tenant_id)
        if user.registration_tenant_id
        else None,
    }


@router.get("", response_class=HTMLResponse)
async def users_list_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_users_read)],
    page: Annotated[int, Query(ge=1)] = 1,
    search: Annotated[str | None, Query(max_length=255)] = None,
    is_active: Annotated[str | None, Query()] = None,
    registration_tenant: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    """Users list page."""
    logger.debug("Admin page: listing users")
    templates = get_templates()

    page_size = 20

    # Resolve filter arguments from the query-string representation.
    is_active_filter: bool | None = None
    if is_active == "true":
        is_active_filter = True
    elif is_active == "false":
        is_active_filter = False

    filter_no_tenant = False
    tenant_uuid_filter: uuid.UUID | None = None
    if registration_tenant == "none":
        filter_no_tenant = True
    elif registration_tenant:
        import contextlib

        with contextlib.suppress(ValueError):
            tenant_uuid_filter = uuid.UUID(registration_tenant)

    users, total = await _user_service.list(
        db,
        page=page,
        page_size=page_size,
        search=search,
        is_active=is_active_filter,
        registration_tenant_id=tenant_uuid_filter,
        filter_no_tenant=filter_no_tenant,
    )

    users_list = [user_to_dict(u) for u in users]
    total_pages = (total + page_size - 1) // page_size

    # Load tenants for the filter dropdown
    tenant_rows = await _tenant_service.list_active_dropdown(db)
    tenants_list = [
        {"id": str(t_id), "name": display_name, "slug": slug}
        for t_id, display_name, slug in tenant_rows
    ]

    success = request.query_params.get("success")
    error = request.query_params.get("error")

    user, roles = auth
    permissions = get_user_admin_permissions(roles)

    return templates.TemplateResponse(
        request=request,
        name="admin/users/list.html",
        context={
            "active_section": "users",
            "users": users_list,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "search": search or "",
            "is_active": is_active,
            "registration_tenant": registration_tenant or "",
            "tenants": tenants_list,
            "success": success,
            "error": error,
            "permissions": permissions,
        },
    )


@router.get("/create", response_class=HTMLResponse)
async def user_create_page(
    request: Request,
    auth: Annotated[tuple[User, list[Role]], Depends(require_users_write)],
) -> HTMLResponse:
    """User creation form page."""
    logger.debug("Admin page: create user form")
    templates = get_templates()

    error = request.query_params.get("error")

    user, roles = auth
    permissions = get_user_admin_permissions(roles)

    return templates.TemplateResponse(
        request=request,
        name="admin/users/create.html",
        context={
            "active_section": "users",
            "error": error,
            "permissions": permissions,
        },
    )


@router.post("/create", response_class=RedirectResponse)
async def user_create_submit(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_users_write)],
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    name: Annotated[str | None, Form()] = None,
    is_verified: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    """Handle user creation form submission."""
    logger.debug("Admin page: creating user email=%s", email)

    if len(password) < 8:
        return RedirectResponse(
            url="/admin/users/create?error=Password+must+be+at+least+8+characters",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if await _user_service.email_exists(db, email):
        return RedirectResponse(
            url="/admin/users/create?error=Email+already+registered",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        user = await _user_service.create_admin_user(
            db,
            email=email,
            password=password,
            name=name,
            is_verified=is_verified == "true",
        )
        await db.commit()

        logger.info("Admin page: created user id=%s email=%s", user.id, email.lower())
        return RedirectResponse(
            url=f"/admin/users/{user.id}?success=User+created+successfully",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        logger.error("Admin page: failed to create user: %s", e)
        return RedirectResponse(
            url=f"/admin/users/create?error={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


@router.get("/{user_id}/edit", response_class=HTMLResponse)
async def user_edit_page(
    request: Request,
    user_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_users_write)],
) -> HTMLResponse:
    """User edit form page."""
    logger.debug("Admin page: edit user form id=%s", user_id)
    templates = get_templates()

    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format",
        )

    user = await _user_service.get_by_id(db, user_uuid)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user_dict = user_to_dict(user)

    error = request.query_params.get("error")
    success = request.query_params.get("success")

    current_user, roles = auth
    permissions = get_user_admin_permissions(roles)

    return templates.TemplateResponse(
        request=request,
        name="admin/users/edit.html",
        context={
            "active_section": "users",
            "user": user_dict,
            "error": error,
            "success": success,
            "permissions": permissions,
        },
    )


@router.post("/{user_id}/edit", response_class=RedirectResponse)
async def user_edit_submit(
    request: Request,
    user_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    profile_service: Annotated[ProfileService, Depends(get_profile_service)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_users_write)],
    name: Annotated[str | None, Form()] = None,
    given_name: Annotated[str | None, Form()] = None,
    family_name: Annotated[str | None, Form()] = None,
    middle_name: Annotated[str | None, Form()] = None,
    nickname: Annotated[str | None, Form()] = None,
    preferred_username: Annotated[str | None, Form()] = None,
    picture_url: Annotated[str | None, Form()] = None,
    profile_url: Annotated[str | None, Form()] = None,
    website: Annotated[str | None, Form()] = None,
    gender: Annotated[str | None, Form()] = None,
    birthdate: Annotated[str | None, Form()] = None,
    zoneinfo: Annotated[str | None, Form()] = None,
    locale: Annotated[str | None, Form()] = None,
    phone_number: Annotated[str | None, Form()] = None,
    address_street: Annotated[str | None, Form()] = None,
    address_locality: Annotated[str | None, Form()] = None,
    address_region: Annotated[str | None, Form()] = None,
    address_postal_code: Annotated[str | None, Form()] = None,
    address_country: Annotated[str | None, Form()] = None,
    is_verified: Annotated[str | None, Form()] = None,
    is_active: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    """Handle user edit form submission."""
    logger.debug("Admin page: updating user id=%s", user_id)

    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        return RedirectResponse(
            url="/admin/users?error=Invalid+user+ID",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    user = await _user_service.get_by_id(db, user_uuid)

    if not user:
        return RedirectResponse(
            url="/admin/users?error=User+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        # Update profile
        if user.profile:
            profile = user.profile
        else:
            # Create profile if it doesn't exist
            profile = UserProfile(user_id=user.id)
            await profile_service.add_profile(db, profile)

        # Update all profile fields
        profile.nickname = nickname.strip() if nickname else None
        profile.preferred_username = preferred_username.strip() if preferred_username else None
        profile.given_name = given_name.strip() if given_name else None
        profile.middle_name = middle_name.strip() if middle_name else None
        profile.family_name = family_name.strip() if family_name else None
        profile.picture_url = picture_url.strip() if picture_url else None
        profile.profile_url = profile_url.strip() if profile_url else None
        profile.website = website.strip() if website else None
        profile.gender = gender.strip() if gender else None
        profile.birthdate = birthdate.strip() if birthdate else None
        profile.zoneinfo = zoneinfo.strip() if zoneinfo else None
        profile.locale = locale.strip() if locale else None
        profile.phone_number = phone_number.strip() if phone_number else None
        profile.address_street = address_street.strip() if address_street else None
        profile.address_locality = address_locality.strip() if address_locality else None
        profile.address_region = address_region.strip() if address_region else None
        profile.address_postal_code = address_postal_code.strip() if address_postal_code else None
        profile.address_country = address_country.strip() if address_country else None

        # Handle full name: use provided value or auto-generate from given/family name
        if name and name.strip():
            profile.name = name.strip()
        else:
            # Auto-generate full name from given/family name
            parts = []
            if profile.given_name:
                parts.append(profile.given_name)
            if profile.family_name:
                parts.append(profile.family_name)
            profile.name = " ".join(parts) if parts else None

        # Update account active status
        new_active = is_active == "true"
        if user.is_active != new_active:
            user.is_active = new_active
            logger.info(
                "Admin page: %s user id=%s",
                "enabled" if new_active else "disabled",
                user_id,
            )

        # Update email verification status
        for email in user.emails:
            if email.is_primary:
                new_verified = is_verified == "true"
                if email.is_verified != new_verified:
                    email.is_verified = new_verified
                    email.verified_at = datetime.now(UTC) if new_verified else None
                break

        await db.commit()

        logger.info("Admin page: updated user id=%s", user_id)
        return RedirectResponse(
            url=f"/admin/users/{user_id}?success=User+updated+successfully",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        logger.error("Admin page: failed to update user: %s", e)
        return RedirectResponse(
            url=f"/admin/users/{user_id}/edit?error={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


@router.post("/{user_id}/avatar", response_class=RedirectResponse)
async def user_avatar_upload(
    user_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    profile_service: Annotated[ProfileService, Depends(get_profile_service)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_users_write)],
    avatar: UploadFile,
) -> RedirectResponse:
    """Handle user avatar upload from admin panel."""
    logger.debug("Admin page: uploading avatar for user id=%s", user_id)

    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        return RedirectResponse(
            url="/admin/users?error=Invalid+user+ID",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    user = await _user_service.get_by_id(db, user_uuid)

    if not user:
        return RedirectResponse(
            url="/admin/users?error=User+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        # Save the avatar file
        relative_path = await upload_service.save_avatar(avatar, user.id)
        avatar_url = upload_service.get_avatar_url(relative_path)

        # Update profile with new avatar URL
        profile_data = ProfileData(picture_url=avatar_url)
        await profile_service.update_profile(db, str(user.id), profile_data)
        await db.commit()

        logger.info("Admin page: avatar uploaded for user_id=%s: %s", user.id, avatar_url)
        return RedirectResponse(
            url=f"/admin/users/{user_id}/edit?success=Avatar+uploaded+successfully",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except UploadError as e:
        logger.warning("Admin page: avatar upload failed for user_id=%s: %s", user_id, str(e))
        return RedirectResponse(
            url=f"/admin/users/{user_id}/edit?error={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        logger.error("Admin page: failed to upload avatar: %s", e)
        return RedirectResponse(
            url=f"/admin/users/{user_id}/edit?error=Failed+to+upload+avatar",
            status_code=status.HTTP_303_SEE_OTHER,
        )


@router.get("/{user_id}", response_class=HTMLResponse)
async def user_detail_page(
    request: Request,
    user_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_users_read)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    mfa_service: Annotated[MFAService, Depends(get_mfa_service)],
    oauth2_client_service: Annotated[OAuth2ClientService, Depends(get_oauth2_client_service)],
) -> HTMLResponse:
    """User detail page."""
    logger.debug("Admin page: viewing user id=%s", user_id)
    templates = get_templates()

    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format",
        )

    user = await _user_service.get_by_id(db, user_uuid)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user_dict = user_to_dict(user)

    # Get all emails
    emails = []
    for email in user.emails:
        emails.append(
            {
                "email": email.email,
                "is_verified": email.is_verified,
                "is_primary": email.is_primary,
                "verified_at": email.verified_at.isoformat() if email.verified_at else None,
            }
        )
    user_dict["emails"] = emails

    # Add MFA status
    mfa = await mfa_service.get_user_mfa(db, str(user_uuid))
    if mfa:
        backup_count = sum(1 for code in mfa.backup_codes if code.used_at is None)
        user_dict["mfa"] = {
            "totp_enabled": mfa.totp_enabled,
            "totp_enabled_at": mfa.totp_enabled_at.isoformat() if mfa.totp_enabled_at else None,
            "backup_codes_remaining": backup_count,
        }
    else:
        user_dict["mfa"] = {"totp_enabled": False}

    # Add session count
    user_dict["active_sessions"] = await session_service.count_active(db, user_id=user_uuid)

    # Add tenant memberships (where the user uses this account)
    memberships = await _tenant_service.list_user_memberships(db, user_uuid)
    user_dict["tenant_memberships"] = [
        {
            "tenant_id": str(member.tenant_id),
            "tenant_name": member.tenant.display_name if member.tenant else None,
            "tenant_slug": member.tenant.slug if member.tenant else None,
            "tenant_active": bool(member.tenant and member.tenant.is_active),
            "role": member.role_display_name,
            "joined_at": member.joined_at.isoformat() if member.joined_at else None,
        }
        for member in memberships
    ]

    # Look up registration client name if applicable
    if user.registration_client_id:
        client = await oauth2_client_service.get_client_by_client_id(
            db, user.registration_client_id
        )
        user_dict["registration_client_name"] = client.name if client else None
    else:
        user_dict["registration_client_name"] = None

    # Look up registration tenant name if applicable
    if user.registration_tenant_id:
        tenant_uuid = (
            user.registration_tenant_id
            if isinstance(user.registration_tenant_id, uuid.UUID)
            else uuid.UUID(str(user.registration_tenant_id))
        )
        user_dict["registration_tenant_name"] = await _tenant_service.get_display_name(
            db, tenant_uuid
        )
    else:
        user_dict["registration_tenant_name"] = None

    success = request.query_params.get("success")
    error = request.query_params.get("error")

    current_user, roles = auth
    permissions = get_user_admin_permissions(roles)

    return templates.TemplateResponse(
        request=request,
        name="admin/users/detail.html",
        context={
            "active_section": "users",
            "user": user_dict,
            "success": success,
            "error": error,
            "permissions": permissions,
        },
    )


@router.post("/{user_id}/disable", response_class=RedirectResponse)
async def user_disable_submit(
    user_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_users_disable)],
) -> RedirectResponse:
    """Handle user disable."""
    logger.debug("Admin page: disabling user id=%s", user_id)

    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        return RedirectResponse(
            url="/admin/users?error=Invalid+user+ID",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    user = await _user_service.get_by_id(db, user_uuid)

    if not user:
        return RedirectResponse(
            url="/admin/users?error=User+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if not user.is_active:
        return RedirectResponse(
            url=f"/admin/users/{user_id}?error=User+already+disabled",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    user.is_active = False
    await db.commit()

    logger.info("Admin page: disabled user id=%s", user_id)
    return RedirectResponse(
        url=f"/admin/users/{user_id}?success=User+disabled+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{user_id}/enable", response_class=RedirectResponse)
async def user_enable_submit(
    user_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_users_disable)],
) -> RedirectResponse:
    """Handle user enable."""
    logger.debug("Admin page: enabling user id=%s", user_id)

    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        return RedirectResponse(
            url="/admin/users?error=Invalid+user+ID",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    user = await _user_service.get_by_id(db, user_uuid)

    if not user:
        return RedirectResponse(
            url="/admin/users?error=User+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if user.is_active:
        return RedirectResponse(
            url=f"/admin/users/{user_id}?error=User+already+enabled",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    user.is_active = True
    await db.commit()

    logger.info("Admin page: enabled user id=%s", user_id)
    return RedirectResponse(
        url=f"/admin/users/{user_id}?success=User+enabled+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{user_id}/revoke-sessions", response_class=RedirectResponse)
async def user_revoke_sessions_submit(
    user_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_users_write)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Handle user sessions revocation."""
    logger.debug("Admin page: revoking sessions for user id=%s", user_id)

    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        return RedirectResponse(
            url="/admin/users?error=Invalid+user+ID",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    user = await _user_service.get_by_id(db, user_uuid)

    if not user:
        return RedirectResponse(
            url="/admin/users?error=User+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    revoked_count = await session_service.revoke_all_active_sessions(db, user_id=user_uuid)
    await db.commit()

    logger.info("Admin page: revoked %d sessions for user id=%s", revoked_count, user_id)
    return RedirectResponse(
        url=f"/admin/users/{user_id}?success=Revoked+{revoked_count}+session(s)",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{user_id}/delete", response_class=RedirectResponse)
async def user_delete_submit(
    user_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_users_delete)],
) -> RedirectResponse:
    """Handle user deletion."""
    logger.debug("Admin page: deleting user id=%s", user_id)

    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        return RedirectResponse(
            url="/admin/users?error=Invalid+user+ID",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    user = await _user_service.get_by_id(db, user_uuid)

    if not user:
        return RedirectResponse(
            url="/admin/users?error=User+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    await _user_service.delete(db, user)
    await db.commit()

    logger.info("Admin page: deleted user id=%s", user_id)
    return RedirectResponse(
        url="/admin/users?success=User+deleted+successfully",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/bulk-delete", response_class=RedirectResponse)
async def users_bulk_delete(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple[User, list[Role]], Depends(require_users_delete)],
) -> RedirectResponse:
    """Handle bulk user deletion."""
    form = await request.form()
    user_ids = form.getlist("user_ids")

    if not user_ids:
        return RedirectResponse(
            url="/admin/users?error=No+users+selected",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    admin_user = auth[0]
    deleted = 0

    for uid in user_ids:
        try:
            user_uuid = uuid.UUID(str(uid))
        except ValueError:
            continue

        if user_uuid == admin_user.id:
            continue

        user = await _user_service.get_by_id(db, user_uuid)
        if user:
            await _user_service.delete(db, user)
            deleted += 1

    await db.commit()

    logger.info("Admin page: bulk deleted %d users", deleted)
    return RedirectResponse(
        url=f"/admin/users?success=Deleted+{deleted}+user(s)",
        status_code=status.HTTP_303_SEE_OTHER,
    )
