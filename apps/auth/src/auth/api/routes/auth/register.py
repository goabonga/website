# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""User registration endpoint."""

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import (
    get_branding_service,
    get_db,
    get_email_service,
    get_profile_service,
    get_user_service,
)
from auth.api.schemas.auth import ProfileFields, RegisterRequest, RegisterResponse
from auth.config import settings
from auth.db.models.tenant import WebhookEvent
from auth.middlewares.tenant import get_tenant_context
from auth.services.branding import BrandingService
from auth.services.email import EmailService
from auth.services.profile import ProfileData, ProfileService
from auth.services.tenant import tenant_service
from auth.services.upload import UploadError, upload_service
from auth.services.user import UserService
from auth.services.webhook import safe_dispatch as dispatch_webhook_event

logger = logging.getLogger(__name__)

router = APIRouter()


def get_tenant_prefix() -> str:
    """Get the URL prefix for the current tenant if resolved via path.

    Returns:
        The tenant prefix (e.g., '/t/knowledge') if using path resolution,
        or empty string otherwise.
    """
    tenant_ctx = get_tenant_context()
    if tenant_ctx and tenant_ctx.tenant_slug and tenant_ctx.resolution_method == "path":
        return f"/t/{tenant_ctx.tenant_slug}"
    return ""


def get_current_tenant_id():
    """Get the current tenant ID from context."""
    tenant_ctx = get_tenant_context()
    return tenant_ctx.tenant_id if tenant_ctx else None


# Default: all fields visible
DEFAULT_REGISTRATION_FIELDS = {
    "profile": True,
    "nickname": True,
    "firstname": True,
    "lastname": True,
    "middle_name": True,
    "preferred_username": True,
    "personal_details": True,
    "gender": True,
    "birthdate": True,
    "locale": True,
    "zoneinfo": True,
    "phone_number": True,
    "address": True,
    "picture": True,
    "web_presence": True,
}


async def get_registration_fields(db: AsyncSession, tenant_id) -> dict[str, bool]:
    """Load registration field visibility config from tenant settings."""
    if not tenant_id:
        return dict(DEFAULT_REGISTRATION_FIELDS)

    import uuid as uuid_mod

    tid = tenant_id if isinstance(tenant_id, uuid_mod.UUID) else uuid_mod.UUID(str(tenant_id))
    tenant_settings = await tenant_service.get_settings(db, tid)

    if not tenant_settings or not isinstance(tenant_settings, dict):
        return dict(DEFAULT_REGISTRATION_FIELDS)

    overrides = tenant_settings.get("registration_fields", {})
    fields = dict(DEFAULT_REGISTRATION_FIELDS)
    for key in fields:
        if key in overrides:
            fields[key] = bool(overrides[key])
    return fields


@router.get("/register", response_class=HTMLResponse)
async def register_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    branding_service: BrandingService = Depends(get_branding_service),
    next: str = "",
    email: str = "",
) -> HTMLResponse:
    """Render the self-registration HTML form.

    Returns the registration page rendered with tenant-aware branding. When a
    tenant is resolved (via path prefix or subdomain), the form reflects that
    tenant's `registration_fields` configuration, hiding or showing optional
    profile fields accordingly. Pre-fills the email field if the `email` query
    parameter is supplied (e.g., after a failed attempt). No session or token
    is required to access this page.

    **Authentication:** none (public registration form)

    **Example:**
    ```
    curl https://auth.example.com/auth/register
    ```
    """
    logger.debug("Registration form requested")
    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()
    reg_fields = await get_registration_fields(db, tenant_id)
    html = await branding_service.render_template(
        db,
        "auth/register.html",
        {
            "request": request,
            "error": None,
            "next": next,
            "email": email,
            "tenant_prefix": tenant_prefix,
            "reg_fields": reg_fields,
        },
        tenant_id=tenant_id,
    )
    return HTMLResponse(content=html)


@router.post("/register", response_class=HTMLResponse, response_model=None)
async def register_submit(
    request: Request,
    # Credentials
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    # Required profile fields
    nickname: str = Form(...),
    firstname: str = Form(...),
    lastname: str = Form(...),
    # Optional profile fields
    middle_name: str | None = Form(None),
    preferred_username: str | None = Form(None),
    profile_url: str | None = Form(None),
    picture_url: str | None = Form(None),
    website: str | None = Form(None),
    gender: str | None = Form(None),
    birthdate: str | None = Form(None),
    zoneinfo: str | None = Form(None),
    locale: str | None = Form(None),
    # Address fields
    address_street: str | None = Form(None),
    address_locality: str | None = Form(None),
    address_region: str | None = Form(None),
    address_postal_code: str | None = Form(None),
    address_country: str | None = Form(None),
    # Phone
    phone_number: str | None = Form(None),
    # Avatar upload
    avatar: UploadFile | None = File(None),
    # Navigation
    next: str = Form(""),
    # Dependencies
    db: AsyncSession = Depends(get_db),
    user_service: UserService = Depends(get_user_service),
    email_service: EmailService = Depends(get_email_service),
    branding_service: BrandingService = Depends(get_branding_service),
    profile_service: ProfileService = Depends(get_profile_service),
) -> HTMLResponse | RedirectResponse:
    """Process the self-registration form and create a new user account.

    Validates the submitted credentials and optional OIDC profile fields
    against the tenant's `registration_fields` policy. Passwords are confirmed
    client-side and then hashed with Argon2 before storage, in accordance with
    **NIST SP 800-63B** credential storage requirements. On duplicate email or
    validation failure the form is re-rendered with an inline error (HTTP 400).
    On success, a verification email is dispatched asynchronously via Celery
    and the browser is redirected (HTTP 303) to `/auth/verify-email`; the
    session cookie is established only after the user completes email
    verification. If the request is tenant-scoped, the new account is
    associated with that tenant and receives its default role.

    **Specification:**
    - **RFC 6265** — session cookie is set by the downstream `/auth/verify-email`
      handler once the email token is consumed, not by this endpoint directly.
    - **NIST SP 800-63B §5.1.1** — passwords are hashed with Argon2 (or bcrypt
      as fallback) before persistence; plaintext passwords are never stored.

    **Authentication:** none (creates the user; session established after email verification)

    **Responses:**
    - `303` — registration accepted; redirect to email-verification page
    - `400` — validation error or duplicate email (form re-rendered with error)

    **Example:**
    ```
    curl -X POST -c cookies.txt \\
      -d "email=new@example.com" \\
      -d "password=S3cret!" \\
      -d "password_confirm=S3cret!" \\
      -d "nickname=jdoe" \\
      -d "firstname=Jane" \\
      -d "lastname=Doe" \\
      -d "csrf_token=<token>" \\
      https://auth.example.com/auth/register -L
    ```
    """
    logger.info("Registration attempt for email=%s", email)
    logger.debug("Registration form submitted: email=%s", email)
    tenant_prefix = get_tenant_prefix()
    tenant_id = get_current_tenant_id()
    reg_fields = await get_registration_fields(db, tenant_id)
    error = None

    # Build form data dict for template context preservation
    form_data = {
        "email": email,
        "nickname": nickname,
        "firstname": firstname,
        "lastname": lastname,
        "middle_name": middle_name,
        "preferred_username": preferred_username,
        "profile_url": profile_url,
        "picture_url": picture_url,
        "website": website,
        "gender": gender,
        "birthdate": birthdate,
        "zoneinfo": zoneinfo,
        "locale": locale,
        "address_street": address_street,
        "address_locality": address_locality,
        "address_region": address_region,
        "address_postal_code": address_postal_code,
        "address_country": address_country,
        "phone_number": phone_number,
        "next": next,
        "tenant_prefix": tenant_prefix,
        "reg_fields": reg_fields,
    }

    # Validate password confirmation
    if password != password_confirm:
        logger.debug("Registration validation failed: passwords do not match for email=%s", email)
        error = "Passwords do not match"
    else:
        # Validate using schema
        try:
            profile = ProfileFields(
                nickname=nickname,
                firstname=firstname,
                lastname=lastname,
                middle_name=middle_name,
                preferred_username=preferred_username,
                profile_url=profile_url,
                picture_url=picture_url,
                website=website,
                gender=gender,
                birthdate=birthdate,
                zoneinfo=zoneinfo,
                locale=locale,
                address_street=address_street,
                address_locality=address_locality,
                address_region=address_region,
                address_postal_code=address_postal_code,
                address_country=address_country,
                phone_number=phone_number,
            )
            RegisterRequest(email=email, password=password, profile=profile)
        except ValueError as e:
            logger.debug("Registration validation failed: %s for email=%s", e, email)
            error = str(e)

    if error:
        logger.warning("Registration failed: %s for email=%s", error, email)
        html = await branding_service.render_template(
            db,
            "auth/register.html",
            {"request": request, "error": error, **form_data},
            tenant_id=tenant_id,
        )
        return HTMLResponse(content=html, status_code=status.HTTP_400_BAD_REQUEST)

    # Create user with profile data and registration source
    try:
        profile_data = profile.to_profile_dict()
        # Get client IP and user agent for tracking
        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

        user = await user_service.create_user(
            db,
            email,
            password,
            profile_data=profile_data,
            registration_source="direct",  # Direct registration via auth UI
            registration_tenant_id=tenant_id,
            registration_ip=client_ip,
            registration_user_agent=user_agent,
        )
    except ValueError as e:
        logger.warning("Registration failed: user creation error: %s for email=%s", e, email)
        html = await branding_service.render_template(
            db,
            "auth/register.html",
            {"request": request, "error": str(e), **form_data},
            tenant_id=tenant_id,
        )
        return HTMLResponse(content=html, status_code=status.HTTP_400_BAD_REQUEST)

    logger.info("ACTION: user_register, user_id=%s, email=%s", user.id, email)

    await dispatch_webhook_event(
        db,
        tenant_id=tenant_id,
        event=WebhookEvent.USER_CREATED,
        data={
            "user_id": str(user.id),
            "email": email,
            "registration_source": "direct",
            "tenant_id": str(tenant_id) if tenant_id else None,
        },
    )
    await db.commit()

    # Handle avatar upload if provided
    if avatar and avatar.filename:
        try:
            relative_path = await upload_service.save_avatar(avatar, user.id)
            avatar_url = upload_service.get_avatar_url(relative_path)
            profile_data_update = ProfileData(picture_url=avatar_url)
            await profile_service.update_profile(db, str(user.id), profile_data_update)
            await db.commit()
            logger.info(
                "Avatar uploaded during registration for user_id=%s: %s", user.id, avatar_url
            )
        except UploadError as e:
            logger.warning(
                "Avatar upload failed during registration for user_id=%s: %s", user.id, str(e)
            )
            # Continue without avatar - don't fail registration

    logger.debug("Sending verification email to %s", email)

    # Send verification email with link
    base_url = str(request.base_url).rstrip("/")
    tenant_id = get_current_tenant_id()
    await email_service.send_verification_email(
        db,
        str(user.id),
        email,
        base_url=base_url,
        tenant_id=str(tenant_id) if tenant_id else None,
    )

    # Redirect to verify email page, preserving next parameter
    verify_params = {"email": email}
    if next:
        verify_params["next"] = next
    return RedirectResponse(
        url=f"{tenant_prefix}/auth/verify-email?{urlencode(verify_params)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/register/api", response_model=RegisterResponse)
async def register_api(
    request: Request,
    data: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    user_service: UserService = Depends(get_user_service),
    email_service: EmailService = Depends(get_email_service),
) -> RegisterResponse:
    """Register a new user account via the JSON API.

    Accepts a JSON body containing email, password, and an optional OIDC
    profile object. The password is hashed with Argon2 before storage per
    **NIST SP 800-63B §5.1.1**; plaintext passwords are never persisted.
    If the email is already registered a `400` error is returned. On success,
    a verification email is dispatched asynchronously via Celery using the
    server's configured issuer as the base URL, and a `RegisterResponse`
    payload is returned — no session cookie is issued by this endpoint.
    When a tenant context is active the new account is scoped to that tenant
    and assigned its default role; the `registration_source` field in the
    request body can carry the originating OAuth2 `client_id`.

    **Specification:**
    - **NIST SP 800-63B §5.1.1** — passwords are hashed with Argon2 before
      persistence; plaintext passwords are never stored.

    **Authentication:** none (creates the user; no session cookie issued)

    **Responses:**
    - `200` — user created; verification email dispatched
    - `400` — validation error or duplicate email

    **Example:**
    ```
    curl -X POST \\
      -H "Content-Type: application/json" \\
      -d '{"email": "new@example.com", "password": "S3cret!", "profile": {"nickname": "jdoe", "firstname": "Jane", "lastname": "Doe"}}' \\
      https://auth.example.com/auth/register/api
    ```
    """
    logger.info("API registration attempt for email=%s", data.email)
    logger.debug("API registration request: email=%s", data.email)

    # Extract registration source info
    reg_source = data.registration_source
    source = reg_source.source if reg_source else "api"
    client_id = reg_source.client_id if reg_source else None

    # Get tenant context if available
    tenant_id = get_current_tenant_id()

    # Get client IP and user agent
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    try:
        profile_data = data.profile.to_profile_dict()
        user = await user_service.create_user(
            db,
            data.email,
            data.password,
            profile_data=profile_data,
            registration_source=source,
            registration_client_id=client_id,
            registration_tenant_id=tenant_id,
            registration_ip=client_ip,
            registration_user_agent=user_agent,
        )
    except ValueError as e:
        logger.warning("API registration failed: %s for email=%s", e, data.email)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    logger.info("ACTION: user_register_api, user_id=%s, email=%s", user.id, data.email)

    await dispatch_webhook_event(
        db,
        tenant_id=tenant_id,
        event=WebhookEvent.USER_CREATED,
        data={
            "user_id": str(user.id),
            "email": data.email,
            "registration_source": source,
            "tenant_id": str(tenant_id) if tenant_id else None,
        },
    )
    await db.commit()

    logger.debug("Sending verification email to %s", data.email)

    # Send verification email with link (use issuer as base_url for API calls)
    tenant_id = get_current_tenant_id()
    await email_service.send_verification_email(
        db,
        str(user.id),
        data.email,
        base_url=settings.issuer,
        tenant_id=str(tenant_id) if tenant_id else None,
    )

    return RegisterResponse(
        id=str(user.id),
        email=data.email,
        message="Registration successful. Please verify your email.",
    )
