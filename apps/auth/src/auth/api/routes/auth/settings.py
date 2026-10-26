# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""User account settings endpoints."""

import logging
import re
import secrets
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from auth.api.deps import (
    get_branding_service,
    get_db,
    get_email_service,
    get_encryption,
    get_jwks_service,
    get_mfa_service,
    get_password_service,
    get_profile_service,
    get_session_service,
    get_templates,
    get_trust_service,
    get_user_admin_permissions,
    require_scope,
)
from auth.api.schemas.settings import (
    PasswordChangeRequest,
    ProfileUpdateRequest,
)
from auth.config import settings
from auth.core.security import hash_password
from auth.db.models.oauth2 import OAuth2Client
from auth.db.models.tenant import (
    TENANT_SCOPES,
    CustomDomainStatus,
    IdentityProvider,
    IdentityProviderType,
    Tenant,
    TenantBranding,
    TenantCustomRole,
    TenantMember,
    TenantTemplate,
    TenantTrustedSource,
    TenantTrustMode,
    TenantWebhook,
    WebhookDelivery,
    WebhookDeliveryStatus,
    WebhookEvent,
    build_scope_groups_from_db,
)
from auth.db.models.user import User, UserEmail, UserProfile
from auth.middlewares.tenant import get_session_cookie_name, get_tenant_context
from auth.services.branding import BrandingConfig, BrandingService
from auth.services.email import EmailService
from auth.services.federation import federation_service
from auth.services.jwks import JWKSService
from auth.services.mfa import MFAService
from auth.services.oauth2_client import OAuth2ClientService
from auth.services.password import PasswordService
from auth.services.profile import ProfileData, ProfileService
from auth.services.role import role_service
from auth.services.scope import scope_service
from auth.services.session import SessionService
from auth.services.tenant import tenant_service
from auth.services.tenant_role import tenant_role_service
from auth.services.token import TokenService
from auth.services.trust import TrustPolicyService
from auth.services.upload import UploadError, upload_service
from auth.services.user import UserService
from auth.services.webhook import (
    WebhookURLError,
    webhook_service,
)
from auth.services.webhook import (
    generate_secret as webhook_generate_secret,
)
from auth.services.webhook import (
    safe_dispatch as webhook_safe_dispatch,
)
from auth.services.webhook import (
    validate_target_url as webhook_validate_target_url,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings")

_user_service = UserService()
_oauth2_client_service = OAuth2ClientService()


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


# Default: all profile fields visible
DEFAULT_PROFILE_FIELDS = {
    "avatar": True,
    "identity": True,
    "nickname": True,
    "preferred_username": True,
    "given_name": True,
    "middle_name": True,
    "family_name": True,
    "personal_info": True,
    "gender": True,
    "birthdate": True,
    "locale": True,
    "zoneinfo": True,
    "contact": True,
    "phone_number": True,
    "website": True,
    "profile_url": True,
    "picture_url": True,
    "address": True,
    "roles_permissions": True,
}

_PROFILE_FIELD_KEYS = list(DEFAULT_PROFILE_FIELDS.keys())


async def get_profile_fields(db, tenant_id) -> dict[str, bool]:
    """Load profile field visibility config from tenant settings."""
    if not tenant_id:
        return dict(DEFAULT_PROFILE_FIELDS)

    import uuid as uuid_mod

    tid = tenant_id if isinstance(tenant_id, uuid_mod.UUID) else uuid_mod.UUID(str(tenant_id))
    tenant_settings = await tenant_service.get_settings(db, tid)

    if not tenant_settings or not isinstance(tenant_settings, dict):
        return dict(DEFAULT_PROFILE_FIELDS)

    overrides = tenant_settings.get("profile_fields", {})
    fields = dict(DEFAULT_PROFILE_FIELDS)
    for key in fields:
        if key in overrides:
            fields[key] = bool(overrides[key])
    return fields


def settings_redirect(path: str, **query_params) -> RedirectResponse:
    """Create a redirect to a settings page with tenant prefix.

    Args:
        path: The settings path (e.g., "/emails", "/organisations").
        **query_params: Query parameters to add to the URL.

    Returns:
        RedirectResponse with proper tenant prefix.
    """
    tenant_prefix = get_tenant_prefix()
    url = f"{tenant_prefix}/auth/settings{path}"
    if query_params:
        from urllib.parse import urlencode

        url += "?" + urlencode(query_params)
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


async def get_branding_for_request(db: AsyncSession) -> BrandingConfig:
    """Get branding configuration for the current request's tenant."""
    tenant_ctx = get_tenant_context()
    if tenant_ctx and tenant_ctx.tenant_id:
        tenant_id: uuid.UUID | None = None
        if isinstance(tenant_ctx.tenant_id, uuid.UUID):
            tenant_id = tenant_ctx.tenant_id
        else:
            try:
                tenant_id = uuid.UUID(str(tenant_ctx.tenant_id))
            except (ValueError, TypeError, AttributeError):
                tenant_id = None
        branding_service = BrandingService(
            templates_path=Path(settings.templates_path),
            db_session_factory=None,
        )
        return await branding_service.get_branding(db, tenant_id)
    return BrandingConfig()


async def get_current_user(
    request: Request,
    db: AsyncSession,
    session_service: SessionService,
) -> User:
    """Get the current authenticated user.

    Args:
        request: The HTTP request.
        db: Database session.
        session_service: Session service.

    Returns:
        The authenticated user.

    Raises:
        HTTPException: If user is not authenticated.
    """
    session_token = request.cookies.get(get_session_cookie_name())

    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    user = await session_service.get_user_by_session_token(db, session_token)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        )

    return user


def _build_current_url(request: Request) -> str:
    """Build the current request URL with proxy headers and tenant prefix restored."""
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc))
    tenant_prefix = get_tenant_prefix()
    path = f"{tenant_prefix}{request.url.path}"
    if request.url.query:
        return f"{scheme}://{host}{path}?{request.url.query}"
    return f"{scheme}://{host}{path}"


def require_auth_redirect(request: Request) -> RedirectResponse:
    """Create a redirect to login page.

    Args:
        request: The HTTP request.

    Returns:
        Redirect response to login page.
    """
    tenant_prefix = get_tenant_prefix()
    next_url = _build_current_url(request)
    return RedirectResponse(
        url=f"{tenant_prefix}/auth/login?next={next_url}",
        status_code=status.HTTP_302_FOUND,
    )


async def check_user_is_admin(db: AsyncSession, user: User) -> tuple[bool, dict[str, bool]]:
    """Check if user has admin privileges and get their admin permissions.

    Args:
        db: Database session.
        user: User to check.

    Returns:
        Tuple of (is_admin, permissions_dict) where is_admin is True if user has
        any admin scope, and permissions_dict contains granular admin permissions.
    """
    # Get user's roles with their scopes
    roles = await role_service.list_user_roles_with_scopes(db, user.id)

    # Get granular admin permissions
    permissions = get_user_admin_permissions(roles)

    # User is admin if they have any admin permission
    is_admin = any(permissions.values())

    return is_admin, permissions


@router.get("", response_class=HTMLResponse)
async def settings_index(
    request: Request,
) -> RedirectResponse:
    """Redirect the settings root to the profile page.

    Acts as the canonical entry point for the settings area; consumers navigating
    to `/auth/settings` are transparently forwarded to `/auth/settings/profile`.
    No authentication check is performed here — unauthenticated users are
    redirected to login by the profile page itself.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -b cookies.txt https://auth.example.com/auth/settings
    ```
    """
    tenant_prefix = get_tenant_prefix()
    logger.debug("Settings index requested, redirecting to profile")
    return RedirectResponse(
        url=f"{tenant_prefix}/auth/settings/profile",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/profile", response_class=HTMLResponse)
async def settings_profile(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    branding_service: Annotated[BrandingService, Depends(get_branding_service)],
) -> Response:
    """Render the user profile settings page.

    Displays the authenticated user's OIDC profile fields (name, avatar, locale,
    address, etc.) along with their assigned roles and scopes. The set of visible
    fields is filtered by the tenant's `profile_fields` configuration. Unauthenticated
    requests are redirected to login with a `next` parameter.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -b cookies.txt https://auth.example.com/auth/settings/profile
    ```
    """
    logger.debug("Profile settings page requested")

    session_token = request.cookies.get(get_session_cookie_name())
    if not session_token:
        return require_auth_redirect(request)

    user = await session_service.get_user_by_session_token(db, session_token)
    if not user:
        return require_auth_redirect(request)

    # Load user profile
    await db.refresh(user, ["profile", "emails"])

    profile = user.profile
    primary_email = next(
        (e.email for e in user.emails if e.is_primary),
        user.emails[0].email if user.emails else None,
    )

    # Get user's roles with their scopes
    user_roles = await role_service.list_user_roles_with_scopes(db, user.id)

    # Build roles info for display
    roles_info = []
    all_scopes = set()
    for role in user_roles:
        scope_names = role.get_all_scope_names()
        roles_info.append(
            {
                "name": role.name,
                "description": role.description,
                "scopes": scope_names,
                "is_system": role.is_system,
            }
        )
        all_scopes.update(scope_names)

    # Check if user is admin
    is_admin, admin_permissions = await check_user_is_admin(db, user)

    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()

    pf = await get_profile_fields(db, tenant_id)

    logger.debug("Rendering profile settings for user_id=%s", user.id)
    html = await branding_service.render_template(
        db,
        "auth/settings/profile.html",
        {
            "request": request,
            "active_section": "profile",
            "user": user,
            "profile": profile,
            "email": primary_email,
            "error": None,
            "success": None,
            "is_admin": is_admin,
            "admin_permissions": admin_permissions,
            "user_roles": roles_info,
            "user_scopes": sorted(all_scopes),
            "tenant_prefix": tenant_prefix,
            "pf": pf,
        },
        tenant_id=tenant_id,
    )
    return HTMLResponse(content=html)


@router.post("/profile", response_class=HTMLResponse)
async def settings_profile_update(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    profile_service: Annotated[ProfileService, Depends(get_profile_service)],
    branding_service: Annotated[BrandingService, Depends(get_branding_service)],
    nickname: Annotated[str | None, Form()] = None,
    given_name: Annotated[str | None, Form()] = None,
    family_name: Annotated[str | None, Form()] = None,
    middle_name: Annotated[str | None, Form()] = None,
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
) -> Response:
    """Process the profile update form submission.

    Accepts all OIDC standard profile fields (given_name, family_name, locale,
    birthdate, address components, etc.) via an HTML form POST and persists
    them through `ProfileService`. Re-renders the profile page with a success
    or error banner on completion. JSON API equivalent: `PUT /api/v1/me/profile`.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      -d "given_name=Alice&family_name=Smith&locale=en-GB" \
      https://auth.example.com/auth/settings/profile
    ```
    """
    logger.debug("Profile update form submitted")

    session_token = request.cookies.get(get_session_cookie_name())
    if not session_token:
        return require_auth_redirect(request)

    user = await session_service.get_user_by_session_token(db, session_token)
    if not user:
        return require_auth_redirect(request)

    # Load user emails for display
    await db.refresh(user, ["emails"])
    primary_email = next(
        (e.email for e in user.emails if e.is_primary),
        user.emails[0].email if user.emails else None,
    )

    # Update profile
    profile_data = ProfileData(
        nickname=nickname,
        given_name=given_name,
        family_name=family_name,
        middle_name=middle_name,
        preferred_username=preferred_username,
        picture_url=picture_url,
        profile_url=profile_url,
        website=website,
        gender=gender,
        birthdate=birthdate,
        zoneinfo=zoneinfo,
        locale=locale,
        phone_number=phone_number,
        address_street=address_street,
        address_locality=address_locality,
        address_region=address_region,
        address_postal_code=address_postal_code,
        address_country=address_country,
    )

    profile = await profile_service.update_profile(db, str(user.id), profile_data)
    await db.commit()
    logger.info("Profile updated for user_id=%s", user.id)

    # Get user's roles with their scopes
    user_roles = await role_service.list_user_roles_with_scopes(db, user.id)

    # Build roles info for display
    roles_info = []
    all_scopes = set()
    for role in user_roles:
        scope_names = role.get_all_scope_names()
        roles_info.append(
            {
                "name": role.name,
                "description": role.description,
                "scopes": scope_names,
                "is_system": role.is_system,
            }
        )
        all_scopes.update(scope_names)

    # Check if user is admin
    is_admin, admin_permissions = await check_user_is_admin(db, user)

    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()
    pf = await get_profile_fields(db, tenant_id)

    html = await branding_service.render_template(
        db,
        "auth/settings/profile.html",
        {
            "request": request,
            "active_section": "profile",
            "user": user,
            "profile": profile,
            "email": primary_email,
            "error": None,
            "success": "Profile updated successfully.",
            "is_admin": is_admin,
            "admin_permissions": admin_permissions,
            "user_roles": roles_info,
            "user_scopes": sorted(all_scopes),
            "tenant_prefix": tenant_prefix,
            "pf": pf,
        },
        tenant_id=tenant_id,
    )
    return HTMLResponse(content=html)


@router.post("/profile/avatar", response_class=HTMLResponse)
async def settings_upload_avatar(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    profile_service: Annotated[ProfileService, Depends(get_profile_service)],
    avatar: UploadFile,
) -> Response:
    """Process a profile avatar upload via multipart form.

    Saves the uploaded image to the configured storage backend, updates the
    user's `picture_url` profile field, and re-renders the profile page with
    success or error feedback. Use `POST /auth/settings/profile/avatar/api` for
    the JSON variant.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      -F "avatar=@/path/to/photo.jpg" \
      https://auth.example.com/auth/settings/profile/avatar
    ```
    """
    logger.debug("Avatar upload form submitted")
    templates = get_templates()

    session_token = request.cookies.get(get_session_cookie_name())
    if not session_token:
        return require_auth_redirect(request)

    user = await session_service.get_user_by_session_token(db, session_token)
    if not user:
        return require_auth_redirect(request)

    # Load user emails and profile for display
    await db.refresh(user, ["emails", "profile"])
    primary_email = next(
        (e.email for e in user.emails if e.is_primary),
        user.emails[0].email if user.emails else None,
    )

    # Check if user is admin
    is_admin, admin_permissions = await check_user_is_admin(db, user)

    # Get branding for tenant
    branding = await get_branding_for_request(db)
    tenant_prefix = get_tenant_prefix()

    error = None
    success = None
    profile: UserProfile | None = user.profile

    try:
        # Save the avatar file
        relative_path = await upload_service.save_avatar(avatar, user.id)
        avatar_url = upload_service.get_avatar_url(relative_path)

        # Update profile with new avatar URL
        profile_data = ProfileData(picture_url=avatar_url)
        profile = await profile_service.update_profile(db, str(user.id), profile_data)

        logger.info("Avatar uploaded for user_id=%s: %s", user.id, avatar_url)
        success = "Profile picture updated successfully."

    except UploadError as e:
        logger.warning("Avatar upload failed for user_id=%s: %s", user.id, str(e))
        error = str(e)

    return templates.TemplateResponse(
        request=request,
        name="auth/settings/profile.html",
        context={
            "active_section": "profile",
            "user": user,
            "profile": profile,
            "email": primary_email,
            "error": error,
            "success": success,
            "is_admin": is_admin,
            "admin_permissions": admin_permissions,
            "branding": branding,
            "tenant_prefix": tenant_prefix,
        },
    )


@router.post("/profile/avatar/api", response_class=JSONResponse)
async def upload_avatar_api(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    profile_service: Annotated[ProfileService, Depends(get_profile_service)],
    avatar: UploadFile,
) -> JSONResponse:
    """Upload a profile avatar and return the new URL as JSON.

    Accepts a multipart file upload and stores the image via the upload service.
    Returns `{"picture_url": "<url>"}` on success or a 400 JSON error if the
    file is invalid. Intended for SPA/AJAX callers; browser-form callers should
    use `POST /auth/settings/profile/avatar` instead.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      -F "avatar=@/path/to/photo.jpg" \
      https://auth.example.com/auth/settings/profile/avatar/api
    ```
    """
    logger.debug("Avatar API POST requested")

    try:
        user = await get_current_user(request, db, session_service)
    except HTTPException:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "Not authenticated"},
        )

    try:
        # Save the avatar file
        relative_path = await upload_service.save_avatar(avatar, user.id)
        avatar_url = upload_service.get_avatar_url(relative_path)

        # Update profile with new avatar URL
        profile_data = ProfileData(picture_url=avatar_url)
        await profile_service.update_profile(db, str(user.id), profile_data)

        logger.info("Avatar uploaded via API for user_id=%s: %s", user.id, avatar_url)
        return JSONResponse(content={"picture_url": avatar_url})

    except UploadError as e:
        logger.warning("Avatar upload via API failed for user_id=%s: %s", user.id, str(e))
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": str(e)},
        )


@router.get("/profile/api", response_class=JSONResponse)
async def get_profile_api(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    profile_service: Annotated[ProfileService, Depends(get_profile_service)],
) -> JSONResponse:
    """Return the current user's profile as a JSON object.

    Reads all standard OIDC profile fields stored for the authenticated user
    and returns them as a flat JSON dictionary. Unauthenticated requests receive
    a 401 JSON error instead of an HTML redirect. JSON API equivalent:
    `GET /api/v1/me/profile`.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -b cookies.txt \
      https://auth.example.com/auth/settings/profile/api
    ```
    """
    logger.debug("Profile API GET requested")

    try:
        user = await get_current_user(request, db, session_service)
    except HTTPException:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "Not authenticated"},
        )

    profile = await profile_service.get_profile(db, str(user.id))
    profile_dict = profile_service.profile_to_dict(profile)

    logger.debug("Returning profile API for user_id=%s", user.id)
    return JSONResponse(content=profile_dict)


@router.put("/profile/api", response_class=JSONResponse)
async def update_profile_api(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    profile_service: Annotated[ProfileService, Depends(get_profile_service)],
    data: ProfileUpdateRequest,
) -> JSONResponse:
    """Update the current user's profile via JSON body.

    Accepts a JSON request body with any subset of standard OIDC profile fields
    and persists them via `ProfileService`. Returns the full updated profile on
    success. Unauthenticated requests receive a 401 JSON error. JSON API
    equivalent: `PUT /api/v1/me/profile`.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -X PUT -b cookies.txt \
      -H "Content-Type: application/json" \
      -d '{"given_name": "Alice", "locale": "en-GB"}' \
      https://auth.example.com/auth/settings/profile/api
    ```
    """
    logger.debug("Profile API PUT requested")

    try:
        user = await get_current_user(request, db, session_service)
    except HTTPException:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "Not authenticated"},
        )

    profile_data = ProfileData(
        nickname=data.nickname,
        given_name=data.given_name,
        family_name=data.family_name,
        middle_name=data.middle_name,
        preferred_username=data.preferred_username,
        picture_url=data.picture_url,
        profile_url=data.profile_url,
        website=data.website,
        gender=data.gender,
        birthdate=data.birthdate,
        zoneinfo=data.zoneinfo,
        locale=data.locale,
        phone_number=data.phone_number,
        address_street=data.address_street,
        address_locality=data.address_locality,
        address_region=data.address_region,
        address_postal_code=data.address_postal_code,
        address_country=data.address_country,
    )

    profile = await profile_service.update_profile(db, str(user.id), profile_data)
    profile_dict = profile_service.profile_to_dict(profile)

    logger.info("Profile updated via API for user_id=%s", user.id)
    return JSONResponse(content=profile_dict)


@router.get("/password", response_class=HTMLResponse)
async def settings_password(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    branding_service: Annotated[BrandingService, Depends(get_branding_service)],
) -> Response:
    """Render the password change settings page.

    Displays a form with fields for current password, new password, and
    confirmation. Unauthenticated requests are redirected to login.
    Implements the self-service password change flow described in
    NIST SP 800-63B §5.1.1.

    **Specification:** NIST SP 800-63B §5.1.1; RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -b cookies.txt https://auth.example.com/auth/settings/password
    ```
    """
    logger.debug("Password settings page requested")

    session_token = request.cookies.get(get_session_cookie_name())
    if not session_token:
        return require_auth_redirect(request)

    user = await session_service.get_user_by_session_token(db, session_token)
    if not user:
        return require_auth_redirect(request)

    # Check if user is admin
    is_admin, admin_permissions = await check_user_is_admin(db, user)

    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()

    logger.debug("Rendering password settings for user_id=%s", user.id)
    html = await branding_service.render_template(
        db,
        "auth/settings/password.html",
        {
            "request": request,
            "active_section": "password",
            "error": None,
            "success": None,
            "is_admin": is_admin,
            "admin_permissions": admin_permissions,
            "tenant_prefix": tenant_prefix,
        },
        tenant_id=tenant_id,
    )
    return HTMLResponse(content=html)


@router.post("/password", response_class=HTMLResponse)
async def settings_password_update(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    password_service: Annotated[PasswordService, Depends(get_password_service)],
    branding_service: Annotated[BrandingService, Depends(get_branding_service)],
    current_password: Annotated[str, Form()],
    new_password: Annotated[str, Form()],
    confirm_password: Annotated[str, Form()],
) -> Response:
    """Process the password change form submission.

    Validates the current password before accepting the new one (minimum 8
    characters). On success, dispatches a `user.password_changed` webhook event
    and re-renders the page with a success message. Implements the verified
    password change requirement from NIST SP 800-63B §5.1.1.

    **Specification:** NIST SP 800-63B §5.1.1; RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      -d "current_password=OldPass1&new_password=NewPass1&confirm_password=NewPass1" \
      https://auth.example.com/auth/settings/password
    ```
    """
    logger.debug("Password update form submitted")

    session_token = request.cookies.get(get_session_cookie_name())
    if not session_token:
        return require_auth_redirect(request)

    user = await session_service.get_user_by_session_token(db, session_token)
    if not user:
        return require_auth_redirect(request)

    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()

    async def _render_password(error_msg=None, success_msg=None):
        html = await branding_service.render_template(
            db,
            "auth/settings/password.html",
            {
                "request": request,
                "active_section": "password",
                "error": error_msg,
                "success": success_msg,
                "tenant_prefix": tenant_prefix,
            },
            tenant_id=tenant_id,
        )
        return HTMLResponse(content=html)

    # Validate password confirmation
    if new_password != confirm_password:
        return await _render_password(error_msg="New passwords do not match.")

    # Validate password length
    if len(new_password) < 8:
        return await _render_password(error_msg="Password must be at least 8 characters.")

    # Change password
    success, error = await password_service.change_password(
        db, str(user.id), current_password, new_password
    )

    if not success:
        return await _render_password(error_msg=error or "Failed to change password.")

    logger.info("Password changed for user_id=%s", user.id)

    await webhook_safe_dispatch(
        db,
        tenant_id=tenant_id,
        event=WebhookEvent.USER_PASSWORD_CHANGED,
        data={
            "user_id": str(user.id),
            "tenant_id": str(tenant_id) if tenant_id else None,
        },
    )
    await db.commit()

    return await _render_password(success_msg="Password changed successfully.")


@router.put("/password/api", response_class=JSONResponse)
async def update_password_api(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    password_service: Annotated[PasswordService, Depends(get_password_service)],
    data: PasswordChangeRequest,
) -> JSONResponse:
    """Change the current user's password via JSON body.

    Requires `current_password` and `new_password` (minimum 8 characters).
    Dispatches a `user.password_changed` webhook event on success. Intended for
    SPA/AJAX callers; HTML form callers should POST to `/auth/settings/password`.
    Implements NIST SP 800-63B §5.1.1 verified password change.

    **Specification:** NIST SP 800-63B §5.1.1; RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -X PUT -b cookies.txt \
      -H "Content-Type: application/json" \
      -d '{"current_password": "OldPass1", "new_password": "NewPass1"}' \
      https://auth.example.com/auth/settings/password/api
    ```
    """
    logger.debug("Password API PUT requested")

    try:
        user = await get_current_user(request, db, session_service)
    except HTTPException:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "Not authenticated"},
        )

    # Validate password length
    if len(data.new_password) < 8:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Password must be at least 8 characters."},
        )

    # Change password
    success, error = await password_service.change_password(
        db, str(user.id), data.current_password, data.new_password
    )

    if not success:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": error or "Failed to change password."},
        )

    logger.info("Password changed via API for user_id=%s", user.id)

    tenant_id = get_current_tenant_id()
    await webhook_safe_dispatch(
        db,
        tenant_id=tenant_id,
        event=WebhookEvent.USER_PASSWORD_CHANGED,
        data={
            "user_id": str(user.id),
            "tenant_id": str(tenant_id) if tenant_id else None,
        },
    )
    await db.commit()

    return JSONResponse(content={"message": "Password changed successfully."})


@router.get("/security", response_class=HTMLResponse)
async def settings_security(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    mfa_service: Annotated[MFAService, Depends(get_mfa_service)],
    branding_service: Annotated[BrandingService, Depends(get_branding_service)],
) -> Response:
    """Render the security settings page showing MFA status.

    Displays whether TOTP is enabled (RFC 6238) and shows the number of remaining
    backup codes when TOTP is active. Provides entry points to enrol or disable
    TOTP. Unauthenticated requests are redirected to login.

    **Specification:** RFC 6238 (TOTP); RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -b cookies.txt https://auth.example.com/auth/settings/security
    ```
    """
    logger.debug("Security settings page requested")

    session_token = request.cookies.get(get_session_cookie_name())
    if not session_token:
        return require_auth_redirect(request)

    user = await session_service.get_user_by_session_token(db, session_token)
    if not user:
        return require_auth_redirect(request)

    # Get MFA status
    user_mfa = await mfa_service.get_user_mfa(db, str(user.id))
    totp_enabled = user_mfa.totp_enabled if user_mfa else False

    backup_codes_remaining = None
    backup_codes_total = None
    if totp_enabled:
        status_result = await mfa_service.get_backup_codes_status(db, str(user.id))
        if status_result:
            backup_codes_remaining, backup_codes_total = status_result

    # Check if user is admin
    is_admin, admin_permissions = await check_user_is_admin(db, user)

    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()

    logger.debug("Rendering security settings for user_id=%s", user.id)
    html = await branding_service.render_template(
        db,
        "auth/settings/security.html",
        {
            "request": request,
            "active_section": "security",
            "totp_enabled": totp_enabled,
            "backup_codes_remaining": backup_codes_remaining,
            "backup_codes_total": backup_codes_total,
            "is_admin": is_admin,
            "admin_permissions": admin_permissions,
            "tenant_prefix": tenant_prefix,
        },
        tenant_id=tenant_id,
    )
    return HTMLResponse(content=html)


@router.get("/sessions", response_class=HTMLResponse)
async def settings_sessions(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    branding_service: Annotated[BrandingService, Depends(get_branding_service)],
) -> Response:
    """Render the active sessions management page.

    Lists all live sessions for the authenticated user, highlighting the current
    one so the user can identify and revoke suspicious sessions from other
    devices or locations. Session tokens are managed per RFC 6265.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -b cookies.txt https://auth.example.com/auth/settings/sessions
    ```
    """
    logger.debug("Sessions settings page requested")

    session_token = request.cookies.get(get_session_cookie_name())
    if not session_token:
        return require_auth_redirect(request)

    user = await session_service.get_user_by_session_token(db, session_token)
    if not user:
        return require_auth_redirect(request)

    # Get current session for comparison
    current_session = await session_service.get_session(db, session_token)

    # Get all user sessions
    sessions = await session_service.get_user_sessions(db, str(user.id))

    # Check if user is admin
    is_admin, admin_permissions = await check_user_is_admin(db, user)

    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()

    logger.debug("Rendering sessions settings for user_id=%s", user.id)
    html = await branding_service.render_template(
        db,
        "auth/settings/sessions.html",
        {
            "request": request,
            "active_section": "sessions",
            "sessions": sessions,
            "current_session_id": str(current_session.id) if current_session else None,
            "error": None,
            "success": None,
            "is_admin": is_admin,
            "admin_permissions": admin_permissions,
            "tenant_prefix": tenant_prefix,
        },
        tenant_id=tenant_id,
    )
    return HTMLResponse(content=html)


@router.post("/sessions/{session_id}/revoke", response_class=HTMLResponse)
async def settings_revoke_session(
    request: Request,
    session_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    branding_service: Annotated[BrandingService, Depends(get_branding_service)],
) -> Response:
    """Revoke a specific session by ID.

    Terminates the session identified by `session_id`, preventing further use of
    that session cookie. The current session cannot be revoked via this endpoint;
    to sign out the current session use the logout flow. Re-renders the sessions
    page with an updated list and success or error feedback.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      https://auth.example.com/auth/settings/sessions/550e8400-e29b-41d4-a716-446655440000/revoke
    ```
    """
    logger.debug("Session revoke requested for session_id=%s", session_id)

    session_token = request.cookies.get(get_session_cookie_name())
    if not session_token:
        return require_auth_redirect(request)

    user = await session_service.get_user_by_session_token(db, session_token)
    if not user:
        return require_auth_redirect(request)

    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()

    # Get current session
    current_session = await session_service.get_session(db, session_token)
    current_session_id = str(current_session.id) if current_session else None

    async def _render_sessions(sessions_list, error_msg=None, success_msg=None):
        html = await branding_service.render_template(
            db,
            "auth/settings/sessions.html",
            {
                "request": request,
                "active_section": "sessions",
                "sessions": sessions_list,
                "current_session_id": current_session_id,
                "error": error_msg,
                "success": success_msg,
                "tenant_prefix": tenant_prefix,
            },
            tenant_id=tenant_id,
        )
        return HTMLResponse(content=html)

    # Cannot revoke current session
    if session_id == current_session_id:
        sessions = await session_service.get_user_sessions(db, str(user.id))
        return await _render_sessions(sessions, error_msg="Cannot revoke the current session.")

    # Revoke the session
    revoked = await session_service.revoke_session_by_id(db, str(user.id), session_id)

    sessions = await session_service.get_user_sessions(db, str(user.id))

    if revoked:
        logger.info("Session %s revoked by user_id=%s", session_id, user.id)
        return await _render_sessions(sessions, success_msg="Session revoked successfully.")

    return await _render_sessions(sessions, error_msg="Session not found or already revoked.")


@router.post("/sessions/revoke-all", response_class=HTMLResponse)
async def settings_revoke_all_sessions(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    branding_service: Annotated[BrandingService, Depends(get_branding_service)],
) -> Response:
    """Revoke all sessions except the one making this request.

    Useful for a "log out everywhere else" action after a suspected compromise.
    The active session (identified by the request cookie) is preserved so the
    user remains logged in. Re-renders the sessions page showing the remaining
    single active session.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      https://auth.example.com/auth/settings/sessions/revoke-all
    ```
    """
    logger.debug("Revoke all sessions requested")

    session_token = request.cookies.get(get_session_cookie_name())
    if not session_token:
        return require_auth_redirect(request)

    user = await session_service.get_user_by_session_token(db, session_token)
    if not user:
        return require_auth_redirect(request)

    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()

    # Get current session
    current_session = await session_service.get_session(db, session_token)
    current_session_id = str(current_session.id) if current_session else None

    # Revoke all sessions except current
    count = await session_service.revoke_all_user_sessions(
        db, str(user.id), except_session_id=current_session_id
    )

    sessions = await session_service.get_user_sessions(db, str(user.id))

    logger.info("Revoked %d sessions for user_id=%s", count, user.id)
    html = await branding_service.render_template(
        db,
        "auth/settings/sessions.html",
        {
            "request": request,
            "active_section": "sessions",
            "sessions": sessions,
            "current_session_id": current_session_id,
            "error": None,
            "success": f"Revoked {count} session(s).",
            "tenant_prefix": tenant_prefix,
        },
        tenant_id=tenant_id,
    )
    return HTMLResponse(content=html)


@router.get("/sessions/api", response_class=JSONResponse)
async def get_sessions_api(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> JSONResponse:
    """Return all active sessions for the current user as JSON.

    Lists each session with its ID, IP address, user-agent, creation time, and
    a boolean indicating whether it is the current session. Intended for
    SPA/AJAX callers; browser callers should use `GET /auth/settings/sessions`.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -b cookies.txt https://auth.example.com/auth/settings/sessions/api
    ```
    """
    logger.debug("Sessions API GET requested")

    try:
        user = await get_current_user(request, db, session_service)
    except HTTPException:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "Not authenticated"},
        )

    session_token = request.cookies.get(get_session_cookie_name())
    current_session = await session_service.get_session(db, session_token or "")
    current_session_id = str(current_session.id) if current_session else None

    sessions = await session_service.get_user_sessions(db, str(user.id))

    sessions_list = [
        {
            "id": str(s.id),
            "ip_address": s.ip_address,
            "user_agent": s.user_agent,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "is_current": str(s.id) == current_session_id,
        }
        for s in sessions
    ]

    logger.debug("Returning %d sessions for user_id=%s", len(sessions_list), user.id)
    return JSONResponse(content={"sessions": sessions_list})


@router.delete("/sessions/{session_id}/api", response_class=JSONResponse)
async def delete_session_api(
    request: Request,
    session_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> JSONResponse:
    """Revoke a specific session via JSON API.

    Terminates the session identified by `session_id`. Returns 400 if the
    caller attempts to revoke their own current session, and 404 if the session
    is not found or already expired. Intended for SPA/AJAX callers; browser
    callers should POST to `/auth/settings/sessions/{session_id}/revoke`.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -X DELETE -b cookies.txt \
      https://auth.example.com/auth/settings/sessions/550e8400-e29b-41d4-a716-446655440000/api
    ```
    """
    logger.debug("Session API DELETE requested for session_id=%s", session_id)

    try:
        user = await get_current_user(request, db, session_service)
    except HTTPException:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "Not authenticated"},
        )

    session_token = request.cookies.get(get_session_cookie_name())
    current_session = await session_service.get_session(db, session_token or "")

    # Cannot revoke current session
    if current_session and str(current_session.id) == session_id:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Cannot revoke the current session."},
        )

    revoked = await session_service.revoke_session_by_id(db, str(user.id), session_id)

    if not revoked:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": "Session not found or already revoked."},
        )

    logger.info("Session %s revoked via API by user_id=%s", session_id, user.id)
    return JSONResponse(content={"message": "Session revoked successfully."})


def get_token_service(
    jwks_service: Annotated[JWKSService, Depends(get_jwks_service)],
) -> TokenService:
    """Get token service instance with JWKS service."""
    return TokenService(jwks_service)


@router.get("/applications", response_class=HTMLResponse)
async def settings_applications(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    token_service: Annotated[TokenService, Depends(get_token_service)],
    branding_service: Annotated[BrandingService, Depends(get_branding_service)],
) -> Response:
    """Render the connected applications (OAuth2 consents) page.

    Lists all OAuth2 clients that the user has authorised, together with the
    granted scopes and last-used timestamp. Each entry has a revoke button that
    posts to `/auth/settings/applications/{client_id}/revoke`.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -b cookies.txt https://auth.example.com/auth/settings/applications
    ```
    """
    logger.debug("Applications settings page requested")

    session_token = request.cookies.get(get_session_cookie_name())
    if not session_token:
        return require_auth_redirect(request)

    user = await session_service.get_user_by_session_token(db, session_token)
    if not user:
        return require_auth_redirect(request)

    # Get authorized applications
    applications = await token_service.get_user_authorized_clients(db, user.id)

    # Check if user is admin
    is_admin, admin_permissions = await check_user_is_admin(db, user)

    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()

    logger.debug("Rendering applications settings for user_id=%s", user.id)
    html = await branding_service.render_template(
        db,
        "auth/settings/applications.html",
        {
            "request": request,
            "active_section": "applications",
            "applications": applications,
            "error": None,
            "success": None,
            "is_admin": is_admin,
            "admin_permissions": admin_permissions,
            "tenant_prefix": tenant_prefix,
        },
        tenant_id=tenant_id,
    )
    return HTMLResponse(content=html)


@router.post("/applications/{client_id}/revoke", response_class=HTMLResponse)
async def settings_revoke_application(
    request: Request,
    client_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    token_service: Annotated[TokenService, Depends(get_token_service)],
    branding_service: Annotated[BrandingService, Depends(get_branding_service)],
) -> Response:
    """Revoke all tokens granted to a specific OAuth2 client.

    Invalidates every access and refresh token the user has issued to
    `client_id`. Re-renders the applications page with a success or error
    banner. The application can still request new consent from the user
    afterward unless its client registration is separately disabled.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      https://auth.example.com/auth/settings/applications/myapp-client-id/revoke
    ```
    """
    logger.debug("Application revoke requested for client_id=%s", client_id)

    session_token = request.cookies.get(get_session_cookie_name())
    if not session_token:
        return require_auth_redirect(request)

    user = await session_service.get_user_by_session_token(db, session_token)
    if not user:
        return require_auth_redirect(request)

    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()

    # Revoke access
    revoked_count = await token_service.revoke_client_access(db, user.id, client_id)

    # Get updated applications list
    applications = await token_service.get_user_authorized_clients(db, user.id)

    async def _render_apps(error_msg=None, success_msg=None):
        html = await branding_service.render_template(
            db,
            "auth/settings/applications.html",
            {
                "request": request,
                "active_section": "applications",
                "applications": applications,
                "error": error_msg,
                "success": success_msg,
                "tenant_prefix": tenant_prefix,
            },
            tenant_id=tenant_id,
        )
        return HTMLResponse(content=html)

    if revoked_count > 0:
        logger.info(
            "Application %s revoked by user_id=%s (%d tokens)",
            client_id,
            user.id,
            revoked_count,
        )
        return await _render_apps(success_msg="Application access revoked successfully.")

    return await _render_apps(error_msg="Application not found or already revoked.")


@router.get("/applications/api", response_class=JSONResponse)
async def get_applications_api(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    token_service: Annotated[TokenService, Depends(get_token_service)],
) -> JSONResponse:
    """Return all OAuth2 applications the current user has authorised as JSON.

    Returns a list of objects with `client_id`, `name`, `scopes`,
    `authorized_at`, and `last_used`. Dates are ISO-8601 strings. Intended for
    SPA/AJAX callers; browser callers should use `GET /auth/settings/applications`.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -b cookies.txt https://auth.example.com/auth/settings/applications/api
    ```
    """
    logger.debug("Applications API GET requested")

    try:
        user = await get_current_user(request, db, session_service)
    except HTTPException:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "Not authenticated"},
        )

    applications = await token_service.get_user_authorized_clients(db, user.id)

    # Convert datetime objects to ISO format for JSON serialization
    apps_list = [
        {
            "client_id": app["client_id"],
            "name": app["name"],
            "description": app["description"],
            "scopes": app["scopes"],
            "authorized_at": app["authorized_at"].isoformat() if app["authorized_at"] else None,
            "last_used": app["last_used"].isoformat() if app["last_used"] else None,
        }
        for app in applications
    ]

    logger.debug("Returning %d applications for user_id=%s", len(apps_list), user.id)
    return JSONResponse(content={"applications": apps_list})


@router.delete("/applications/{client_id}/api", response_class=JSONResponse)
async def delete_application_api(
    request: Request,
    client_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    token_service: Annotated[TokenService, Depends(get_token_service)],
) -> JSONResponse:
    """Revoke all tokens granted to a specific OAuth2 client via JSON API.

    Invalidates every access and refresh token issued to `client_id` for the
    current user. Returns 404 if no tokens exist for the client. Intended for
    SPA/AJAX callers; browser callers should POST to
    `/auth/settings/applications/{client_id}/revoke`.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -X DELETE -b cookies.txt \
      https://auth.example.com/auth/settings/applications/myapp-client-id/api
    ```
    """
    logger.debug("Application API DELETE requested for client_id=%s", client_id)

    try:
        user = await get_current_user(request, db, session_service)
    except HTTPException:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "Not authenticated"},
        )

    revoked_count = await token_service.revoke_client_access(db, user.id, client_id)

    if revoked_count == 0:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": "Application not found or already revoked."},
        )

    logger.info(
        "Application %s revoked via API by user_id=%s (%d tokens)",
        client_id,
        user.id,
        revoked_count,
    )
    return JSONResponse(
        content={
            "message": "Application access revoked successfully.",
            "revoked_tokens": revoked_count,
        }
    )


# =============================================================================
# Email Management
# =============================================================================


@router.get("/emails", response_class=HTMLResponse)
async def settings_emails(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    email_service: Annotated[EmailService, Depends(get_email_service)],
    branding_service: Annotated[BrandingService, Depends(get_branding_service)],
) -> Response:
    """Render the email addresses management page.

    Lists all email addresses linked to the account, indicating which is
    primary and which are verified. Unverified addresses show whether a valid
    verification code is already outstanding. Success and error messages are
    passed via query parameters after form-action redirects.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -b cookies.txt https://auth.example.com/auth/settings/emails
    ```
    """
    logger.debug("Emails settings page requested")

    session_token = request.cookies.get(get_session_cookie_name())
    if not session_token:
        return require_auth_redirect(request)

    user = await session_service.get_user_by_session_token(db, session_token)
    if not user:
        return require_auth_redirect(request)

    # Load user emails
    await db.refresh(user, ["emails"])

    # Build email list with verification code status
    emails = []
    for e in sorted(user.emails, key=lambda x: (not x.is_primary, x.email)):
        email_data = {
            "id": str(e.id),
            "email": e.email,
            "is_primary": e.is_primary,
            "is_verified": e.is_verified,
            "verified_at": e.verified_at.isoformat() if e.verified_at else None,
            "has_valid_code": False,
        }
        # Check for valid verification code only for unverified emails
        if not e.is_verified:
            email_data["has_valid_code"] = await email_service.has_valid_verification_code(
                db, e.email
            )
        emails.append(email_data)

    success = request.query_params.get("success")
    error = request.query_params.get("error")

    # Check if user is admin
    is_admin, admin_permissions = await check_user_is_admin(db, user)

    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()

    logger.debug("Rendering emails settings for user_id=%s", user.id)
    html = await branding_service.render_template(
        db,
        "auth/settings/emails.html",
        {
            "request": request,
            "active_section": "emails",
            "emails": emails,
            "error": error,
            "success": success,
            "is_admin": is_admin,
            "admin_permissions": admin_permissions,
            "tenant_prefix": tenant_prefix,
        },
        tenant_id=tenant_id,
    )
    return HTMLResponse(content=html)


@router.get("/emails/add", response_class=RedirectResponse)
async def settings_add_email_redirect(
    request: Request,
) -> RedirectResponse:
    """Redirect GET requests for the add-email form to the emails page.

    The add-email form lives on the main emails page; direct GET navigation to
    this URL is forwarded there. Submit the form via POST to add a new address.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -b cookies.txt https://auth.example.com/auth/settings/emails/add
    ```
    """
    tenant_prefix = get_tenant_prefix()
    logger.debug("GET request to /emails/add, redirecting to /emails")
    return RedirectResponse(
        url=f"{tenant_prefix}/auth/settings/emails",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/emails/add", response_class=RedirectResponse)
async def settings_add_email(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    email_service: Annotated[EmailService, Depends(get_email_service)],
    email: Annotated[str, Form()],
) -> RedirectResponse:
    """Add a new email address and send a verification email.

    Creates an unverified `UserEmail` record and dispatches a verification link
    to the provided address. Rejects addresses already registered by any user.
    Redirects back to the emails page with a success or error query parameter.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      -d "email=alice%40example.com" \
      https://auth.example.com/auth/settings/emails/add
    ```
    """
    logger.debug("Add email requested: %s", email)

    session_token = request.cookies.get(get_session_cookie_name())
    if not session_token:
        return require_auth_redirect(request)

    user = await session_service.get_user_by_session_token(db, session_token)
    if not user:
        return require_auth_redirect(request)

    email_lower = email.lower().strip()

    # Check if email already exists
    if await _user_service.email_exists(db, email_lower):
        logger.warning("Email already registered: %s", email_lower)
        return settings_redirect("/emails", error="Email address already registered")

    # Create new email

    user_email = UserEmail(
        user_id=user.id,
        email=email_lower,
        is_primary=False,
        is_verified=False,
    )
    await _user_service.add_email(db, user_email)
    await db.commit()

    # Send verification email with link
    base_url = str(request.base_url).rstrip("/")
    tenant_ctx = get_tenant_context()
    tenant_id = str(tenant_ctx.tenant_id) if tenant_ctx and tenant_ctx.tenant_id else None
    success = await email_service.send_verification_email(
        db,
        str(user.id),
        email_lower,
        base_url=base_url,
        tenant_id=tenant_id,
    )

    if success:
        logger.info("Email %s added for user_id=%s", email_lower, user.id)
        return settings_redirect(
            "/emails", success="Email added. Please check your inbox to verify it."
        )
    else:
        logger.warning(
            "Email %s added but verification email failed for user_id=%s", email_lower, user.id
        )
        return settings_redirect(
            "/emails",
            success="Email added but verification email could not be sent. Try resending later.",
        )


@router.post("/emails/{email_id}/remove", response_class=RedirectResponse)
async def settings_remove_email(
    request: Request,
    email_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Remove a secondary email address from the account.

    Deletes the `UserEmail` record identified by `email_id`. Blocks removal of
    the primary address (set another address as primary first) and of the last
    remaining address. Redirects back to the emails page with feedback.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      https://auth.example.com/auth/settings/emails/550e8400-e29b-41d4-a716-446655440000/remove
    ```
    """
    logger.debug("Remove email requested: %s", email_id)

    session_token = request.cookies.get(get_session_cookie_name())
    if not session_token:
        return require_auth_redirect(request)

    user = await session_service.get_user_by_session_token(db, session_token)
    if not user:
        return require_auth_redirect(request)

    # Load user emails
    await db.refresh(user, ["emails"])

    # Find the email
    target_email = None
    for e in user.emails:
        if str(e.id) == email_id:
            target_email = e
            break

    if not target_email:
        return settings_redirect("/emails", error="Email not found")

    # Cannot remove primary email
    if target_email.is_primary:
        return settings_redirect(
            "/emails", error="Cannot remove primary email. Set another email as primary first."
        )

    # Cannot remove last email
    if len(user.emails) <= 1:
        return settings_redirect("/emails", error="Cannot remove your only email address")

    email_addr = target_email.email
    await _user_service.delete_email(db, target_email)
    await db.commit()

    logger.info("Email %s removed for user_id=%s", email_addr, user.id)
    return settings_redirect("/emails", success="Email removed successfully")


@router.post("/emails/{email_id}/set-primary", response_class=RedirectResponse)
async def settings_set_primary_email(
    request: Request,
    email_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Promote a verified email address to be the primary address.

    Sets the address identified by `email_id` as the primary contact email,
    which is used for authentication recovery and OIDC `email` claims. The
    address must be verified first. Redirects back to the emails page with
    feedback.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      https://auth.example.com/auth/settings/emails/550e8400-e29b-41d4-a716-446655440000/set-primary
    ```
    """
    logger.debug("Set primary email requested: %s", email_id)

    session_token = request.cookies.get(get_session_cookie_name())
    if not session_token:
        return require_auth_redirect(request)

    user = await session_service.get_user_by_session_token(db, session_token)
    if not user:
        return require_auth_redirect(request)

    # Load user emails
    await db.refresh(user, ["emails"])

    # Find the email
    target_email = None
    for e in user.emails:
        if str(e.id) == email_id:
            target_email = e
            break

    if not target_email:
        return settings_redirect("/emails", error="Email not found")

    # Must be verified to be primary
    if not target_email.is_verified:
        return settings_redirect(
            "/emails", error="Email must be verified before setting as primary"
        )

    # Already primary
    if target_email.is_primary:
        return settings_redirect("/emails", error="This email is already primary")

    # Unset current primary and set new primary
    for e in user.emails:
        e.is_primary = str(e.id) == email_id

    await db.commit()

    logger.info("Primary email set to %s for user_id=%s", target_email.email, user.id)
    return settings_redirect("/emails", success="Primary email updated successfully")


@router.get("/emails/{email_id}/verify", response_class=RedirectResponse)
async def settings_verify_email_redirect(
    request: Request,
    email_id: str,
) -> RedirectResponse:
    """Redirect GET requests for the verify-email form to the emails page.

    The verification code form is embedded in the main emails page; direct GET
    navigation to this URL is forwarded there. Submit the verification code via
    POST to confirm email ownership.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -b cookies.txt \
      https://auth.example.com/auth/settings/emails/550e8400-e29b-41d4-a716-446655440000/verify
    ```
    """
    tenant_prefix = get_tenant_prefix()
    logger.debug("GET request to /emails/%s/verify, redirecting to /emails", email_id)
    return RedirectResponse(
        url=f"{tenant_prefix}/auth/settings/emails",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/emails/{email_id}/verify", response_class=RedirectResponse)
async def settings_verify_email(
    request: Request,
    email_id: str,
    code: Annotated[str, Form()],
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    email_service: Annotated[EmailService, Depends(get_email_service)],
) -> RedirectResponse:
    """Verify an email address using the one-time code sent by email.

    Validates `code` against the outstanding verification record for the address
    identified by `email_id`. Marks the address as verified on success. The code
    expires after a configured TTL; a fresh code can be requested via the
    resend endpoint. Redirects back to the emails page with feedback.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      -d "code=123456" \
      https://auth.example.com/auth/settings/emails/550e8400-e29b-41d4-a716-446655440000/verify
    ```
    """
    logger.debug("Email verification requested: email_id=%s", email_id)

    session_token = request.cookies.get(get_session_cookie_name())
    if not session_token:
        return require_auth_redirect(request)

    user = await session_service.get_user_by_session_token(db, session_token)
    if not user:
        return require_auth_redirect(request)

    # Load user emails
    await db.refresh(user, ["emails"])

    # Find the email
    target_email = None
    for e in user.emails:
        if str(e.id) == email_id:
            target_email = e
            break

    if not target_email:
        return settings_redirect("/emails", error="Email not found")

    # Already verified
    if target_email.is_verified:
        return settings_redirect("/emails", error="Email is already verified")

    # Verify the code
    success = await email_service.verify_code(db, target_email.email, code)

    if not success:
        logger.warning("Email verification failed: invalid code for email_id=%s", email_id)
        return settings_redirect("/emails", error="Invalid or expired verification code")

    logger.info("Email %s verified for user_id=%s", target_email.email, user.id)
    return settings_redirect("/emails", success="Email verified successfully")


@router.post("/emails/{email_id}/resend-verification", response_class=RedirectResponse)
async def settings_resend_email_verification(
    request: Request,
    email_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    email_service: Annotated[EmailService, Depends(get_email_service)],
) -> RedirectResponse:
    """Resend the verification email for an unverified address.

    Generates a new one-time verification code and dispatches it to the address
    identified by `email_id`. Rejects requests for already-verified addresses
    or addresses that do not belong to the current user. Redirects back to the
    emails page with feedback.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      https://auth.example.com/auth/settings/emails/550e8400-e29b-41d4-a716-446655440000/resend-verification
    ```
    """
    logger.debug("Resend verification requested: %s", email_id)

    session_token = request.cookies.get(get_session_cookie_name())
    if not session_token:
        return require_auth_redirect(request)

    user = await session_service.get_user_by_session_token(db, session_token)
    if not user:
        return require_auth_redirect(request)

    # Load user emails
    await db.refresh(user, ["emails"])

    # Find the email
    target_email = None
    for e in user.emails:
        if str(e.id) == email_id:
            target_email = e
            break

    if not target_email:
        return settings_redirect("/emails", error="Email not found")

    # Already verified
    if target_email.is_verified:
        return settings_redirect("/emails", error="Email is already verified")

    # Send verification email with link
    base_url = str(request.base_url).rstrip("/")
    tenant_ctx = get_tenant_context()
    tenant_id = str(tenant_ctx.tenant_id) if tenant_ctx and tenant_ctx.tenant_id else None
    success = await email_service.send_verification_email(
        db,
        str(user.id),
        target_email.email,
        base_url=base_url,
        tenant_id=tenant_id,
    )

    if not success:
        logger.error(
            "Failed to send verification email to %s, user_id=%s", target_email.email, user.id
        )
        return settings_redirect(
            "/emails", error="Failed to send verification email. Please try again later."
        )

    logger.info("Verification email resent for %s, user_id=%s", target_email.email, user.id)
    return settings_redirect("/emails", success="Verification email sent. Please check your inbox.")


# =============================================================================
# Tenant Management (User's tenant memberships)
# =============================================================================


@router.get("/organisations", response_class=HTMLResponse)
async def settings_tenants(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    branding_service: Annotated[BrandingService, Depends(get_branding_service)],
) -> Response:
    """Render the organisations (tenant memberships) page.

    Lists every organisation the authenticated user belongs to, including their
    assigned role, federated identity links (IdPs) per organisation, and
    available IdPs they can link to. Provides Leave and Unlink IdP actions.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -b cookies.txt https://auth.example.com/auth/settings/organisations
    ```
    """
    logger.debug("Tenants settings page requested")

    session_token = request.cookies.get(get_session_cookie_name())
    if not session_token:
        return require_auth_redirect(request)

    user = await session_service.get_user_by_session_token(db, session_token)
    if not user:
        return require_auth_redirect(request)

    # Get user's tenant memberships with tenant, IdP info, and custom role
    memberships = await tenant_service.list_user_memberships_with_idps(db, user.id)

    # Get user's federated identities
    federated_identities = await federation_service.list_user_federated_identities(db, user.id)

    # Build memberships list with details
    memberships_list = []
    for m in memberships:
        tenant = m.tenant
        if not tenant:
            continue

        # Get IdPs for this tenant that user is linked to
        linked_idps = []
        for fed in federated_identities:
            if fed.identity_provider and fed.identity_provider.tenant_id == tenant.id:
                linked_idps.append(
                    {
                        "id": str(fed.identity_provider.id),
                        "name": fed.identity_provider.name,
                        "provider_type": fed.identity_provider.provider_type.value,
                        "external_email": fed.external_email,
                        "last_login_at": fed.last_login_at.isoformat()
                        if fed.last_login_at
                        else None,
                    }
                )

        memberships_list.append(
            {
                "id": str(m.id),
                "tenant_id": str(tenant.id),
                "tenant_slug": tenant.slug,
                "tenant_name": tenant.display_name,
                "tenant_active": tenant.is_active,
                "role": m.role_name,
                "role_display_name": m.role_display_name,
                # The organisation pages open with `settings:read`
                "can_manage": m.has_scope("settings:read"),
                "joined_at": m.joined_at.isoformat()
                if m.joined_at
                else m.created_at.isoformat()
                if m.created_at
                else None,
                "linked_idps": linked_idps,
                "available_idps": [
                    {
                        "id": str(idp.id),
                        "name": idp.name,
                        "provider_type": idp.provider_type.value,
                        "button_text": idp.button_text,
                    }
                    for idp in tenant.identity_providers
                    if idp.is_active
                    and idp.allow_linking
                    and str(idp.id) not in [linked["id"] for linked in linked_idps]
                ],
            }
        )

    success = request.query_params.get("success")
    error = request.query_params.get("error")

    # Check if user is admin
    is_admin, admin_permissions = await check_user_is_admin(db, user)

    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()

    logger.debug("Rendering tenants settings for user_id=%s", user.id)
    html = await branding_service.render_template(
        db,
        "auth/settings/tenants.html",
        {
            "request": request,
            "active_section": "tenants",
            "memberships": memberships_list,
            "error": error,
            "success": success,
            "is_admin": is_admin,
            "admin_permissions": admin_permissions,
            "tenant_prefix": tenant_prefix,
        },
        tenant_id=tenant_id,
    )
    return HTMLResponse(content=html)


@router.post("/organisations/{tenant_id}/leave", response_class=RedirectResponse)
async def settings_leave_tenant(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Remove the current user from an organisation.

    Deletes the `TenantMember` record and unlinks any federated identities tied
    to the organisation's IdPs. Blocks the operation if the user is the sole
    owner — ownership must be transferred first. Redirects back to the
    organisations page with feedback.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      https://auth.example.com/auth/settings/organisations/550e8400-e29b-41d4-a716-446655440000/leave
    ```
    """
    logger.debug("Leave tenant requested: %s", tenant_id)

    session_token = request.cookies.get(get_session_cookie_name())
    if not session_token:
        return require_auth_redirect(request)

    user = await session_service.get_user_by_session_token(db, session_token)
    if not user:
        return require_auth_redirect(request)

    import uuid as uuid_module

    try:
        tenant_uuid = uuid_module.UUID(tenant_id)
    except ValueError:
        return settings_redirect("/organisations", error="Invalid tenant ID")

    # Find membership
    membership = await tenant_service.get_member(db, tenant_uuid, user.id)

    if not membership:
        return settings_redirect("/organisations", error="You are not a member of this tenant")

    # Cannot leave if you're the only owner (someone with * scope)
    if membership.has_scope("*"):
        # Count owners (members with * scope via their role)
        all_members = await tenant_service.list_members(db, tenant_uuid)
        owners = [m for m in all_members if m.has_scope("*")]
        if len(owners) <= 1:
            return settings_redirect(
                "/organisations",
                error="Cannot leave: you are the only owner. Transfer ownership first.",
            )

    # Remove membership
    await tenant_service.remove_member(db, membership)

    # Also unlink any federated identities for this tenant
    fed_identities = await federation_service.list_federated_identities_for_user_in_tenant(
        db, user.id, tenant_uuid
    )
    for fed in fed_identities:
        await federation_service.delete_federated_identity(db, fed)

    await db.commit()

    logger.info("User %s left tenant %s", user.id, tenant_id)
    return settings_redirect("/organisations", success="You have left the organization")


@router.post("/organisations/{tenant_id}/unlink-idp/{idp_id}", response_class=RedirectResponse)
async def settings_unlink_tenant_idp(
    request: Request,
    tenant_id: str,
    idp_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Remove the federated identity link between the user and an org IdP.

    Deletes the `FederatedIdentity` record that connects the user's account to
    the specified identity provider within the organisation. After unlinking,
    the user can no longer sign in via that IdP until they re-link. Redirects
    back to the organisations page with feedback.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265)

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      https://auth.example.com/auth/settings/organisations/550e8400-e29b-41d4-a716-446655440000/unlink-idp/7c9e6679-7425-40de-944b-e07fc1f90ae7
    ```
    """
    logger.debug("Unlink IdP requested: tenant=%s idp=%s", tenant_id, idp_id)

    session_token = request.cookies.get(get_session_cookie_name())
    if not session_token:
        return require_auth_redirect(request)

    user = await session_service.get_user_by_session_token(db, session_token)
    if not user:
        return require_auth_redirect(request)

    import uuid as uuid_module

    try:
        idp_uuid = uuid_module.UUID(idp_id)
    except ValueError:
        return settings_redirect("/organisations", error="Invalid IdP ID")

    # Find federated identity
    fed_identity = await federation_service.get_federated_identity(db, user.id, idp_uuid)

    if not fed_identity:
        return settings_redirect("/organisations", error="Identity provider link not found")

    await federation_service.delete_federated_identity(db, fed_identity)
    await db.commit()

    logger.info("User %s unlinked IdP %s", user.id, idp_id)
    return settings_redirect("/organisations", success="Identity provider unlinked successfully")


def generate_tenant_slug(name: str) -> str:
    """Generate a URL-friendly slug from an organization name.

    Args:
        name: The organization display name.

    Returns:
        A lowercase slug with only alphanumeric characters and hyphens.
    """
    # Lowercase and replace non-alphanumeric with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower())
    # Remove leading/trailing hyphens
    slug = slug.strip("-")
    # Limit to 50 chars to leave room for uniqueness suffix
    slug = slug[:50]
    # Ensure we have something
    return slug or "org"


require_tenants_write = require_scope("org:write", redirect_to_login=True)


@router.post("/organisations/create", response_class=RedirectResponse)
async def settings_create_tenant(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[tuple, Depends(require_tenants_write)],
    organization_name: Annotated[str, Form()],
) -> RedirectResponse:
    """Create a new organisation and grant the creator owner role.

    Generates a URL-friendly slug from `organization_name`, creates the `Tenant`
    record with default RBAC roles, and adds the requesting user as an owner
    member. Requires the `org:write` scope. The new organisation's allowed
    scopes are derived from the user's existing memberships.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie (RFC 6265) + `org:write` scope

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      -d "organization_name=Acme+Corp" \
      https://auth.example.com/auth/settings/organisations/create
    ```
    """
    logger.debug("Create tenant requested")

    user, _roles = auth

    # Validate organization name
    name = organization_name.strip()
    if not name:
        return settings_redirect("/organisations", error="Organization name is required")

    if len(name) > 255:
        return settings_redirect(
            "/organisations", error="Organization name must be less than 256 characters"
        )

    # Generate slug
    base_slug = generate_tenant_slug(name)
    slug = base_slug

    # Ensure slug uniqueness
    max_attempts = 10
    for _attempt in range(max_attempts):
        if not await tenant_service.slug_exists(db, slug):
            break
        # Add random suffix
        slug = f"{base_slug}-{secrets.token_hex(3)}"
    else:
        logger.error("Failed to generate unique slug for tenant after %d attempts", max_attempts)
        return settings_redirect(
            "/organisations", error="Failed to create organization. Please try again."
        )

    # Compute allowed scopes from user's existing tenant memberships
    existing_memberships = await tenant_service.list_user_memberships_with_custom_role(db, user.id)

    allowed_scopes_setting = None  # Default: all allowed
    if existing_memberships:
        user_scopes: set[str] = set()
        for m in existing_memberships:
            if m.custom_role:
                user_scopes.update(m.custom_role.scopes)

        if "*" not in user_scopes:
            all_tenant_scope_keys = set(TENANT_SCOPES.keys())
            allowed: set[str] = set()
            for scope in user_scopes:
                if scope in all_tenant_scope_keys:
                    allowed.add(scope)
                elif scope.endswith(":*"):
                    resource = scope.split(":")[0]
                    allowed.update(s for s in all_tenant_scope_keys if s.startswith(f"{resource}:"))
                    allowed.add(scope)
            allowed_scopes_setting = sorted(allowed) if allowed else None

    # Create the tenant
    tenant = Tenant(
        slug=slug,
        display_name=name,
        is_active=True,
        settings={"allowed_scopes": allowed_scopes_setting} if allowed_scopes_setting else None,
    )
    await tenant_service.add_tenant(db, tenant)

    # Create default roles for the tenant
    roles = await tenant_role_service.create_default_roles(db, tenant)
    owner_role = next((r for r in roles if r.name == "owner"), None)
    if not owner_role:
        raise HTTPException(status_code=500, detail="Failed to create owner role")

    # Create owner membership with custom role
    membership = TenantMember(
        tenant_id=tenant.id,
        user_id=user.id,
        role_id=owner_role.id,
        joined_at=datetime.now(UTC),
    )
    await tenant_service.add_member(db, membership)

    await db.commit()

    logger.info("User %s created tenant %s (slug=%s)", user.id, tenant.id, slug)
    return settings_redirect(
        "/organisations", success=f'Organization "{name}" created successfully'
    )


# =============================================================================
# Organization Owner Management
# =============================================================================


async def get_all_available_scopes(
    db: AsyncSession, tenant: Tenant | None = None
) -> dict[str, dict[str, str]]:
    """Get all available scopes grouped by category.

    Returns a dict with two keys:
    - "tenant": TENANT_SCOPES (filtered by tenant's allowed list if provided)
    - "application": scopes from the database (for application-specific permissions)
    """
    # Get tenant scopes (filtered if tenant provided)
    if tenant:
        tenant_scopes = tenant_role_service.get_tenant_allowed_scopes(tenant)
    else:
        tenant_scopes = TENANT_SCOPES

    # Get application scopes from database
    scopes = await scope_service.list_active(db)
    db_scopes = {s.name: s.description or s.name for s in scopes}

    return {
        "tenant": tenant_scopes,
        "application": db_scopes,
    }


def org_redirect(tenant_id: str, path: str = "", **query_params) -> RedirectResponse:
    """Create a redirect to an org settings page with tenant prefix.

    Args:
        tenant_id: The tenant UUID.
        path: The path after /org/{tenant_id} (e.g., "/edit", "/branding").
        **query_params: Query parameters to add to the URL.

    Returns:
        RedirectResponse with proper tenant prefix.
    """
    tenant_prefix = get_tenant_prefix()
    url = f"{tenant_prefix}/auth/settings/org/{tenant_id}{path}"
    if query_params:
        url += "?" + urlencode(query_params)
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


class OrgPermissions:
    """The scopes the signed-in member holds in an organisation, for the templates.

    Built once per page from the membership and given to the template as `can`, so
    that a template asks `can["idp:write"]` instead of re-implementing the rules: the
    answer is the one of `TenantMember.has_scope`, the check the guards apply, with
    the same wildcards (`idp:*`, `*`). It only decides what is displayed; the route
    behind a control still answers 403 on its own.
    """

    __slots__ = ("_membership",)

    def __init__(self, membership: TenantMember) -> None:
        self._membership = membership

    def __getitem__(self, scope: str) -> bool:
        return bool(self._membership.has_scope(scope))


async def require_tenant_manager(
    request: Request,
    tenant_id: str,
    db: AsyncSession,
    session_service: SessionService,
    required_scope: str,
) -> tuple[User, Tenant, TenantMember]:
    """Verify user is authenticated and has required scope for tenant management.

    Args:
        request: The HTTP request.
        tenant_id: UUID string of the tenant.
        db: Database session.
        session_service: Session service.
        required_scope: The organisation scope the operation requires, for instance
            `members:invite` or `branding:write`. There is no default: every route names
            its own scope, so that a forgotten one cannot silently fall back to a weaker
            check.

    Returns:
        Tuple of (user, tenant, membership) if authorized.

    Raises:
        HTTPException 401: If not authenticated.
        HTTPException 403: If user doesn't have required scope.
        HTTPException 404: If tenant not found.
    """
    session_token = request.cookies.get(get_session_cookie_name())
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = await session_service.get_user_by_session_token(db, session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")

    try:
        tenant_uuid = uuid.UUID(tenant_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid tenant ID")

    tenant = await tenant_service.get_by_id_with_all_relations(db, tenant_uuid)

    if not tenant:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Find user's membership with custom_role loaded
    membership = next(
        (m for m in tenant.members if m.user_id == user.id),
        None,
    )

    if not membership:
        raise HTTPException(
            status_code=403,
            detail="You are not a member of this organization",
        )

    # Check if member has required scope
    if not membership.has_scope(required_scope):
        raise HTTPException(
            status_code=403,
            detail=f"You don't have permission to perform this action (requires: {required_scope})",
        )

    return user, tenant, membership


def org_tenant_to_dict(tenant: Tenant) -> dict:
    """Convert Tenant model to dictionary format for org pages."""
    from sqlalchemy import inspect

    insp = inspect(tenant)
    members_loaded = "members" not in insp.unloaded
    idp_loaded = "identity_providers" not in insp.unloaded

    return {
        "id": str(tenant.id),
        "slug": tenant.slug,
        "display_name": tenant.display_name,
        "custom_domain": tenant.custom_domain,
        "custom_domain_status": tenant.custom_domain_status.value
        if tenant.custom_domain_status
        else None,
        "custom_domain_verified_at": tenant.custom_domain_verified_at.isoformat()
        if tenant.custom_domain_verified_at
        else None,
        "custom_domain_ssl_at": tenant.custom_domain_ssl_at.isoformat()
        if tenant.custom_domain_ssl_at
        else None,
        "custom_domain_error": tenant.custom_domain_error,
        "custom_domain_checked_at": tenant.custom_domain_checked_at.isoformat()
        if tenant.custom_domain_checked_at
        else None,
        "is_active": tenant.is_active,
        "settings": tenant.settings or {},
        "members_count": len(tenant.members) if members_loaded and tenant.members else 0,
        "idp_count": len(tenant.identity_providers)
        if idp_loaded and tenant.identity_providers
        else 0,
        "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
        "updated_at": tenant.updated_at.isoformat() if tenant.updated_at else None,
    }


def org_member_to_dict(member: TenantMember, user_email: str | None = None) -> dict:
    """Convert TenantMember model to dictionary format."""
    return {
        "id": str(member.id),
        "user_id": str(member.user_id),
        "user_email": user_email,
        "user_name": member.user.profile.name if member.user and member.user.profile else None,
        "role": member.role_name,  # Uses custom_role.name or fallback to role.value
        "role_id": str(member.role_id) if member.role_id else None,
        "role_display_name": member.role_display_name,
        "is_owner": member.has_scope("*"),
        "joined_at": member.joined_at.isoformat() if member.joined_at else None,
        "invited_at": member.invited_at.isoformat() if member.invited_at else None,
        "created_at": member.created_at.isoformat() if member.created_at else None,
    }


def org_idp_to_dict(idp: IdentityProvider) -> dict:
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


def org_branding_to_dict(branding: TenantBranding | None) -> dict | None:
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


def org_template_to_dict(template: TenantTemplate) -> dict:
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


def webhook_to_dict(
    webhook: TenantWebhook, deliveries: list[WebhookDelivery] | None = None
) -> dict:
    """Convert TenantWebhook into a template-friendly dict."""
    return {
        "id": str(webhook.id),
        "tenant_id": str(webhook.tenant_id),
        "name": webhook.name,
        "url": webhook.url,
        "events": list(webhook.events or []),
        "headers": dict(webhook.headers or {}),
        "is_active": webhook.is_active,
        "last_triggered_at": webhook.last_triggered_at.isoformat()
        if webhook.last_triggered_at
        else None,
        "last_status_code": webhook.last_status_code,
        "last_error": webhook.last_error,
        "failure_count": webhook.failure_count,
        "created_at": webhook.created_at.isoformat() if webhook.created_at else None,
        "updated_at": webhook.updated_at.isoformat() if webhook.updated_at else None,
        "recent_deliveries": [webhook_delivery_to_dict(d) for d in (deliveries or [])],
    }


def webhook_delivery_to_dict(delivery: WebhookDelivery) -> dict:
    """Convert WebhookDelivery into a template-friendly dict."""
    return {
        "id": str(delivery.id),
        "event": delivery.event,
        "status": delivery.status.value
        if isinstance(delivery.status, WebhookDeliveryStatus)
        else delivery.status,
        "attempt": delivery.attempt,
        "max_attempts": delivery.max_attempts,
        "response_status": delivery.response_status,
        "error": delivery.error,
        "duration_ms": delivery.duration_ms,
        "delivered_at": delivery.delivered_at.isoformat() if delivery.delivered_at else None,
        "next_retry_at": delivery.next_retry_at.isoformat() if delivery.next_retry_at else None,
        "created_at": delivery.created_at.isoformat() if delivery.created_at else None,
    }


def _build_webhook_events_by_group() -> dict[str, list[str]]:
    """Group WebhookEvent values by their top-level prefix for UI rendering."""
    groups: dict[str, list[str]] = {}
    for event in WebhookEvent:
        prefix = event.value.split(".", 1)[0]
        groups.setdefault(prefix, []).append(event.value)
    for key in groups:
        groups[key].sort()
    return dict(sorted(groups.items()))


async def _load_tenant_webhooks(
    db: AsyncSession, tenant_id: uuid.UUID, *, deliveries_per_webhook: int = 20
) -> list[dict]:
    """Return webhooks for ``tenant_id`` with their N most recent deliveries.

    Runs one query for webhooks and one per webhook for deliveries; fine for
    the handful of webhooks a tenant typically configures.
    """
    webhooks = await webhook_service.list_all_for_tenant(db, tenant_id=tenant_id)

    out: list[dict] = []
    for webhook in webhooks:
        deliveries = await webhook_service.list_recent_deliveries(
            db, webhook_id=webhook.id, limit=deliveries_per_webhook
        )
        out.append(webhook_to_dict(webhook, list(deliveries)))
    return out


@router.get("/org/{tenant_id}", response_class=HTMLResponse)
async def org_detail_page(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    trust_service: Annotated[TrustPolicyService, Depends(get_trust_service)],
) -> Response:
    """Render the organisation detail dashboard for members with access.

    Displays member list, IdP list, custom roles, trust configuration, and
    webhook list (filtered by the viewer's `webhooks:read` scope). One-shot
    webhook secrets are surfaced via `new_webhook_secret` query parameter
    after creation or rotation and are never stored in HTML. Requires at least
    `settings:read` org membership scope.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `settings:read`

    **Example:**
    ```
    curl -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000
    ```
    """
    logger.debug("Org detail page requested: tenant=%s", tenant_id)

    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="settings:read"
    )

    # Get member emails
    members_list = []
    for member in tenant.members:
        user_email = await tenant_service.get_member_primary_email(db, member.user_id)
        members_list.append(org_member_to_dict(member, user_email))

    # Sort by role then name
    role_order = {"owner": 0, "admin": 1, "member": 2}
    members_list.sort(key=lambda m: (role_order.get(m["role"], 99), m.get("user_name") or ""))

    # Get IdPs
    idps_list = [org_idp_to_dict(idp) for idp in tenant.identity_providers]
    idps_list.sort(key=lambda i: i["display_order"])

    success = request.query_params.get("success")
    error = request.query_params.get("error")
    # One-shot secret reveal after create/rotate. The secret is surfaced via
    # the redirect URL query params; never rendered from DB state.
    new_webhook_id = request.query_params.get("new_webhook_id")
    new_webhook_secret = request.query_params.get("new_webhook_secret")

    # Check if user is admin
    is_admin, admin_permissions = await check_user_is_admin(db, user)

    # Get trust config
    trust_config = await trust_service.get_tenant_trust_config(db, tenant.id)
    available_tenants = await trust_service.get_available_tenants_for_trust(db, tenant.id)

    # Get branding and tenant prefix
    branding = await get_branding_for_request(db)
    tenant_prefix = get_tenant_prefix()

    # Webhooks (visible to members with webhooks:read, which the webhooks:*
    # on admin and * on owner both grant).
    can_view_webhooks = membership.has_scope("webhooks:read")
    webhooks_list: list[dict] = []
    if can_view_webhooks:
        webhooks_list = await _load_tenant_webhooks(db, tenant.id)

    templates = get_templates()
    return templates.TemplateResponse(
        request=request,
        name="auth/settings/org/detail.html",
        context={
            "can": OrgPermissions(membership),
            "active_section": "tenants",
            "tenant": org_tenant_to_dict(tenant),
            "members": members_list,
            "identity_providers": idps_list,
            "tenant_roles": sorted(
                [
                    {
                        "id": str(r.id),
                        "name": r.name,
                        "display_name": r.display_name,
                        "description": r.description,
                        "scopes": r.scopes,
                        "is_system": r.is_system,
                        "is_default": r.is_default,
                    }
                    for r in tenant.roles
                ],
                key=lambda r: str(r.get("display_name", "")),
            ),
            "role_member_counts": {
                str(r.id): sum(1 for m in tenant.members if m.role_id == r.id) for r in tenant.roles
            },
            "idp_types": [t.value for t in IdentityProviderType],
            "trust_mode": trust_config["trust_mode"] if trust_config else "none",
            "trusted_sources": trust_config["trusted_sources"] if trust_config else [],
            "available_tenants": available_tenants,
            "webhooks": webhooks_list,
            "webhook_events_by_group": _build_webhook_events_by_group(),
            "new_webhook_id": new_webhook_id,
            "new_webhook_secret": new_webhook_secret,
            "success": success,
            "error": error,
            "is_admin": is_admin,
            "admin_permissions": admin_permissions,
            "branding": branding,
            "tenant_prefix": tenant_prefix,
        },
    )


@router.get("/org/{tenant_id}/edit", response_class=HTMLResponse)
async def org_edit_page(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> Response:
    """Render the organisation edit form for settings managers.

    Displays the display name, the e-mail sender and the allowed scopes (saved
    by routes that require `settings:write`) and the custom domain (saved by a
    route that requires `domain:write`, shown with `domain:read` or
    `domain:write`). A member only sees the forms of the scopes they hold. The
    scope picker is filtered to only scopes the current member can grant.
    Requires at least the `settings:read` org scope.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `settings:read`

    **Example:**
    ```
    curl -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/edit
    ```
    """
    logger.debug("Org edit page requested: tenant=%s", tenant_id)

    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="settings:read"
    )

    error = request.query_params.get("error")
    success = request.query_params.get("success")

    is_admin, admin_permissions = await check_user_is_admin(db, user)
    branding = await get_branding_for_request(db)
    tenant_prefix = get_tenant_prefix()

    # Load scopes the user can manage (filtered by their role)
    all_scopes = await scope_service.list_active(db)
    user_scopes = [s for s in all_scopes if membership.has_scope(s.name)]

    tenant_settings = tenant.settings or {}
    allowed_list = tenant_settings.get("allowed_scopes")
    user_scope_names = {s.name for s in user_scopes}
    current_allowed = set(allowed_list) & user_scope_names if allowed_list else set()

    templates = get_templates()
    return templates.TemplateResponse(
        request=request,
        name="auth/settings/org/edit.html",
        context={
            "can": OrgPermissions(membership),
            "active_section": "tenants",
            "tenant": org_tenant_to_dict(tenant),
            "scope_groups": build_scope_groups_from_db(user_scopes),
            "current_allowed": current_allowed,
            "error": error,
            "success": success,
            "cname_target": settings.custom_domain_cname_target or settings.tenant_base_domain,
            "is_admin": is_admin,
            "admin_permissions": admin_permissions,
            "branding": branding,
            "tenant_prefix": tenant_prefix,
        },
    )


@router.post("/org/{tenant_id}/edit", response_class=RedirectResponse)
async def org_edit_submit(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Process the organisation edit form submission.

    Persists the `display_name` change and dispatches a `tenant.updated` webhook
    event. The custom domain is not part of this form: it is saved by
    `POST /auth/settings/org/{tenant_id}/domain`, which requires `domain:write`,
    so a member holding `settings:write` alone can rename the organisation but
    never change its domain (a `custom_domain` field posted here is ignored).

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `settings:write`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      -d "display_name=Acme+Corp" \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/edit
    ```
    """
    logger.debug("Org edit submit: tenant=%s", tenant_id)

    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="settings:write"
    )

    form_data = await request.form()
    display_name = str(form_data.get("display_name", "")).strip()

    if not display_name:
        return org_redirect(tenant_id, "/edit", error="Display name is required")

    if len(display_name) > 255:
        return org_redirect(
            tenant_id, "/edit", error="Display name must be less than 256 characters"
        )

    tenant.display_name = display_name

    await _dispatch_tenant_event(
        db,
        tenant_id=tenant.id,
        event=WebhookEvent.TENANT_UPDATED,
        data={
            "tenant_id": str(tenant.id),
            "display_name": display_name,
            "custom_domain": tenant.custom_domain,
            "actor_id": str(user.id),
        },
    )

    await db.commit()

    logger.info("User %s updated org %s", user.id, tenant_id)
    return org_redirect(tenant_id, "", success="Organization updated successfully")


@router.post("/org/{tenant_id}/domain", response_class=RedirectResponse)
async def org_domain_submit(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Set, change or remove the custom domain of an organisation.

    Persists `custom_domain` (an empty value removes it). When the domain
    changes, resets the verification state to `PENDING` and asynchronously
    triggers a DNS verification Celery task; removing the domain triggers a
    config-removal task. Dispatches a `tenant.updated` webhook event on change.
    The scope is `domain:write`, which no default role other than the owner
    (`*`) holds: `settings:write` does not allow to change the domain.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `domain:write`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      -d "custom_domain=acme.example.com" \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/domain
    ```
    """
    logger.debug("Org domain submit: tenant=%s", tenant_id)

    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="domain:write"
    )

    form_data = await request.form()
    custom_domain = str(form_data.get("custom_domain", "")).strip() or None

    # Track if custom domain changed
    old_custom_domain = tenant.custom_domain
    domain_changed = custom_domain != old_custom_domain
    if not domain_changed:
        return org_redirect(tenant_id, "/edit", success="Custom domain unchanged")

    tenant.custom_domain = custom_domain

    if custom_domain:
        # New domain configured - set to pending and trigger verification
        tenant.custom_domain_status = CustomDomainStatus.PENDING
    else:
        # Domain removed - clear status
        tenant.custom_domain_status = None
    tenant.custom_domain_verified_at = None
    tenant.custom_domain_ssl_at = None
    tenant.custom_domain_error = None
    tenant.custom_domain_checked_at = None

    await _dispatch_tenant_event(
        db,
        tenant_id=tenant.id,
        event=WebhookEvent.TENANT_UPDATED,
        data={
            "tenant_id": str(tenant.id),
            "display_name": tenant.display_name,
            "custom_domain": custom_domain,
            "actor_id": str(user.id),
        },
    )

    await db.commit()

    # Trigger tasks after commit
    if custom_domain:
        # Trigger DNS verification task
        from auth.tasks.custom_domain import verify_custom_domain_dns

        verify_custom_domain_dns.delay(str(tenant.id), custom_domain, tenant.slug)
        logger.info(
            "User %s configured custom domain %s for org %s", user.id, custom_domain, tenant_id
        )
    elif old_custom_domain:
        # Trigger config removal task
        from auth.tasks.custom_domain import remove_custom_domain_config

        remove_custom_domain_config.delay(old_custom_domain, tenant.slug)
        logger.info(
            "User %s removed custom domain %s from org %s",
            user.id,
            old_custom_domain,
            tenant_id,
        )

    return org_redirect(tenant_id, "/edit", success="Custom domain updated")


@router.post("/org/{tenant_id}/email-sender", response_class=RedirectResponse)
async def org_email_sender_submit(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Save the outbound email sender address and name for an organisation.

    Persists `email_sender_address` and `email_sender_name` into the tenant's
    `settings` JSONB column and invalidates the platform sender cache so the
    next email dispatch picks up the new values. Requires the `settings:write`
    org scope.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `settings:write`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      -d "email_sender_address=noreply%40acme.com&email_sender_name=Acme" \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/email-sender
    ```
    """
    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="settings:write"
    )

    form_data = await request.form()
    sender_address = str(form_data.get("email_sender_address", "")).strip() or None
    sender_name = str(form_data.get("email_sender_name", "")).strip() or None

    current_settings = dict(tenant.settings or {})
    current_settings["email_sender_address"] = sender_address
    current_settings["email_sender_name"] = sender_name
    tenant.settings = current_settings

    await db.commit()

    from auth.tasks.email import invalidate_platform_sender_cache

    invalidate_platform_sender_cache()

    logger.info("User %s updated email sender for org %s", user.id, tenant_id)
    return org_redirect(tenant_id, "/edit", success="Email sender updated")


@router.post("/org/{tenant_id}/allowed-scopes", response_class=RedirectResponse)
async def org_allowed_scopes_submit(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Save the list of allowed OAuth2 scopes for an organisation.

    Validates each submitted scope name against the active scope registry, then
    persists the filtered list in `tenant.settings["allowed_scopes"]`. When set,
    only these scopes may be requested by clients scoped to this organisation.
    Clearing the list restores the default (all scopes allowed).

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `settings:write`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      -d "allowed_scopes=openid&allowed_scopes=profile&allowed_scopes=email" \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/allowed-scopes
    ```
    """
    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="settings:write"
    )

    form_data = await request.form()
    selected = form_data.getlist("allowed_scopes")

    # Validate scopes against DB
    active_scopes = await scope_service.list_active(db)
    valid_scopes = {s.name for s in active_scopes}

    for scope in selected:
        if scope not in valid_scopes:
            return org_redirect(tenant_id, "/edit", error=f"Invalid scope: {scope}")

    current_settings = dict(tenant.settings or {})
    current_settings["allowed_scopes"] = sorted(selected) if selected else None
    tenant.settings = current_settings

    await db.commit()

    logger.info("User %s updated allowed scopes for org %s", user.id, tenant_id)
    return org_redirect(tenant_id, "/edit", success="Allowed scopes updated")


@router.get("/org/{tenant_id}/verify-domain", response_class=RedirectResponse)
async def org_verify_domain(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Trigger DNS verification for the organisation's custom domain.

    Resets the domain status to `PENDING` and enqueues the
    `verify_custom_domain_dns` Celery task. Returns an error if no domain is
    configured or if verification/SSL provisioning is already in progress.
    Poll `GET /auth/settings/org/{tenant_id}/domain-status` to monitor progress.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `domain:write`

    **Example:**
    ```
    curl -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/verify-domain
    ```
    """
    logger.debug("Manual domain verification requested: tenant=%s", tenant_id)

    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="domain:write"
    )

    if not tenant.custom_domain:
        return org_redirect(tenant_id, "/edit", error="No custom domain configured")

    if tenant.custom_domain_status == CustomDomainStatus.ACTIVE:
        return org_redirect(tenant_id, "/edit", success="Domain is already active")

    if tenant.custom_domain_status in [
        CustomDomainStatus.SSL_PROVISIONING,
        CustomDomainStatus.DNS_VERIFYING,
    ]:
        return org_redirect(tenant_id, "/edit", error="Domain verification already in progress")

    # Reset status to pending and trigger verification
    tenant.custom_domain_status = CustomDomainStatus.PENDING
    tenant.custom_domain_error = None
    await db.commit()

    # Trigger DNS verification task
    from auth.tasks.custom_domain import verify_custom_domain_dns

    verify_custom_domain_dns.delay(str(tenant.id), tenant.custom_domain, tenant.slug)

    logger.info(
        "User %s triggered manual domain verification for %s", user.id, tenant.custom_domain
    )
    return org_redirect(tenant_id, "/edit", success="Domain verification started")


@router.get("/org/{tenant_id}/domain-status")
async def org_domain_status(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> dict:
    """Return the custom domain verification status for polling.

    Returns a JSON object with `custom_domain`, `status` (pending/dns_verifying/
    ssl_provisioning/active/failed), `error`, `verified_at`, `ssl_at`, and
    `checked_at`. Designed for lightweight polling by the org edit page.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `domain:read`

    **Example:**
    ```
    curl -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/domain-status
    ```
    """
    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="domain:read"
    )

    return {
        "custom_domain": tenant.custom_domain,
        "status": tenant.custom_domain_status.value if tenant.custom_domain_status else None,
        "error": tenant.custom_domain_error,
        "verified_at": tenant.custom_domain_verified_at.isoformat()
        if tenant.custom_domain_verified_at
        else None,
        "ssl_at": tenant.custom_domain_ssl_at.isoformat() if tenant.custom_domain_ssl_at else None,
        "checked_at": tenant.custom_domain_checked_at.isoformat()
        if tenant.custom_domain_checked_at
        else None,
    }


# -----------------------------------------------------------------------------
# Member Management
# -----------------------------------------------------------------------------


@router.post("/org/{tenant_id}/members/add", response_class=RedirectResponse)
async def org_add_member_submit(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Add an existing user to the organisation by email address.

    Looks up the user by their primary email, validates the target role belongs
    to this organisation, and creates a `TenantMember` record. Dispatches a
    `member.added` webhook event. Rejects the request if the user is already a
    member. Requires the `members:invite` org scope.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `members:invite`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      -d "email=bob%40example.com&role_id=7c9e6679-7425-40de-944b-e07fc1f90ae7" \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/members/add
    ```
    """
    logger.debug("Org add member: tenant=%s", tenant_id)

    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="members:invite"
    )

    form_data = await request.form()
    email = str(form_data.get("email", "")).strip().lower()
    role_id_str = str(form_data.get("role_id") or form_data.get("role", ""))

    if not email:
        return org_redirect(tenant_id, "", error="Email is required")

    # Find the role - can be role_id (UUID) or role name
    role: TenantCustomRole | None = None
    try:
        role_uuid = uuid.UUID(str(role_id_str))
        role = await tenant_role_service.get_role_by_id(db, role_uuid)
    except ValueError:
        # Try by name (backward compat)
        role = await tenant_role_service.get_role_by_name(db, tenant.id, str(role_id_str))

    if not role:
        # Default to member role
        role = await tenant_role_service.get_role_by_name(db, tenant.id, "member")

    if role and role.tenant_id != tenant.id:
        return org_redirect(tenant_id, "", error="Invalid role")

    # Find user by email
    user_email = await _user_service.get_user_email_row(db, email)

    if not user_email:
        return org_redirect(tenant_id, "", error=f"User not found with email {email}")

    # Check if already a member
    existing_membership = await tenant_service.get_existing_membership(
        db, tenant.id, user_email.user_id
    )
    if existing_membership:
        return org_redirect(tenant_id, "", error="User is already a member")

    new_member = TenantMember(
        tenant_id=tenant.id,
        user_id=user_email.user_id,
        role_id=role.id if role else None,
        invited_by=user.id,
        invited_at=datetime.now(UTC),
        joined_at=datetime.now(UTC),
    )
    await tenant_service.add_member(db, new_member)

    await _dispatch_tenant_event(
        db,
        tenant_id=tenant.id,
        event=WebhookEvent.MEMBER_ADDED,
        data={
            "tenant_id": str(tenant.id),
            "user_id": str(user_email.user_id),
            "email": user_email.email,
            "role_id": str(role.id) if role else None,
            "role_name": role.name if role else None,
            "actor_id": str(user.id),
        },
    )

    await db.commit()

    logger.info("User %s added member %s to org %s", user.id, user_email.user_id, tenant_id)
    return org_redirect(tenant_id, "", success="Member added successfully")


@router.post("/org/{tenant_id}/members/{member_id}/update-role", response_class=RedirectResponse)
async def org_update_member_role_submit(
    request: Request,
    tenant_id: str,
    member_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Update an organisation member's assigned role.

    Reassigns the member identified by `member_id` to the role specified by
    `role_id`. Only owners can promote to or demote other owners. Prevents
    demoting the sole owner. Dispatches a `member.role_changed` webhook event.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `members:update`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      -d "role_id=7c9e6679-7425-40de-944b-e07fc1f90ae7" \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/members/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/update-role
    ```
    """
    logger.debug("Org update member role: tenant=%s member=%s", tenant_id, member_id)

    user, tenant, ownership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="members:update"
    )

    form_data = await request.form()
    role_id_str = str(form_data.get("role_id") or form_data.get("role", ""))

    try:
        member_uuid = uuid.UUID(member_id)
    except ValueError:
        return org_redirect(tenant_id, "", error="Invalid member ID")

    # Find the member with custom_role loaded
    member = await tenant_service.get_member_in_tenant(db, member_uuid, tenant.id)

    if not member:
        return org_redirect(tenant_id, "", error="Member not found")

    # Find the new role - can be role_id (UUID) or role name
    new_role: TenantCustomRole | None = None
    try:
        role_uuid = uuid.UUID(str(role_id_str))
        new_role = await tenant_role_service.get_role_by_id(db, role_uuid)
    except ValueError:
        # Try by name (backward compat with old form)
        new_role = await tenant_role_service.get_role_by_name(db, tenant.id, str(role_id_str))

    if not new_role:
        return org_redirect(tenant_id, "", error="Invalid role")

    if new_role.tenant_id != tenant.id:
        return org_redirect(tenant_id, "", error="Role does not belong to this organization")

    # Check if trying to assign owner role
    is_new_role_owner = new_role.has_scope("*")
    is_member_owner = member.has_scope("*")
    is_ownership_owner = ownership.has_scope("*")

    # Only owners can promote to owner or manage other owners
    if not is_ownership_owner:
        if is_new_role_owner:
            return org_redirect(tenant_id, "", error="Only owners can promote members to owner")
        if is_member_owner:
            return org_redirect(tenant_id, "", error="Only owners can change other owners' roles")

    # If demoting the only owner, prevent it
    if is_member_owner and not is_new_role_owner:
        # Count current owners (members with * scope)
        all_members = await tenant_service.list_members(db, tenant.id)
        owners = [m for m in all_members if m.has_scope("*")]
        if len(owners) <= 1:
            return org_redirect(
                tenant_id, "", error="Cannot demote the only owner. Add another owner first."
            )

    # Assign the new role
    old_role_id = member.role_id
    member.role_id = new_role.id

    await _dispatch_tenant_event(
        db,
        tenant_id=tenant.id,
        event=WebhookEvent.MEMBER_ROLE_CHANGED,
        data={
            "tenant_id": str(tenant.id),
            "member_id": str(member.id),
            "user_id": str(member.user_id),
            "old_role_id": str(old_role_id) if old_role_id else None,
            "new_role_id": str(new_role.id),
            "new_role_name": new_role.name,
            "actor_id": str(user.id),
        },
    )

    await db.commit()

    logger.info(
        "User %s updated member %s role to %s in org %s",
        user.id,
        member_id,
        new_role.name,
        tenant_id,
    )
    return org_redirect(tenant_id, "", success="Member role updated")


@router.post("/org/{tenant_id}/members/{member_id}/remove", response_class=RedirectResponse)
async def org_remove_member_submit(
    request: Request,
    tenant_id: str,
    member_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Remove a member from the organisation.

    Deletes the `TenantMember` record identified by `member_id`. Only owners
    can remove other owners; prevents removal of the sole owner. Dispatches a
    `member.removed` webhook event on success.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `members:remove`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/members/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/remove
    ```
    """
    logger.debug("Org remove member: tenant=%s member=%s", tenant_id, member_id)

    user, tenant, ownership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="members:remove"
    )

    try:
        member_uuid = uuid.UUID(member_id)
    except ValueError:
        return org_redirect(tenant_id, "", error="Invalid member ID")

    # Find the member with custom_role loaded
    member = await tenant_service.get_member_in_tenant(db, member_uuid, tenant.id)

    if not member:
        return org_redirect(tenant_id, "", error="Member not found")

    is_member_owner = member.has_scope("*")
    is_ownership_owner = ownership.has_scope("*")

    # Only owners can remove other owners
    if is_member_owner and not is_ownership_owner:
        return org_redirect(tenant_id, "", error="Only owners can remove other owners")

    # Cannot remove the only owner
    if is_member_owner:
        # Count current owners (members with * scope)
        all_members = await tenant_service.list_members(db, tenant.id)
        owners = [m for m in all_members if m.has_scope("*")]
        if len(owners) <= 1:
            return org_redirect(
                tenant_id, "", error="Cannot remove the only owner. Add another owner first."
            )

    removed_user_id = str(member.user_id)
    removed_member_id = str(member.id)
    await tenant_service.remove_member(db, member)
    await db.flush()

    await _dispatch_tenant_event(
        db,
        tenant_id=tenant.id,
        event=WebhookEvent.MEMBER_REMOVED,
        data={
            "tenant_id": str(tenant.id),
            "member_id": removed_member_id,
            "user_id": removed_user_id,
            "actor_id": str(user.id),
        },
    )
    await db.commit()

    logger.info("User %s removed member %s from org %s", user.id, member_id, tenant_id)
    return org_redirect(tenant_id, "", success="Member removed")


# ============================================================================
# Organization Roles Management Endpoints
# ============================================================================


@router.get("/org/{tenant_id}/roles", response_class=HTMLResponse)
async def org_roles_page(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    templates: Annotated[Any, Depends(get_templates)],
) -> Response:
    """Render the organisation roles management page.

    Lists all custom roles for the organisation with member counts and assigned
    scopes. Write and delete actions are conditionally enabled based on the
    viewer's `roles:write` and `roles:delete` membership scopes.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `roles:read`

    **Example:**
    ```
    curl -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/roles
    ```
    """
    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="roles:read"
    )

    # Get all roles for this tenant
    roles = await tenant_role_service.get_tenant_roles(db, tenant.id)

    # Get member count for each role
    role_stats = {}
    for role in roles:
        role_stats[str(role.id)] = await tenant_role_service.get_role_member_count(db, role)

    return templates.TemplateResponse(
        request,
        "auth/settings/org/roles.html",
        {
            "can": OrgPermissions(membership),
            "active_section": "tenants",
            "user": user,
            "tenant": tenant,
            "membership": membership,
            "roles": roles,
            "role_stats": role_stats,
            "available_scopes": tenant_role_service.get_tenant_allowed_scopes(tenant),
            "tenant_prefix": get_tenant_prefix(),
        },
    )


@router.get("/org/{tenant_id}/roles/create", response_class=HTMLResponse)
async def org_role_create_page(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    templates: Annotated[Any, Depends(get_templates)],
) -> Response:
    """Render the new-role creation form for the organisation.

    Displays name, display_name, description, and scope picker fields. Available
    scopes are filtered by the tenant's allowed-scopes configuration. Submitting
    the form POSTs to `POST /auth/settings/org/{tenant_id}/roles/create`.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `roles:write`

    **Example:**
    ```
    curl -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/roles/create
    ```
    """
    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="roles:write"
    )

    # Get all available scopes (tenant + application), filtered by tenant config
    available_scopes = await get_all_available_scopes(db, tenant=tenant)

    return templates.TemplateResponse(
        request,
        "auth/settings/org/role_form.html",
        {
            "can": OrgPermissions(membership),
            "active_section": "tenants",
            "user": user,
            "tenant": tenant,
            "membership": membership,
            "role": None,
            "available_scopes": available_scopes,
            "tenant_prefix": get_tenant_prefix(),
            "form_action": f"/auth/settings/org/{tenant_id}/roles/create",
            "form_title": "Create Role",
        },
    )


@router.post("/org/{tenant_id}/roles/create", response_class=RedirectResponse)
async def org_role_create_submit(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Process the new-role creation form submission.

    Validates the role name (must be unique within the org) and creates the
    `TenantCustomRole` with the selected scopes. Dispatches a `role.created`
    webhook event. Redirects to the roles list with feedback.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `roles:write`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      -d "name=editor&display_name=Editor&scopes=content%3Awrite" \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/roles/create
    ```
    """
    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="roles:write"
    )

    form_data = await request.form()
    name = str(form_data.get("name", "")).strip().lower()
    display_name = str(form_data.get("display_name", "")).strip()
    description = str(form_data.get("description", "")).strip() or None
    scopes = [str(s) for s in form_data.getlist("scopes")]

    if not name:
        return org_redirect(tenant_id, "/roles", error="Role name is required")

    if not display_name:
        display_name = name.capitalize()

    try:
        role = await tenant_role_service.create_role(
            db, tenant.id, name, display_name, scopes, description, tenant=tenant
        )
        await _dispatch_tenant_event(
            db,
            tenant_id=tenant.id,
            event=WebhookEvent.ROLE_CREATED,
            data={
                "tenant_id": str(tenant.id),
                "role_id": str(role.id),
                "name": role.name,
                "display_name": role.display_name,
                "scopes": list(role.scopes or []),
                "actor_id": str(user.id),
            },
        )
        await db.commit()
        logger.info("User %s created role %s in org %s", user.id, role.name, tenant_id)
        return org_redirect(tenant_id, "/roles", success=f'Role "{display_name}" created')
    except ValueError as e:
        return org_redirect(tenant_id, "/roles", error=str(e))


@router.get("/org/{tenant_id}/roles/{role_id}/edit", response_class=HTMLResponse)
async def org_role_edit_page(
    request: Request,
    tenant_id: str,
    role_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    templates: Annotated[Any, Depends(get_templates)],
) -> Response:
    """Render the role edit form for an existing custom role.

    Loads the role's current display_name, description, scopes, and is_default
    flag into the form. Available scopes are filtered by the tenant's allowed
    list. System roles can only have their display_name and description edited.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `roles:write`

    **Example:**
    ```
    curl -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/roles/7c9e6679-7425-40de-944b-e07fc1f90ae7/edit
    ```
    """
    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="roles:write"
    )

    try:
        role_uuid = uuid.UUID(role_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid role ID")

    role = await tenant_role_service.get_role_by_id(db, role_uuid)
    if not role or role.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Role not found")

    # Get all available scopes (tenant + application), filtered by tenant config
    available_scopes = await get_all_available_scopes(db, tenant=tenant)

    return templates.TemplateResponse(
        request,
        "auth/settings/org/role_form.html",
        {
            "can": OrgPermissions(membership),
            "active_section": "tenants",
            "user": user,
            "tenant": tenant,
            "membership": membership,
            "role": role,
            "available_scopes": available_scopes,
            "tenant_prefix": get_tenant_prefix(),
            "form_action": f"/auth/settings/org/{tenant_id}/roles/{role_id}/edit",
            "form_title": f"Edit Role: {role.display_name}",
        },
    )


@router.post("/org/{tenant_id}/roles/{role_id}/edit", response_class=RedirectResponse)
async def org_role_edit_submit(
    request: Request,
    tenant_id: str,
    role_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Process the role edit form submission.

    Updates display_name, description, and scopes (skipped for system roles).
    Handles the `is_default` toggle: setting it clears the previous default
    role; unsetting it leaves the org without a designated default until another
    is picked. Dispatches a `role.updated` webhook event.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `roles:write`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      -d "display_name=Senior+Editor&scopes=content%3Awrite&is_default=true" \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/roles/7c9e6679-7425-40de-944b-e07fc1f90ae7/edit
    ```
    """
    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="roles:write"
    )

    try:
        role_uuid = uuid.UUID(role_id)
    except ValueError:
        return org_redirect(tenant_id, "/roles", error="Invalid role ID")

    role = await tenant_role_service.get_role_by_id(db, role_uuid)
    if not role or role.tenant_id != tenant.id:
        return org_redirect(tenant_id, "/roles", error="Role not found")

    form_data = await request.form()
    display_name = str(form_data.get("display_name", "")).strip() or None
    description = str(form_data.get("description", "")).strip() or None
    scopes = [str(s) for s in form_data.getlist("scopes")] if not role.is_system else None
    is_default_requested = form_data.get("is_default") in ("true", "on", "1")

    try:
        await tenant_role_service.update_role(
            db, role, display_name, scopes, description, tenant=tenant
        )

        # Apply is_default flip after the main update so we have the final
        # scopes to warn against (the warning is UI-side only — per product
        # decision, we still allow "*" roles to be marked default).
        if is_default_requested and not role.is_default:
            await tenant_role_service.set_default_role(db, tenant.id, role.id)
        elif not is_default_requested and role.is_default:
            # User explicitly unchecked -> clear; tenant falls back to
            # the "member" role by name until another one is picked.
            await tenant_role_service.clear_default_role(db, tenant.id)

        await _dispatch_tenant_event(
            db,
            tenant_id=tenant.id,
            event=WebhookEvent.ROLE_UPDATED,
            data={
                "tenant_id": str(tenant.id),
                "role_id": str(role.id),
                "name": role.name,
                "display_name": role.display_name,
                "scopes": list(role.scopes or []),
                "is_default": role.is_default,
                "actor_id": str(user.id),
            },
        )
        await db.commit()
        logger.info("User %s updated role %s in org %s", user.id, role.name, tenant_id)
        return org_redirect(tenant_id, "/roles", success=f'Role "{role.display_name}" updated')
    except ValueError as e:
        return org_redirect(tenant_id, "/roles", error=str(e))


@router.post("/org/{tenant_id}/roles/{role_id}/delete", response_class=RedirectResponse)
async def org_role_delete_submit(
    request: Request,
    tenant_id: str,
    role_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Permanently delete a custom role from the organisation.

    Removes the `TenantCustomRole` record. System roles cannot be deleted.
    Members previously assigned this role are downgraded to the default role.
    Dispatches a `role.deleted` webhook event. Redirects to the roles list.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `roles:delete`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/roles/7c9e6679-7425-40de-944b-e07fc1f90ae7/delete
    ```
    """
    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="roles:delete"
    )

    try:
        role_uuid = uuid.UUID(role_id)
    except ValueError:
        return org_redirect(tenant_id, "/roles", error="Invalid role ID")

    role = await tenant_role_service.get_role_by_id(db, role_uuid)
    if not role or role.tenant_id != tenant.id:
        return org_redirect(tenant_id, "/roles", error="Role not found")

    role_name = role.display_name
    deleted_role_id = str(role.id)
    deleted_role_slug = role.name

    try:
        await tenant_role_service.delete_role(db, role)
        await _dispatch_tenant_event(
            db,
            tenant_id=tenant.id,
            event=WebhookEvent.ROLE_DELETED,
            data={
                "tenant_id": str(tenant.id),
                "role_id": deleted_role_id,
                "name": deleted_role_slug,
                "actor_id": str(user.id),
            },
        )
        await db.commit()
        logger.info("User %s deleted role %s in org %s", user.id, role_name, tenant_id)
        return org_redirect(tenant_id, "/roles", success=f'Role "{role_name}" deleted')
    except ValueError as e:
        return org_redirect(tenant_id, "/roles", error=str(e))


# ============================================================================
# Organization IdP Management Endpoints
# ============================================================================


@router.get("/org/{tenant_id}/idp/create", response_class=HTMLResponse)
async def org_idp_create_page(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> Response:
    """Render the identity provider creation form for org owners.

    Displays fields for IdP name, type (OIDC/SAML), client ID, client secret,
    discovery URL, scopes, and display options. The submitted client secret is
    stored encrypted; it is never returned in plaintext after this form.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `idp:write`

    **Example:**
    ```
    curl -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/idp/create
    ```
    """
    logger.debug("Org IdP create page: tenant=%s", tenant_id)
    templates = get_templates()

    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="idp:write"
    )

    error = request.query_params.get("error")

    tenant_prefix = get_tenant_prefix()

    return templates.TemplateResponse(
        request=request,
        name="auth/settings/org/idp_create.html",
        context={
            "can": OrgPermissions(membership),
            "tenant": org_tenant_to_dict(tenant),
            "idp_types": [{"value": t.value, "label": t.name} for t in IdentityProviderType],
            "error": error,
            "tenant_prefix": tenant_prefix,
            "branding": await get_branding_for_request(db),
        },
    )


@router.post("/org/{tenant_id}/idp/create", response_class=RedirectResponse)
async def org_idp_create_submit(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Process the identity provider creation form submission.

    Creates an `IdentityProvider` record for the organisation. The client
    secret (if provided) is encrypted at rest before storage. Dispatches an
    `idp.created` webhook event. Redirects to the org detail page on success.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `idp:write`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      -d "name=Google+SSO&provider_type=oidc&client_id=xxx&client_secret=yyy&is_active=true" \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/idp/create
    ```
    """
    logger.debug("Org IdP create submit: tenant=%s", tenant_id)

    user, tenant, ownership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="idp:write"
    )

    form_data = await request.form()

    name = str(form_data.get("name", "")).strip()
    provider_type_str = str(form_data.get("provider_type", "oidc"))
    client_id = str(form_data.get("client_id", "")).strip()
    client_secret = str(form_data.get("client_secret", "")).strip()
    discovery_url = str(form_data.get("discovery_url", "")).strip() or None
    scopes_str = str(form_data.get("scopes", "openid profile email")).strip()

    if not name or not client_id:
        return org_redirect(tenant_id, "/idp/create", error="Name and Client ID are required")

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
        await tenant_service.add_idp(db, idp)
        await _dispatch_tenant_event(
            db,
            tenant_id=tenant.id,
            event=WebhookEvent.IDP_CREATED,
            data={
                "tenant_id": str(tenant.id),
                "idp_id": str(idp.id),
                "name": idp.name,
                "provider_type": idp.provider_type.value,
                "actor_id": str(user.id),
            },
        )
        await db.commit()
        await db.refresh(idp)

        logger.info("User %s created IdP %s for org %s", user.id, idp.id, tenant_id)

        return org_redirect(tenant_id, "", success="Identity provider created successfully")
    except Exception as e:
        logger.error("Failed to create IdP for org %s: %s", tenant_id, e)
        return org_redirect(tenant_id, "/idp/create", error=str(e))


@router.get("/org/{tenant_id}/idp/{idp_id}/edit", response_class=HTMLResponse)
async def org_idp_edit_page(
    request: Request,
    tenant_id: str,
    idp_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> Response:
    """Render the identity provider edit form for org owners.

    Loads current IdP settings into the form. The client secret field is masked
    (`has_secret` flag indicates whether one is stored); leave it blank to keep
    the existing secret. Federated user count is shown as a warning before
    destructive changes.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `idp:write`

    **Example:**
    ```
    curl -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/idp/7c9e6679-7425-40de-944b-e07fc1f90ae7/edit
    ```
    """
    logger.debug("Org IdP edit page: tenant=%s idp=%s", tenant_id, idp_id)
    templates = get_templates()

    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="idp:write"
    )

    try:
        idp_uuid = uuid.UUID(idp_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid IdP ID",
        )

    idp = await tenant_service.get_idp_scoped_with_federated(db, idp_uuid, tenant.id)

    if not idp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Identity provider not found",
        )

    error = request.query_params.get("error")
    tenant_prefix = get_tenant_prefix()

    idp_dict = org_idp_to_dict(idp)
    idp_dict["has_secret"] = idp.client_secret_encrypted is not None
    idp_dict["federated_count"] = len(idp.federated_identities)

    return templates.TemplateResponse(
        request=request,
        name="auth/settings/org/idp_edit.html",
        context={
            "can": OrgPermissions(membership),
            "tenant": org_tenant_to_dict(tenant),
            "idp": idp_dict,
            "idp_types": [{"value": t.value, "label": t.name} for t in IdentityProviderType],
            "error": error,
            "tenant_prefix": tenant_prefix,
            "branding": await get_branding_for_request(db),
        },
    )


@router.post("/org/{tenant_id}/idp/{idp_id}/edit", response_class=RedirectResponse)
async def org_idp_edit_submit(
    request: Request,
    tenant_id: str,
    idp_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Process the identity provider edit form submission.

    Updates all mutable IdP fields. The client secret is only overwritten when
    a non-empty value is submitted. Dispatches an `idp.updated` webhook event.
    Redirects to the org detail page on success.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `idp:write`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      -d "name=Google+SSO&client_id=new-client-id&is_active=true" \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/idp/7c9e6679-7425-40de-944b-e07fc1f90ae7/edit
    ```
    """
    logger.debug("Org IdP edit submit: tenant=%s idp=%s", tenant_id, idp_id)

    user, tenant, ownership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="idp:write"
    )

    try:
        idp_uuid = uuid.UUID(idp_id)
    except ValueError:
        return org_redirect(tenant_id, "", error="Invalid IdP ID")

    idp = await tenant_service.get_idp_scoped(db, idp_uuid, tenant.id)

    if not idp:
        return org_redirect(tenant_id, "", error="Identity provider not found")

    form_data = await request.form()

    name = str(form_data.get("name", "")).strip()
    client_id = str(form_data.get("client_id", "")).strip()
    client_secret = str(form_data.get("client_secret", "")).strip()
    discovery_url = str(form_data.get("discovery_url", "")).strip() or None
    scopes_str = str(form_data.get("scopes", "openid profile email")).strip()

    if not name or not client_id:
        return org_redirect(
            tenant_id, f"/idp/{idp_id}/edit", error="Name and Client ID are required"
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

        await _dispatch_tenant_event(
            db,
            tenant_id=tenant.id,
            event=WebhookEvent.IDP_UPDATED,
            data={
                "tenant_id": str(tenant.id),
                "idp_id": str(idp.id),
                "name": idp.name,
                "provider_type": idp.provider_type.value,
                "actor_id": str(user.id),
            },
        )
        await db.commit()

        logger.info("User %s updated IdP %s for org %s", user.id, idp_id, tenant_id)

        return org_redirect(tenant_id, "", success="Identity provider updated successfully")
    except Exception as e:
        logger.error("Failed to update IdP %s for org %s: %s", idp_id, tenant_id, e)
        return org_redirect(tenant_id, f"/idp/{idp_id}/edit", error=str(e))


@router.post("/org/{tenant_id}/idp/{idp_id}/toggle", response_class=RedirectResponse)
async def org_idp_toggle_submit(
    request: Request,
    tenant_id: str,
    idp_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Toggle an identity provider's active status.

    Flips `is_active` on the specified IdP. When disabled, the IdP login button
    is hidden from the login page and federation is suspended. No webhook event
    is dispatched for this lightweight toggle. Redirects to the org detail page.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `idp:write`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/idp/7c9e6679-7425-40de-944b-e07fc1f90ae7/toggle
    ```
    """
    logger.debug("Org IdP toggle: tenant=%s idp=%s", tenant_id, idp_id)

    user, tenant, ownership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="idp:write"
    )

    try:
        idp_uuid = uuid.UUID(idp_id)
    except ValueError:
        return org_redirect(tenant_id, "", error="Invalid IdP ID")

    idp = await tenant_service.get_idp_scoped(db, idp_uuid, tenant.id)

    if not idp:
        return org_redirect(tenant_id, "", error="Identity provider not found")

    idp.is_active = not idp.is_active
    await db.commit()

    action = "enabled" if idp.is_active else "disabled"
    logger.info("User %s %s IdP %s for org %s", user.id, action, idp_id, tenant_id)
    return org_redirect(tenant_id, "", success=f"Identity provider {action}")


@router.post("/org/{tenant_id}/idp/{idp_id}/delete", response_class=RedirectResponse)
async def org_idp_delete_submit(
    request: Request,
    tenant_id: str,
    idp_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Permanently delete an identity provider and all its federated identities.

    Removes the `IdentityProvider` record along with all linked `FederatedIdentity`
    rows (cascaded). Users who previously authenticated only via this IdP may
    lose access unless they have a password set. Dispatches an `idp.deleted`
    webhook event.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `idp:delete`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/idp/7c9e6679-7425-40de-944b-e07fc1f90ae7/delete
    ```
    """
    logger.debug("Org IdP delete: tenant=%s idp=%s", tenant_id, idp_id)

    user, tenant, ownership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="idp:delete"
    )

    try:
        idp_uuid = uuid.UUID(idp_id)
    except ValueError:
        return org_redirect(tenant_id, "", error="Invalid IdP ID")

    idp = await tenant_service.get_idp_scoped(db, idp_uuid, tenant.id)

    if not idp:
        return org_redirect(tenant_id, "", error="Identity provider not found")

    deleted_idp_name = idp.name
    deleted_idp_type = idp.provider_type.value
    await tenant_service.delete_idp(db, idp)
    await db.flush()

    await _dispatch_tenant_event(
        db,
        tenant_id=tenant.id,
        event=WebhookEvent.IDP_DELETED,
        data={
            "tenant_id": str(tenant.id),
            "idp_id": idp_id,
            "name": deleted_idp_name,
            "provider_type": deleted_idp_type,
            "actor_id": str(user.id),
        },
    )
    await db.commit()

    logger.info("User %s deleted IdP %s from org %s", user.id, idp_id, tenant_id)
    return org_redirect(tenant_id, "", success="Identity provider deleted")


# ============================================================================
# Organization Branding Management Endpoints
# ============================================================================


@router.get("/org/{tenant_id}/branding", response_class=HTMLResponse)
async def org_branding_page(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> Response:
    """Render the branding customisation page for org owners.

    Displays current colour palette, logo URLs, font settings, custom CSS/JS,
    and the "Powered by" toggle. Defaults from `BrandingConfig` are pre-filled
    when no custom branding record exists yet.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `branding:read`

    **Example:**
    ```
    curl -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/branding
    ```
    """
    logger.debug("Org branding page: tenant=%s", tenant_id)
    templates = get_templates()

    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="branding:read"
    )

    # Reload tenant with branding relationship
    reloaded = await tenant_service.get_by_id_with_branding(db, tenant.id)
    assert reloaded is not None
    tenant = reloaded

    success = request.query_params.get("success")
    error = request.query_params.get("error")
    tenant_prefix = get_tenant_prefix()

    # Get branding or use defaults
    branding_dict = org_branding_to_dict(tenant.branding)
    if not branding_dict:
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

    # Get page branding for base template styling
    page_branding = await get_branding_for_request(db)

    return templates.TemplateResponse(
        request=request,
        name="auth/settings/org/branding.html",
        context={
            "can": OrgPermissions(membership),
            "tenant": org_tenant_to_dict(tenant),
            "tenant_branding": branding_dict,
            "has_branding": tenant.branding is not None,
            "success": success,
            "error": error,
            "tenant_prefix": tenant_prefix,
            "branding": page_branding,
        },
    )


@router.post("/org/{tenant_id}/branding", response_class=RedirectResponse)
async def org_branding_submit(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Process the branding customisation form submission.

    Creates or updates the `TenantBranding` record with all colour, font, logo,
    custom CSS/JS, and `show_powered_by` values. Applies immediately to all
    tenant-scoped HTML pages. Redirects back to the branding page with feedback.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `branding:write`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      -d "primary_color=%23007bff&font_family=Inter&show_powered_by=true" \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/branding
    ```
    """
    logger.debug("Org branding submit: tenant=%s", tenant_id)

    user, tenant, ownership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="branding:write"
    )

    # Reload tenant with branding relationship
    reloaded = await tenant_service.get_by_id_with_branding(db, tenant.id)
    assert reloaded is not None
    tenant = reloaded

    form_data = await request.form()

    try:
        branding = tenant.branding
        if not branding:
            branding = TenantBranding(tenant_id=tenant.id)
            await tenant_service.add_branding(db, branding)

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

        logger.info("User %s updated branding for org %s", user.id, tenant_id)

        return org_redirect(tenant_id, "/branding", success="Branding updated successfully")
    except Exception as e:
        logger.error("Failed to update branding for org %s: %s", tenant_id, e)
        return org_redirect(tenant_id, "/branding", error=str(e))


@router.post("/org/{tenant_id}/branding/reset", response_class=RedirectResponse)
async def org_branding_reset(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Delete the organisation's custom branding and revert to platform defaults.

    Removes the `TenantBranding` record entirely so the platform default colours
    and fonts apply again. This is irreversible — branding must be reconfigured
    manually after a reset. Redirects to the branding page with feedback.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `branding:write`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/branding/reset
    ```
    """
    logger.debug("Org branding reset: tenant=%s", tenant_id)

    user, tenant, ownership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="branding:write"
    )

    branding = await tenant_service.get_branding(db, tenant.id)

    if branding:
        await tenant_service.delete_branding(db, branding)
        await db.commit()
        logger.info("User %s reset branding for org %s", user.id, tenant_id)

    return org_redirect(tenant_id, "/branding", success="Branding reset to defaults")


# ============================================================================
# Organization Registration Fields Configuration
# ============================================================================

_ORG_REGISTRATION_FIELD_KEYS = [
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


@router.get("/org/{tenant_id}/registration-fields", response_class=HTMLResponse)
async def org_registration_fields_page(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> Response:
    """Render the registration fields configuration page for org owners.

    Displays a checklist of optional OIDC profile fields that can be requested
    during user registration (nickname, given/family name, birthdate, address,
    etc.). Current visibility settings are loaded from `tenant.settings["registration_fields"]`.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `settings:read`

    **Example:**
    ```
    curl -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/registration-fields
    ```
    """
    logger.debug("Org registration fields page: tenant=%s", tenant_id)
    templates = get_templates()

    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="settings:read"
    )

    tenant_settings = tenant.settings or {}
    fields = dict.fromkeys(_ORG_REGISTRATION_FIELD_KEYS, True)
    overrides = tenant_settings.get("registration_fields", {})
    for k in fields:
        if k in overrides:
            fields[k] = bool(overrides[k])

    success = request.query_params.get("success")
    error = request.query_params.get("error")
    tenant_prefix = get_tenant_prefix()

    # Check if user is admin
    is_admin, admin_permissions = await check_user_is_admin(db, user)

    page_branding = await get_branding_for_request(db)

    return templates.TemplateResponse(
        request=request,
        name="auth/settings/org/registration_fields.html",
        context={
            "can": OrgPermissions(membership),
            "tenant": org_tenant_to_dict(tenant),
            "fields": fields,
            "success": success,
            "error": error,
            "tenant_prefix": tenant_prefix,
            "branding": page_branding,
            "is_admin": is_admin,
            "admin_permissions": admin_permissions,
        },
    )


@router.post("/org/{tenant_id}/registration-fields", response_class=RedirectResponse)
async def org_registration_fields_submit(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Save the registration fields configuration for an organisation.

    Persists the boolean visibility flags for each registration field into
    `tenant.settings["registration_fields"]`. Fields set to false are hidden
    from the registration form for this tenant.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `settings:write`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      -d "firstname=true&lastname=true&phone_number=false" \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/registration-fields
    ```
    """
    logger.debug("Org registration fields submit: tenant=%s", tenant_id)

    user, tenant, ownership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="settings:write"
    )

    form_data = await request.form()
    tenant_prefix = get_tenant_prefix()

    try:
        reg_fields = {}
        for key in _ORG_REGISTRATION_FIELD_KEYS:
            reg_fields[key] = form_data.get(key) == "true"

        current_settings = dict(tenant.settings or {})
        current_settings["registration_fields"] = reg_fields
        tenant.settings = current_settings

        await db.commit()
        logger.info("Org registration fields updated for tenant=%s", tenant_id)

        return RedirectResponse(
            url=f"{tenant_prefix}/auth/settings/org/{tenant_id}/registration-fields?success=Registration+fields+updated",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        logger.error("Failed to update org registration fields: %s", e)
        return RedirectResponse(
            url=f"{tenant_prefix}/auth/settings/org/{tenant_id}/registration-fields?error={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


# Organization Profile Fields Configuration
# ============================================================================


@router.get("/org/{tenant_id}/profile-fields", response_class=HTMLResponse)
async def org_profile_fields_page(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> Response:
    """Render the profile fields visibility configuration page for org owners.

    Displays a checklist controlling which OIDC profile fields are visible on
    the user profile settings page for members of this organisation. Defaults
    come from `DEFAULT_PROFILE_FIELDS`; overrides are stored in
    `tenant.settings["profile_fields"]`.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `settings:read`

    **Example:**
    ```
    curl -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/profile-fields
    ```
    """
    logger.debug("Org profile fields page: tenant=%s", tenant_id)
    templates = get_templates()

    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="settings:read"
    )

    tenant_settings = tenant.settings or {}
    fields = dict(DEFAULT_PROFILE_FIELDS)
    overrides = tenant_settings.get("profile_fields", {})
    for k in fields:
        if k in overrides:
            fields[k] = bool(overrides[k])

    success = request.query_params.get("success")
    error = request.query_params.get("error")
    tenant_prefix = get_tenant_prefix()

    is_admin, admin_permissions = await check_user_is_admin(db, user)
    page_branding = await get_branding_for_request(db)

    return templates.TemplateResponse(
        request=request,
        name="auth/settings/org/profile_fields.html",
        context={
            "can": OrgPermissions(membership),
            "tenant": org_tenant_to_dict(tenant),
            "fields": fields,
            "success": success,
            "error": error,
            "tenant_prefix": tenant_prefix,
            "branding": page_branding,
            "is_admin": is_admin,
            "admin_permissions": admin_permissions,
        },
    )


@router.post("/org/{tenant_id}/profile-fields", response_class=RedirectResponse)
async def org_profile_fields_submit(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Save the profile fields visibility configuration for an organisation.

    Persists the boolean visibility flags for each profile field into
    `tenant.settings["profile_fields"]`. Fields set to false are hidden from
    the profile settings page for members of this organisation.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `settings:write`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      -d "avatar=true&birthdate=false&address=false" \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/profile-fields
    ```
    """
    logger.debug("Org profile fields submit: tenant=%s", tenant_id)

    user, tenant, ownership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="settings:write"
    )

    form_data = await request.form()
    tenant_prefix = get_tenant_prefix()

    try:
        pf = {}
        for key in _PROFILE_FIELD_KEYS:
            pf[key] = form_data.get(key) == "true"

        current_settings = dict(tenant.settings or {})
        current_settings["profile_fields"] = pf
        tenant.settings = current_settings

        await db.commit()
        logger.info("Org profile fields updated for tenant=%s", tenant_id)

        return RedirectResponse(
            url=f"{tenant_prefix}/auth/settings/org/{tenant_id}/profile-fields?success=Profile+fields+updated",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception as e:
        logger.error("Failed to update org profile fields: %s", e)
        return RedirectResponse(
            url=f"{tenant_prefix}/auth/settings/org/{tenant_id}/profile-fields?error={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


# Organization OAuth2 Clients Management
# ============================================================================

_ORG_CLIENT_OIDC_SCOPES = [
    {"name": "openid", "description": "OpenID Connect authentication"},
    {"name": "profile", "description": "User profile information"},
    {"name": "email", "description": "User email address"},
    {"name": "offline_access", "description": "Refresh tokens for offline access"},
]


def _generate_client_id() -> str:
    return secrets.token_urlsafe(24)


def _generate_client_secret() -> str:
    return secrets.token_urlsafe(32)


async def _get_org_client(db, client_uuid_str: str, tenant_id) -> OAuth2Client:
    try:
        cid = uuid.UUID(client_uuid_str)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid client ID")
    client = await _oauth2_client_service.get_scoped_to_tenant(db, cid, tenant_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


def _org_client_to_dict(client: OAuth2Client) -> dict:
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
        "access_token_expiry_seconds": client.access_token_expiry_seconds,
        "refresh_token_expiry_seconds": client.refresh_token_expiry_seconds,
        "created_at": client.created_at.isoformat() if client.created_at else None,
    }


@router.get("/org/{tenant_id}/clients", response_class=HTMLResponse)
async def org_clients_page(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> Response:
    """Render the OAuth2 clients list page for the organisation.

    Lists all `OAuth2Client` records scoped to this tenant, sorted by creation
    date. The "Create new client" button is only shown when the viewer has the
    `clients:write` scope. Mirrors the JSON API at `GET /api/v1/me/organisations/{id}/clients`.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `clients:read`

    **Example:**
    ```
    curl -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/clients
    ```
    """
    logger.debug("Org clients page: tenant=%s", tenant_id)
    templates = get_templates()

    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="clients:read"
    )

    tenant_clients, _ = await _oauth2_client_service.list(
        db, page=1, page_size=1000, tenant_id=tenant.id
    )
    clients = [_org_client_to_dict(c) for c in tenant_clients]

    success = request.query_params.get("success")
    error = request.query_params.get("error")
    tenant_prefix = get_tenant_prefix()
    is_admin, admin_permissions = await check_user_is_admin(db, user)
    page_branding = await get_branding_for_request(db)

    return templates.TemplateResponse(
        request=request,
        name="auth/settings/org/clients/list.html",
        context={
            "can": OrgPermissions(membership),
            "tenant": org_tenant_to_dict(tenant),
            "membership": membership,
            "clients": clients,
            "success": success,
            "error": error,
            "tenant_prefix": tenant_prefix,
            "branding": page_branding,
            "is_admin": is_admin,
            "admin_permissions": admin_permissions,
        },
    )


@router.get("/org/{tenant_id}/clients/create", response_class=HTMLResponse)
async def org_client_create_page(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> Response:
    """Render the OAuth2 client creation form for the organisation.

    Displays fields for name, description, homepage URL, redirect URIs (newline-
    separated), grant types, scopes (filtered by tenant's allowed list),
    confidentiality, PKCE, consent requirement, and token expiry overrides.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `clients:write`

    **Example:**
    ```
    curl -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/clients/create
    ```
    """
    logger.debug("Org client create page: tenant=%s", tenant_id)
    templates = get_templates()

    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="clients:write"
    )

    tenant_prefix = get_tenant_prefix()
    is_admin, admin_permissions = await check_user_is_admin(db, user)
    page_branding = await get_branding_for_request(db)

    # Load scopes allowed for this tenant
    tenant_allowed = (tenant.settings or {}).get("allowed_scopes")
    tenant_scopes = await scope_service.list_active(
        db, names=tenant_allowed if tenant_allowed is not None else None
    )

    return templates.TemplateResponse(
        request=request,
        name="auth/settings/org/clients/create.html",
        context={
            "can": OrgPermissions(membership),
            "tenant": org_tenant_to_dict(tenant),
            "membership": membership,
            "scope_groups": build_scope_groups_from_db(tenant_scopes),
            "tenant_prefix": tenant_prefix,
            "branding": page_branding,
            "is_admin": is_admin,
            "admin_permissions": admin_permissions,
        },
    )


@router.post("/org/{tenant_id}/clients/create", response_class=RedirectResponse)
async def org_client_create_submit(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Process the OAuth2 client creation form submission.

    Generates a random `client_id` and (for confidential clients) a plaintext
    `client_secret` returned once via the redirect's `new_secret` query param.
    Dispatches a `client.created` webhook event. Redirects to the new client's
    detail page.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `clients:write`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      -d "name=My+App&is_confidential=true&redirect_uris=https%3A%2F%2Fapp.example.com%2Fcallback" \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/clients/create
    ```
    """
    logger.debug("Org client create submit: tenant=%s", tenant_id)

    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="clients:write"
    )

    form_data = await request.form()

    try:
        name = str(form_data.get("name", "")).strip()
        if not name:
            return org_redirect(tenant_id, "/clients/create", error="Client name is required")

        description = str(form_data.get("description", "")).strip() or None
        homepage_url = str(form_data.get("homepage_url", "")).strip() or None

        # Parse redirect URIs (newline-separated)
        raw_uris = str(form_data.get("redirect_uris", "")).strip()
        redirect_uris = [u.strip() for u in raw_uris.splitlines() if u.strip()]

        # Parse scopes (scope_ prefix checkboxes)
        scopes = [key.removeprefix("scope_") for key in form_data if key.startswith("scope_")]

        # Parse grant types (grant_ prefix checkboxes)
        grant_types = [key.removeprefix("grant_") for key in form_data if key.startswith("grant_")]

        is_confidential = form_data.get("is_confidential") == "true"
        require_pkce = form_data.get("require_pkce") == "true"
        require_consent = form_data.get("require_consent") == "true"

        # Token expiry
        access_expiry = str(form_data.get("access_token_expiry_seconds", "")).strip()
        access_token_expiry_seconds = int(access_expiry) if access_expiry else None
        refresh_expiry = str(form_data.get("refresh_token_expiry_seconds", "")).strip()
        refresh_token_expiry_seconds = int(refresh_expiry) if refresh_expiry else None

        # Allowed origins (newline-separated)
        raw_origins = str(form_data.get("allowed_origins", "")).strip()
        allowed_origins = [o.strip() for o in raw_origins.splitlines() if o.strip()] or None

        # Generate credentials
        client_id = _generate_client_id()
        client_secret = _generate_client_secret() if is_confidential else None
        client_secret_hash = hash_password(client_secret) if client_secret else None

        token_endpoint_auth_method = "client_secret_basic" if is_confidential else "none"

        new_client = OAuth2Client(
            client_id=client_id,
            client_secret_hash=client_secret_hash,
            name=name,
            description=description,
            homepage_url=homepage_url,
            redirect_uris=redirect_uris,
            allowed_scopes=scopes,
            allowed_grant_types=grant_types,
            token_endpoint_auth_method=token_endpoint_auth_method,
            is_confidential=is_confidential,
            require_pkce=require_pkce,
            require_consent=require_consent,
            allowed_origins=allowed_origins,
            access_token_expiry_seconds=access_token_expiry_seconds,
            refresh_token_expiry_seconds=refresh_token_expiry_seconds,
            tenant_id=tenant.id,
        )
        await _oauth2_client_service.add(db, new_client)
        await _dispatch_tenant_event(
            db,
            tenant_id=tenant.id,
            event=WebhookEvent.CLIENT_CREATED,
            data={
                "tenant_id": str(tenant.id),
                "client_id_value": new_client.client_id,
                "client_uuid": str(new_client.id),
                "name": new_client.name,
                "is_confidential": new_client.is_confidential,
                "actor_id": str(user.id),
            },
        )
        await db.commit()
        await db.refresh(new_client)

        logger.info("Created org OAuth2 client %s for tenant=%s", new_client.id, tenant_id)

        redirect_kwargs: dict = {"success": "Client created successfully"}
        if client_secret:
            redirect_kwargs["new_secret"] = client_secret

        return org_redirect(tenant_id, f"/clients/{new_client.id}", **redirect_kwargs)
    except Exception as e:
        logger.error("Failed to create org OAuth2 client: %s", e)
        return org_redirect(tenant_id, "/clients/create", error=str(e))


@router.get("/org/{tenant_id}/clients/{client_uuid}", response_class=HTMLResponse)
async def org_client_detail_page(
    request: Request,
    tenant_id: str,
    client_uuid: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> Response:
    """Render the OAuth2 client detail page.

    Displays all configuration fields for the specified client. A one-shot
    `new_secret` query parameter surfaces the plaintext secret immediately after
    creation or rotation — it is never stored in HTML state and will not be
    shown again.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `clients:read`

    **Example:**
    ```
    curl -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/clients/7c9e6679-7425-40de-944b-e07fc1f90ae7
    ```
    """
    logger.debug("Org client detail: tenant=%s client=%s", tenant_id, client_uuid)
    templates = get_templates()

    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="clients:read"
    )

    client = await _get_org_client(db, client_uuid, tenant.id)

    success = request.query_params.get("success")
    error = request.query_params.get("error")
    new_secret = request.query_params.get("new_secret")
    tenant_prefix = get_tenant_prefix()
    is_admin, admin_permissions = await check_user_is_admin(db, user)
    page_branding = await get_branding_for_request(db)

    return templates.TemplateResponse(
        request=request,
        name="auth/settings/org/clients/detail.html",
        context={
            "can": OrgPermissions(membership),
            "tenant": org_tenant_to_dict(tenant),
            "membership": membership,
            "client": _org_client_to_dict(client),
            "success": success,
            "error": error,
            "new_secret": new_secret,
            "tenant_prefix": tenant_prefix,
            "branding": page_branding,
            "is_admin": is_admin,
            "admin_permissions": admin_permissions,
        },
    )


@router.get("/org/{tenant_id}/clients/{client_uuid}/edit", response_class=HTMLResponse)
async def org_client_edit_page(
    request: Request,
    tenant_id: str,
    client_uuid: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> Response:
    """Render the OAuth2 client edit form.

    Pre-fills all current client settings. The scope picker is filtered by the
    tenant's allowed scopes. Switching between confidential and public client
    types triggers secret generation or removal on submission.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `clients:write`

    **Example:**
    ```
    curl -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/clients/7c9e6679-7425-40de-944b-e07fc1f90ae7/edit
    ```
    """
    logger.debug("Org client edit page: tenant=%s client=%s", tenant_id, client_uuid)
    templates = get_templates()

    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="clients:write"
    )

    client = await _get_org_client(db, client_uuid, tenant.id)

    # Load scopes allowed for this tenant
    tenant_allowed = (tenant.settings or {}).get("allowed_scopes")
    tenant_scopes = await scope_service.list_active(
        db, names=tenant_allowed if tenant_allowed is not None else None
    )

    tenant_prefix = get_tenant_prefix()
    is_admin, admin_permissions = await check_user_is_admin(db, user)
    page_branding = await get_branding_for_request(db)

    return templates.TemplateResponse(
        request=request,
        name="auth/settings/org/clients/edit.html",
        context={
            "can": OrgPermissions(membership),
            "tenant": org_tenant_to_dict(tenant),
            "membership": membership,
            "client": _org_client_to_dict(client),
            "scope_groups": build_scope_groups_from_db(tenant_scopes),
            "tenant_prefix": tenant_prefix,
            "branding": page_branding,
            "is_admin": is_admin,
            "admin_permissions": admin_permissions,
        },
    )


@router.post("/org/{tenant_id}/clients/{client_uuid}/edit", response_class=RedirectResponse)
async def org_client_edit_submit(
    request: Request,
    tenant_id: str,
    client_uuid: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Process the OAuth2 client edit form submission.

    Updates all mutable client fields. Switching a client from public to
    confidential auto-generates a new secret (returned once via redirect);
    switching from confidential to public removes the stored secret hash.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `clients:write`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      -d "name=My+App&is_confidential=true&require_pkce=false" \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/clients/7c9e6679-7425-40de-944b-e07fc1f90ae7/edit
    ```
    """
    logger.debug("Org client edit submit: tenant=%s client=%s", tenant_id, client_uuid)

    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="clients:write"
    )

    client = await _get_org_client(db, client_uuid, tenant.id)
    form_data = await request.form()

    try:
        name = str(form_data.get("name", "")).strip()
        if not name:
            return org_redirect(
                tenant_id, f"/clients/{client_uuid}/edit", error="Client name is required"
            )

        client.name = name
        client.description = str(form_data.get("description", "")).strip() or None
        client.homepage_url = str(form_data.get("homepage_url", "")).strip() or None

        # Parse redirect URIs (newline-separated)
        raw_uris = str(form_data.get("redirect_uris", "")).strip()
        client.redirect_uris = [u.strip() for u in raw_uris.splitlines() if u.strip()]

        # Parse scopes (scope_ prefix checkboxes)
        client.allowed_scopes = [
            key.removeprefix("scope_") for key in form_data if key.startswith("scope_")
        ]

        # Parse grant types (grant_ prefix checkboxes)
        client.allowed_grant_types = [
            key.removeprefix("grant_") for key in form_data if key.startswith("grant_")
        ]

        new_is_confidential = form_data.get("is_confidential") == "true"
        client.require_pkce = form_data.get("require_pkce") == "true"
        client.require_consent = form_data.get("require_consent") == "true"

        # Token expiry
        access_expiry = str(form_data.get("access_token_expiry_seconds", "")).strip()
        client.access_token_expiry_seconds = int(access_expiry) if access_expiry else None
        refresh_expiry = str(form_data.get("refresh_token_expiry_seconds", "")).strip()
        client.refresh_token_expiry_seconds = int(refresh_expiry) if refresh_expiry else None

        # Allowed origins (newline-separated)
        raw_origins = str(form_data.get("allowed_origins", "")).strip()
        client.allowed_origins = [o.strip() for o in raw_origins.splitlines() if o.strip()] or None

        # Handle confidential/public type change
        new_secret = None
        if new_is_confidential and not client.is_confidential:
            # Switching from public to confidential: generate new secret
            new_secret = _generate_client_secret()
            client.client_secret_hash = hash_password(new_secret)
            client.token_endpoint_auth_method = "client_secret_basic"
        elif not new_is_confidential and client.is_confidential:
            # Switching from confidential to public: remove secret
            client.client_secret_hash = None
            client.token_endpoint_auth_method = "none"
        client.is_confidential = new_is_confidential

        await db.commit()
        logger.info("Updated org OAuth2 client %s for tenant=%s", client_uuid, tenant_id)

        redirect_kwargs: dict = {"success": "Client updated successfully"}
        if new_secret:
            redirect_kwargs["new_secret"] = new_secret

        return org_redirect(tenant_id, f"/clients/{client_uuid}", **redirect_kwargs)
    except Exception as e:
        logger.error("Failed to update org OAuth2 client: %s", e)
        return org_redirect(tenant_id, f"/clients/{client_uuid}/edit", error=str(e))


@router.post("/org/{tenant_id}/clients/{client_uuid}/disable", response_class=RedirectResponse)
async def org_client_disable(
    request: Request,
    tenant_id: str,
    client_uuid: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Disable an OAuth2 client, blocking all new token issuance.

    Sets `is_active = False` on the client. Existing tokens continue to be
    accepted until they expire, but the client cannot obtain new ones via any
    grant type. Re-enable with `POST /clients/{uuid}/enable`.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `clients:write`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/clients/7c9e6679-7425-40de-944b-e07fc1f90ae7/disable
    ```
    """
    logger.debug("Org client disable: tenant=%s client=%s", tenant_id, client_uuid)

    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="clients:write"
    )

    client = await _get_org_client(db, client_uuid, tenant.id)
    client.is_active = False
    await db.commit()
    logger.info("Disabled org OAuth2 client %s for tenant=%s", client_uuid, tenant_id)

    return org_redirect(tenant_id, "/clients", success="Client disabled")


@router.post("/org/{tenant_id}/clients/{client_uuid}/enable", response_class=RedirectResponse)
async def org_client_enable(
    request: Request,
    tenant_id: str,
    client_uuid: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Re-enable a previously disabled OAuth2 client.

    Sets `is_active = True`, restoring the client's ability to request tokens
    via configured grant types. Has no effect if the client is already active.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `clients:write`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/clients/7c9e6679-7425-40de-944b-e07fc1f90ae7/enable
    ```
    """
    logger.debug("Org client enable: tenant=%s client=%s", tenant_id, client_uuid)

    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="clients:write"
    )

    client = await _get_org_client(db, client_uuid, tenant.id)
    client.is_active = True
    await db.commit()
    logger.info("Enabled org OAuth2 client %s for tenant=%s", client_uuid, tenant_id)

    return org_redirect(tenant_id, "/clients", success="Client enabled")


@router.post(
    "/org/{tenant_id}/clients/{client_uuid}/rotate-secret",
    response_class=RedirectResponse,
)
async def org_client_rotate_secret(
    request: Request,
    tenant_id: str,
    client_uuid: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Rotate the client secret for a confidential OAuth2 client.

    Generates a new cryptographically random secret, stores its bcrypt hash, and
    returns the plaintext once via the redirect's `new_secret` query param. The
    old secret is immediately invalidated. Not applicable to public clients.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `clients:rotate`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/clients/7c9e6679-7425-40de-944b-e07fc1f90ae7/rotate-secret
    ```
    """
    logger.debug("Org client rotate secret: tenant=%s client=%s", tenant_id, client_uuid)

    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="clients:rotate"
    )

    client = await _get_org_client(db, client_uuid, tenant.id)

    if not client.is_confidential:
        return org_redirect(
            tenant_id,
            f"/clients/{client_uuid}",
            error="Cannot rotate secret for a public client",
        )

    new_secret = _generate_client_secret()
    client.client_secret_hash = hash_password(new_secret)
    await db.commit()
    logger.info("Rotated secret for org OAuth2 client %s tenant=%s", client_uuid, tenant_id)

    return org_redirect(
        tenant_id, f"/clients/{client_uuid}", success="Secret rotated", new_secret=new_secret
    )


@router.post("/org/{tenant_id}/clients/{client_uuid}/delete", response_class=RedirectResponse)
async def org_client_delete(
    request: Request,
    tenant_id: str,
    client_uuid: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Permanently delete an OAuth2 client from the organisation.

    Removes the `OAuth2Client` record and dispatches a `client.deleted` webhook
    event. All existing tokens issued to this client become unusable on next
    validation. This action is irreversible.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `clients:delete`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/clients/7c9e6679-7425-40de-944b-e07fc1f90ae7/delete
    ```
    """
    logger.debug("Org client delete: tenant=%s client=%s", tenant_id, client_uuid)

    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="clients:delete"
    )

    client = await _get_org_client(db, client_uuid, tenant.id)
    deleted_client_name = client.name
    deleted_client_id_value = client.client_id
    await _oauth2_client_service.delete(db, client)
    await db.flush()

    await _dispatch_tenant_event(
        db,
        tenant_id=tenant.id,
        event=WebhookEvent.CLIENT_DELETED,
        data={
            "tenant_id": str(tenant.id),
            "client_uuid": client_uuid,
            "client_id_value": deleted_client_id_value,
            "name": deleted_client_name,
            "actor_id": str(user.id),
        },
    )
    await db.commit()
    logger.info("Deleted org OAuth2 client %s for tenant=%s", client_uuid, tenant_id)

    return org_redirect(tenant_id, "/clients", success="Client deleted")


# Organization Templates Management Endpoints
# ============================================================================


@router.get("/org/{tenant_id}/templates", response_class=HTMLResponse)
async def org_templates_page(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> Response:
    """Render the Jinja2/MJML templates management page for org owners.

    Lists all customisable templates along with any active tenant-specific
    overrides. Templates not yet overridden fall back to the platform defaults.
    Provides Edit, Toggle, and Delete actions per template.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `templates:read`

    **Example:**
    ```
    curl -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/templates
    ```
    """
    logger.debug("Org templates page: tenant=%s", tenant_id)
    templates = get_templates()

    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="templates:read"
    )

    # Reload tenant with templates relationship
    reloaded = await tenant_service.get_by_id_with_templates(db, tenant.id)
    assert reloaded is not None
    tenant = reloaded

    success = request.query_params.get("success")
    error = request.query_params.get("error")
    tenant_prefix = get_tenant_prefix()

    # Get existing templates
    tenant_templates = [org_template_to_dict(t) for t in tenant.templates]
    tenant_templates.sort(key=lambda t: t["template_name"])

    # List of customizable templates
    customizable = BrandingService.CUSTOMIZABLE_TEMPLATES

    return templates.TemplateResponse(
        request=request,
        name="auth/settings/org/templates.html",
        context={
            "can": OrgPermissions(membership),
            "tenant": org_tenant_to_dict(tenant),
            "tenant_templates": tenant_templates,
            "customizable_templates": customizable,
            "success": success,
            "error": error,
            "tenant_prefix": tenant_prefix,
            "branding": await get_branding_for_request(db),
        },
    )


@router.get("/org/{tenant_id}/templates/{template_name:path}/edit", response_class=HTMLResponse)
async def org_template_edit_page(
    request: Request,
    tenant_id: str,
    template_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> Response:
    """Render the template editor for a specific customisable template.

    Loads the current tenant override content if one exists, otherwise shows
    the platform default content. Only templates in `BrandingService.CUSTOMIZABLE_TEMPLATES`
    can be edited. Supports both Jinja2 HTML and MJML email templates.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `templates:write`

    **Example:**
    ```
    curl -b cookies.txt \
      "https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/templates/auth/emails/welcome.mjml/edit"
    ```
    """
    logger.debug("Org template edit page: tenant=%s template=%s", tenant_id, template_name)
    templates = get_templates()

    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="templates:write"
    )

    # Check if template is customizable
    if template_name not in BrandingService.CUSTOMIZABLE_TEMPLATES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Template is not customizable",
        )

    # Get existing template if any
    tenant_template = await tenant_service.get_template(db, tenant.id, template_name)

    # Get default template content
    from pathlib import Path

    templates_dir = Path(__file__).parent.parent.parent.parent / "templates"
    default_path = templates_dir / template_name
    default_content = ""
    if default_path.exists():
        default_content = default_path.read_text(encoding="utf-8")

    success = request.query_params.get("success")
    error = request.query_params.get("error")
    tenant_prefix = get_tenant_prefix()

    return templates.TemplateResponse(
        request=request,
        name="auth/settings/org/template_edit.html",
        context={
            "can": OrgPermissions(membership),
            "tenant": org_tenant_to_dict(tenant),
            "template_name": template_name,
            "template": org_template_to_dict(tenant_template) if tenant_template else None,
            "default_content": default_content,
            "success": success,
            "error": error,
            "tenant_prefix": tenant_prefix,
            "branding": await get_branding_for_request(db),
        },
    )


@router.post(
    "/org/{tenant_id}/templates/{template_name:path}/edit", response_class=RedirectResponse
)
async def org_template_edit_submit(
    request: Request,
    tenant_id: str,
    template_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Save a custom template override for the organisation.

    Validates Jinja2 syntax (or MJML syntax for `.mjml` templates) before
    persisting. Creates the `TenantTemplate` record if it does not exist yet.
    Invalidates the email renderer cache for MJML templates. Redirects to the
    templates list on success.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `templates:write`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      -d "content=%7B%25+block+title+%25%7D...&is_active=true" \
      "https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/templates/auth/emails/welcome.mjml/edit"
    ```
    """
    logger.debug("Org template edit submit: tenant=%s template=%s", tenant_id, template_name)

    user, tenant, ownership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="templates:write"
    )

    # Check if template is customizable
    if template_name not in BrandingService.CUSTOMIZABLE_TEMPLATES:
        return org_redirect(tenant_id, "/templates", error="Template is not customizable")

    form_data = await request.form()

    content = str(form_data.get("content", "")).strip()
    description = str(form_data.get("description", "")).strip() or None
    is_active = form_data.get("is_active") == "true"

    if not content:
        return org_redirect(
            tenant_id, f"/templates/{template_name}/edit", error="Content is required"
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
        error_msg = f"Invalid {syntax_type} syntax: {str(e)[:50]}"
        return org_redirect(tenant_id, f"/templates/{template_name}/edit", error=error_msg)

    try:
        # Get or create template via the service (upsert semantics)
        await tenant_service.upsert_template(
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

        logger.info("User %s saved template %s for org %s", user.id, template_name, tenant_id)

        return org_redirect(tenant_id, "/templates", success="Template saved successfully")
    except Exception as e:
        logger.error("Failed to save template %s for org %s: %s", template_name, tenant_id, e)
        return org_redirect(tenant_id, f"/templates/{template_name}/edit", error=str(e))


@router.post(
    "/org/{tenant_id}/templates/{template_name:path}/delete", response_class=RedirectResponse
)
async def org_template_delete(
    request: Request,
    tenant_id: str,
    template_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Delete the tenant's custom template override, reverting to the platform default.

    Removes the `TenantTemplate` record so the base platform template is used
    again. If no override existed the operation is a no-op. Redirects to the
    templates list with feedback.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `templates:write`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      "https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/templates/auth/emails/welcome.mjml/delete"
    ```
    """
    logger.debug("Org template delete: tenant=%s template=%s", tenant_id, template_name)

    user, tenant, ownership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="templates:write"
    )

    tenant_template = await tenant_service.get_template(db, tenant.id, template_name)

    if tenant_template:
        await tenant_service.delete_template(db, tenant_template)
        await db.commit()
        logger.info("User %s deleted template %s for org %s", user.id, template_name, tenant_id)

    return org_redirect(tenant_id, "/templates", success="Template deleted (reverted to default)")


@router.post(
    "/org/{tenant_id}/templates/{template_name:path}/toggle", response_class=RedirectResponse
)
async def org_template_toggle(
    request: Request,
    tenant_id: str,
    template_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Toggle a custom template's active status.

    Flips `is_active` on the `TenantTemplate` record. When inactive, the
    platform default template is used even though a custom override exists.
    Useful for previewing or disabling a template without deleting it.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `templates:write`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      "https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/templates/auth/emails/welcome.mjml/toggle"
    ```
    """
    logger.debug("Org template toggle: tenant=%s template=%s", tenant_id, template_name)

    user, tenant, ownership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="templates:write"
    )

    tenant_template = await tenant_service.get_template(db, tenant.id, template_name)

    if not tenant_template:
        return org_redirect(tenant_id, "/templates", error="Template not found")

    await tenant_service.toggle_template(db, tenant_template)
    await db.commit()

    action = "enabled" if tenant_template.is_active else "disabled"
    logger.info("User %s %s template %s for org %s", user.id, action, template_name, tenant_id)

    return org_redirect(tenant_id, "/templates", success=f"Template {action}")


# =============================================================================
# Trust Policy Management
# =============================================================================


def trust_source_to_dict(source: TenantTrustedSource) -> dict:
    """Convert TenantTrustedSource to dictionary for templates."""
    return {
        "id": str(source.id),
        "trusted_tenant_id": str(source.trusted_tenant_id) if source.trusted_tenant_id else None,
        "trusted_tenant_name": source.trusted_tenant.display_name
        if source.trusted_tenant
        else "Main Domain",
        "trusted_tenant_slug": source.trusted_tenant.slug if source.trusted_tenant else None,
        "description": source.description,
        "created_at": source.created_at.isoformat() if source.created_at else None,
    }


@router.get("/org/{tenant_id}/trust", response_class=HTMLResponse)
async def org_trust_page(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    trust_service: Annotated[TrustPolicyService, Depends(get_trust_service)],
) -> Response:
    """Render the trust policy management page for org owners.

    Displays the current trust mode (none/allowlist/open) and the list of
    trusted source organisations. Also shows available organisations that can
    be added as trusted sources. Changes take effect immediately for new
    token-exchange and federation requests.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `trust:read`

    **Example:**
    ```
    curl -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/trust
    ```
    """
    logger.debug("Org trust page requested: tenant=%s", tenant_id)

    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="trust:read"
    )

    # Get trust configuration
    trust_config = await trust_service.get_tenant_trust_config(db, tenant.id)

    # Get available tenants for adding as trusted sources
    available_tenants = await trust_service.get_available_tenants_for_trust(db, tenant.id)

    success = request.query_params.get("success")
    error = request.query_params.get("error")

    is_admin, admin_permissions = await check_user_is_admin(db, user)
    branding = await get_branding_for_request(db)
    tenant_prefix = get_tenant_prefix()

    templates = get_templates()
    return templates.TemplateResponse(
        request=request,
        name="auth/settings/org/trust.html",
        context={
            "can": OrgPermissions(membership),
            "active_section": "tenants",
            "tenant": org_tenant_to_dict(tenant),
            "trust_mode": trust_config["trust_mode"] if trust_config else "none",
            "trust_modes": [m.value for m in TenantTrustMode],
            "trusted_sources": trust_config["trusted_sources"] if trust_config else [],
            "available_tenants": available_tenants,
            "success": success,
            "error": error,
            "is_admin": is_admin,
            "admin_permissions": admin_permissions,
            "branding": branding,
            "tenant_prefix": tenant_prefix,
        },
    )


@router.post("/org/{tenant_id}/trust/mode", response_class=RedirectResponse)
async def org_trust_mode_submit(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    trust_service: Annotated[TrustPolicyService, Depends(get_trust_service)],
) -> RedirectResponse:
    """Update the trust mode for the organisation.

    Sets the `TenantTrustMode` to one of `none`, `allowlist`, or `open`. In
    `none` mode all cross-tenant token exchanges are rejected; in `allowlist`
    only trusted sources are accepted; in `open` any organisation is trusted.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `trust:write`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      -d "trust_mode=allowlist" \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/trust/mode
    ```
    """
    logger.debug("Org trust mode submit: tenant=%s", tenant_id)

    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="trust:write"
    )

    form_data = await request.form()
    trust_mode_str = str(form_data.get("trust_mode", "none"))

    try:
        trust_mode = TenantTrustMode(str(trust_mode_str))
    except ValueError:
        return org_redirect(tenant_id, "/trust", error="Invalid trust mode")

    await trust_service.update_trust_mode(db, tenant.id, trust_mode)
    await db.commit()

    logger.info("User %s updated trust mode for org %s to %s", user.id, tenant_id, trust_mode.value)

    return org_redirect(tenant_id, "/trust", success=f"Trust mode updated to {trust_mode.value}")


@router.post("/org/{tenant_id}/trust/add-source", response_class=RedirectResponse)
async def org_trust_add_source_submit(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    trust_service: Annotated[TrustPolicyService, Depends(get_trust_service)],
) -> RedirectResponse:
    """Add a trusted source organisation to the allowlist.

    Creates a `TenantTrustedSource` record linking `trusted_tenant_id` as a
    trusted federation source. Returns an error if the source is already in
    the allowlist. Has no effect when trust mode is `none` or `open` — only
    meaningful in `allowlist` mode.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `trust:write`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      -d "trusted_tenant_id=7c9e6679-7425-40de-944b-e07fc1f90ae7&description=Partner+org" \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/trust/add-source
    ```
    """
    logger.debug("Org trust add source: tenant=%s", tenant_id)

    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="trust:write"
    )

    form_data = await request.form()
    trusted_tenant_id_str = str(form_data.get("trusted_tenant_id", ""))
    description = str(form_data.get("description", "")).strip() or None

    if not trusted_tenant_id_str:
        return org_redirect(tenant_id, "/trust", error="Please select an organization")

    try:
        trusted_tenant_id = uuid.UUID(str(trusted_tenant_id_str))
    except ValueError:
        return org_redirect(tenant_id, "/trust", error="Invalid organization ID")

    source = await trust_service.add_trusted_source(db, tenant.id, trusted_tenant_id, description)

    if not source:
        return org_redirect(tenant_id, "/trust", error="This organization is already trusted")

    await db.commit()

    logger.info(
        "User %s added trusted source %s to org %s", user.id, trusted_tenant_id_str, tenant_id
    )

    return org_redirect(tenant_id, "/trust", success="Trusted source added")


@router.post("/org/{tenant_id}/trust/remove-source/{source_id}", response_class=RedirectResponse)
async def org_trust_remove_source_submit(
    request: Request,
    tenant_id: str,
    source_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    trust_service: Annotated[TrustPolicyService, Depends(get_trust_service)],
) -> RedirectResponse:
    """Remove a trusted source organisation from the allowlist.

    Deletes the `TenantTrustedSource` record identified by `source_id`. After
    removal, token exchanges from the removed source organisation are rejected
    (when trust mode is `allowlist`). Returns 404 via redirect if not found.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `trust:write`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/trust/remove-source/7c9e6679-7425-40de-944b-e07fc1f90ae7
    ```
    """
    logger.debug("Org trust remove source: tenant=%s source=%s", tenant_id, source_id)

    user, tenant, membership = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="trust:write"
    )

    try:
        source_uuid = uuid.UUID(source_id)
    except ValueError:
        return org_redirect(tenant_id, "/trust", error="Invalid source ID")

    removed = await trust_service.remove_trusted_source(db, tenant.id, source_uuid)

    if not removed:
        return org_redirect(tenant_id, "/trust", error="Trusted source not found")

    await db.commit()

    logger.info("User %s removed trusted source %s from org %s", user.id, source_id, tenant_id)

    return org_redirect(tenant_id, "/trust", success="Trusted source removed")


# =============================================================================
# Outbound tenant webhooks
# =============================================================================

_VALID_EVENT_VALUES: set[str] = {e.value for e in WebhookEvent}


async def _dispatch_tenant_event(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    event: WebhookEvent,
    data: dict,
) -> None:
    """Enqueue a webhook dispatch; never raises into the caller.

    Webhook configuration issues (bad URL, dead host, etc.) must not break
    the underlying business action. We log and swallow here so the caller
    can proceed to commit.
    """
    try:
        await webhook_service.dispatch(db, tenant_id=tenant_id, event=event.value, data=data)
    except Exception:  # noqa: BLE001 - isolation is the point
        logger.exception(
            "Failed to enqueue webhook dispatch (tenant=%s, event=%s)",
            tenant_id,
            event.value,
        )


def _sanitize_events(selected: list[str]) -> list[str]:
    """Keep only event strings that are real WebhookEvent values, group
    wildcards like ``user.*`` built from a real prefix, or the global ``*``.
    """
    groups = {e.value.split(".", 1)[0] for e in WebhookEvent}
    out: list[str] = []
    seen: set[str] = set()
    for raw in selected:
        value = raw.strip()
        if not value or value in seen:
            continue
        if value == "*":
            out.append(value)
            seen.add(value)
            continue
        if value in _VALID_EVENT_VALUES:
            out.append(value)
            seen.add(value)
            continue
        if value.endswith(".*"):
            prefix = value[:-2]
            if prefix in groups or any(e.value.startswith(prefix + ".") for e in WebhookEvent):
                out.append(value)
                seen.add(value)
    return out


async def _get_tenant_webhook(
    db: AsyncSession, tenant_id: uuid.UUID, webhook_id: str
) -> TenantWebhook | None:
    try:
        webhook_uuid = uuid.UUID(webhook_id)
    except ValueError:
        return None
    return await webhook_service.get_for_tenant(db, tenant_id=tenant_id, webhook_id=webhook_uuid)


@router.post("/org/{tenant_id}/webhooks/create", response_class=RedirectResponse)
async def org_webhook_create_submit(
    request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Create a new outbound webhook subscription for the organisation.

    Validates the target URL (must be HTTPS, not a private/loopback address) and
    the selected event list. Generates an HMAC signing secret and returns it
    once via the `new_webhook_secret` redirect query parameter — it is never
    retrievable again. Requires `webhooks:write` membership scope.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `webhooks:write`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      -d "name=My+Webhook&url=https%3A%2F%2Fhooks.example.com%2Fauth&events=user.created" \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/webhooks/create
    ```
    """
    user, tenant, _ = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="webhooks:write"
    )

    form = await request.form()
    name = str(form.get("name", "")).strip()
    url = str(form.get("url", "")).strip()
    events = _sanitize_events([str(v) for v in form.getlist("events")])

    if not name:
        return org_redirect(tenant_id, "", error="Webhook name is required")
    if len(name) > 100:
        return org_redirect(tenant_id, "", error="Webhook name must be <= 100 characters")
    if not url:
        return org_redirect(tenant_id, "", error="Webhook URL is required")
    if not events:
        return org_redirect(tenant_id, "", error="Select at least one event to subscribe to")

    try:
        webhook_validate_target_url(url)
    except WebhookURLError as e:
        return org_redirect(tenant_id, "", error=f"Invalid webhook URL: {e}")

    secret = webhook_generate_secret()
    webhook = await webhook_service.create_for_tenant(
        db,
        tenant_id=tenant.id,
        name=name,
        url=url,
        events=events,
        secret=secret,
        headers={},
        is_active=True,
    )
    await db.commit()

    logger.info("User %s created webhook %s for org %s", user.id, webhook.id, tenant_id)
    return org_redirect(
        tenant_id,
        "",
        success="Webhook created",
        new_webhook_id=str(webhook.id),
        new_webhook_secret=secret,
    )


@router.post("/org/{tenant_id}/webhooks/{webhook_id}/update", response_class=RedirectResponse)
async def org_webhook_update_submit(
    request: Request,
    tenant_id: str,
    webhook_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Update a webhook's name, URL, and subscribed event list.

    Validates the new URL before saving. At least one event must be selected.
    The HMAC signing secret is not affected by this operation; rotate it
    separately with the rotate-secret endpoint.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `webhooks:write`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      -d "name=Updated+Hook&url=https%3A%2F%2Fhooks.example.com%2Fv2&events=user.*" \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/webhooks/7c9e6679-7425-40de-944b-e07fc1f90ae7/update
    ```
    """
    user, tenant, _ = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="webhooks:write"
    )
    webhook = await _get_tenant_webhook(db, tenant.id, webhook_id)
    if not webhook:
        return org_redirect(tenant_id, "", error="Webhook not found")

    form = await request.form()
    name = str(form.get("name", "")).strip()
    url = str(form.get("url", "")).strip()
    events = _sanitize_events([str(v) for v in form.getlist("events")])

    if not name or len(name) > 100:
        return org_redirect(tenant_id, "", error="Invalid webhook name")
    if not url:
        return org_redirect(tenant_id, "", error="Webhook URL is required")
    if not events:
        return org_redirect(tenant_id, "", error="Select at least one event")
    try:
        webhook_validate_target_url(url)
    except WebhookURLError as e:
        return org_redirect(tenant_id, "", error=f"Invalid webhook URL: {e}")

    webhook.name = name
    webhook.url = url
    webhook.events = events
    await db.commit()

    logger.info("User %s updated webhook %s in org %s", user.id, webhook.id, tenant_id)
    return org_redirect(tenant_id, "", success="Webhook updated")


@router.post("/org/{tenant_id}/webhooks/{webhook_id}/toggle", response_class=RedirectResponse)
async def org_webhook_toggle(
    request: Request,
    tenant_id: str,
    webhook_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Pause or resume a webhook by toggling its active flag.

    When paused (`is_active = False`), no new deliveries are enqueued for this
    webhook until it is resumed. Existing pending deliveries are not affected.
    The current state is reflected in the org detail page webhook list.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `webhooks:write`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/webhooks/7c9e6679-7425-40de-944b-e07fc1f90ae7/toggle
    ```
    """
    user, tenant, _ = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="webhooks:write"
    )
    webhook = await _get_tenant_webhook(db, tenant.id, webhook_id)
    if not webhook:
        return org_redirect(tenant_id, "", error="Webhook not found")

    webhook.is_active = not webhook.is_active
    await db.commit()

    action = "resumed" if webhook.is_active else "paused"
    logger.info("User %s %s webhook %s in org %s", user.id, action, webhook.id, tenant_id)
    return org_redirect(tenant_id, "", success=f"Webhook {action}")


@router.post(
    "/org/{tenant_id}/webhooks/{webhook_id}/rotate-secret", response_class=RedirectResponse
)
async def org_webhook_rotate_secret(
    request: Request,
    tenant_id: str,
    webhook_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Rotate the HMAC signing secret for a webhook.

    Generates a new signing secret and returns it once via the
    `new_webhook_secret` redirect query parameter. The previous secret is
    immediately invalidated — update your endpoint's signature verification
    before rotating. Requires `webhooks:write` membership scope.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `webhooks:write`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/webhooks/7c9e6679-7425-40de-944b-e07fc1f90ae7/rotate-secret
    ```
    """
    user, tenant, _ = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="webhooks:write"
    )
    webhook = await _get_tenant_webhook(db, tenant.id, webhook_id)
    if not webhook:
        return org_redirect(tenant_id, "", error="Webhook not found")

    new_secret = webhook_generate_secret()
    webhook.secret = new_secret
    await db.commit()

    logger.info("User %s rotated secret for webhook %s in org %s", user.id, webhook.id, tenant_id)
    return org_redirect(
        tenant_id,
        "",
        success="Webhook secret rotated",
        new_webhook_id=str(webhook.id),
        new_webhook_secret=new_secret,
    )


@router.post("/org/{tenant_id}/webhooks/{webhook_id}/test", response_class=RedirectResponse)
async def org_webhook_test(
    request: Request,
    tenant_id: str,
    webhook_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Send a test ping through the webhook delivery pipeline.

    Creates a synthetic `webhook.test` delivery row targeting this webhook only
    — not the full subscription fan-out — so the operator can verify their
    endpoint is reachable regardless of their event subscription list. The
    delivery is dispatched asynchronously via Celery; check the delivery log in
    the org detail page for the result.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `webhooks:write`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/webhooks/7c9e6679-7425-40de-944b-e07fc1f90ae7/test
    ```
    """
    user, tenant, _ = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="webhooks:write"
    )
    webhook = await _get_tenant_webhook(db, tenant.id, webhook_id)
    if not webhook:
        return org_redirect(tenant_id, "", error="Webhook not found")

    try:
        webhook_validate_target_url(webhook.url)
    except WebhookURLError as e:
        return org_redirect(tenant_id, "", error=f"Cannot test: {e}")

    await webhook_service.create_test_delivery(db, webhook=webhook, triggered_by=user.id)
    await db.commit()

    logger.info("User %s pinged webhook %s in org %s", user.id, webhook.id, tenant_id)
    return org_redirect(tenant_id, "", success="Test delivery sent")


@router.post("/org/{tenant_id}/webhooks/{webhook_id}/delete", response_class=RedirectResponse)
async def org_webhook_delete(
    request: Request,
    tenant_id: str,
    webhook_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Permanently delete a webhook and cascade-delete all its delivery records.

    Removes the `TenantWebhook` row and all associated `WebhookDelivery` rows.
    This action is irreversible. The signing secret is also purged. Requires
    `webhooks:delete` membership scope.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `webhooks:delete`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/webhooks/7c9e6679-7425-40de-944b-e07fc1f90ae7/delete
    ```
    """
    user, tenant, _ = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="webhooks:delete"
    )
    webhook = await _get_tenant_webhook(db, tenant.id, webhook_id)
    if not webhook:
        return org_redirect(tenant_id, "", error="Webhook not found")

    await webhook_service.delete(db, webhook)
    await db.commit()

    logger.info("User %s deleted webhook %s from org %s", user.id, webhook_id, tenant_id)
    return org_redirect(tenant_id, "", success="Webhook deleted")


@router.post(
    "/org/{tenant_id}/webhooks/{webhook_id}/deliveries/{delivery_id}/replay",
    response_class=RedirectResponse,
)
async def org_webhook_replay_delivery(
    request: Request,
    tenant_id: str,
    webhook_id: str,
    delivery_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> RedirectResponse:
    """Replay a previous webhook delivery by cloning it into a new delivery row.

    Copies the original envelope with a fresh delivery ID and timestamp, creates
    a new `WebhookDelivery` record with `PENDING` status, and dispatches it via
    the Celery delivery task. The original delivery is left untouched. Useful
    for retrying failed deliveries without waiting for automatic retry backoff.

    **Specification:** RFC 6265 (session cookie)

    **Authentication:** session cookie + org membership + `webhooks:write`

    **Example:**
    ```
    curl -X POST -b cookies.txt \
      https://auth.example.com/auth/settings/org/550e8400-e29b-41d4-a716-446655440000/webhooks/7c9e6679-7425-40de-944b-e07fc1f90ae7/deliveries/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/replay
    ```
    """
    user, tenant, _ = await require_tenant_manager(
        request, tenant_id, db, session_service, required_scope="webhooks:write"
    )
    webhook = await _get_tenant_webhook(db, tenant.id, webhook_id)
    if not webhook:
        return org_redirect(tenant_id, "", error="Webhook not found")

    try:
        delivery_uuid = uuid.UUID(delivery_id)
    except ValueError:
        return org_redirect(tenant_id, "", error="Invalid delivery id")

    original = await webhook_service.get_delivery_for_webhook(
        db, webhook_id=webhook.id, delivery_id=delivery_uuid
    )
    if not original:
        return org_redirect(tenant_id, "", error="Delivery not found")

    replay = await webhook_service.replay_delivery(db, webhook=webhook, original=original)
    await db.commit()

    logger.info(
        "User %s replayed delivery %s (new=%s) for webhook %s",
        user.id,
        delivery_id,
        replay.id,
        webhook.id,
    )
    return org_redirect(tenant_id, "", success="Delivery replayed")


# Silence ``unused`` import warnings if the webhook_service is only referenced
# indirectly via tests.
_ = webhook_service
