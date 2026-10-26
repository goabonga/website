# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""User-facing API endpoints with Bearer token authentication.

These endpoints are designed to be called by client applications (like Knowledge)
on behalf of authenticated users, using the user's access token.
"""

import logging
from datetime import UTC, datetime
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import (
    get_db,
    get_mfa_service,
    get_password_service,
    get_profile_service,
    get_token_service,
)
from auth.api.schemas.me_legacy import (
    PasswordChangeRequest,
    ProfileResponse,
    ProfileUpdateRequest,
)
from auth.api.schemas.mfa import (
    BackupCodesResponse,
    MFAStatusResponse,
    TOTPEnableResponse,
    TOTPSetupResponse,
    TOTPVerifyRequest,
)
from auth.db.models.user import User
from auth.services.mfa import MFAService
from auth.services.password import PasswordService
from auth.services.profile import ProfileData, ProfileService
from auth.services.token import TokenService
from auth.services.user import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me", tags=["user-api"])


# ===== Authentication Dependency =====


def _extract_bearer_token(authorization: str | None) -> str | None:
    """Extract bearer token from Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization[7:]


async def get_current_user_from_token(
    db: AsyncSession,
    token_service: TokenService,
    access_token: str,
) -> tuple[User, str]:
    """Get user from Bearer access token.

    Args:
        db: Database session.
        token_service: Token service.
        access_token: Bearer access token.

    Returns:
        Tuple of (authenticated user, JWT sub claim).

    Raises:
        HTTPException: If token is invalid or user not found.
    """
    # Decode token without verification to get claims
    try:
        unverified = jwt.decode(access_token, options={"verify_signature": False})
    except jwt.DecodeError:
        logger.warning("API auth failed: invalid access token format")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )

    jti = unverified.get("jti")
    if not jti:
        logger.warning("API auth failed: access token missing jti")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )

    # Verify token is valid in database
    token_record = await token_service.get_access_token_by_jti(db, jti)
    if not token_record:
        logger.warning("API auth failed: access token not found jti=%s", jti)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token not found",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )

    # Check if revoked
    if token_record.revoked_at is not None:
        logger.warning("API auth failed: access token has been revoked jti=%s", jti)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has been revoked",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )

    # Check if expired
    now = datetime.now(UTC)
    if token_record.expires_at < now:
        logger.warning("API auth failed: access token has expired jti=%s", jti)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has expired",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )

    # Get user_id from token
    user_id = token_record.user_id
    if not user_id:
        logger.warning("API auth failed: access token has no associated user jti=%s", jti)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has no associated user",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )

    # Load user with profile and emails via service
    user_service = UserService()
    user = await user_service.get_by_id(db, user_id)

    if not user or not user.is_active:
        logger.warning("API auth failed: user not found or inactive user_id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )

    # Return user + the original JWT sub (pairwise or user_id depending on config)
    jwt_sub = unverified.get("sub", str(user.id))
    return user, jwt_sub


# ===== Profile Endpoints =====


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(
    db: Annotated[AsyncSession, Depends(get_db)],
    token_service: Annotated[TokenService, Depends(get_token_service)],
    profile_service: Annotated[ProfileService, Depends(get_profile_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> ProfileResponse:
    """Get current user's profile."""
    access_token = _extract_bearer_token(authorization)
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user, jwt_sub = await get_current_user_from_token(db, token_service, access_token)
    profile = user.profile

    logger.debug("Profile API GET for user_id=%s", user.id)

    return ProfileResponse(
        sub=jwt_sub,
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


@router.put("/profile", response_model=ProfileResponse)
async def update_profile(
    data: ProfileUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    token_service: Annotated[TokenService, Depends(get_token_service)],
    profile_service: Annotated[ProfileService, Depends(get_profile_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> ProfileResponse:
    """Update current user's profile."""
    access_token = _extract_bearer_token(authorization)
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user, jwt_sub = await get_current_user_from_token(db, token_service, access_token)

    # Update profile
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

    profile = await profile_service.update_profile(db, str(user.id), profile_data)
    await db.commit()

    logger.info("ACTION: profile_update_api, user_id=%s", user.id)

    return ProfileResponse(
        sub=jwt_sub,
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


# ===== Password Endpoints =====


@router.put("/password")
async def change_password(
    data: PasswordChangeRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    token_service: Annotated[TokenService, Depends(get_token_service)],
    password_service: Annotated[PasswordService, Depends(get_password_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    """Change current user's password."""
    access_token = _extract_bearer_token(authorization)
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user, jwt_sub = await get_current_user_from_token(db, token_service, access_token)

    # Verify current password
    from auth.services.auth import AuthService

    auth_service = AuthService()

    email = None
    for e in user.emails:
        if e.is_primary:
            email = e.email
            break

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User has no email address",
        )

    # Verify current password
    verified_user = await auth_service.verify_credentials(db, email, data.current_password)
    if not verified_user:
        logger.warning("Password change failed: invalid current password for user_id=%s", user.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    # Change password
    change_result = await password_service.change_password(
        db, str(user.id), data.current_password, data.new_password
    )
    success = bool(change_result[0]) if isinstance(change_result, tuple) else bool(change_result)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to change password",
        )

    await db.commit()

    logger.info("ACTION: password_change_api, user_id=%s", user.id)

    return {"message": "Password changed successfully"}


# ===== MFA Endpoints =====


@router.get("/mfa/status", response_model=MFAStatusResponse)
async def get_mfa_status(
    db: Annotated[AsyncSession, Depends(get_db)],
    token_service: Annotated[TokenService, Depends(get_token_service)],
    mfa_service: Annotated[MFAService, Depends(get_mfa_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> MFAStatusResponse:
    """Get MFA status for current user."""
    access_token = _extract_bearer_token(authorization)
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user, jwt_sub = await get_current_user_from_token(db, token_service, access_token)

    user_mfa = await mfa_service.get_user_mfa(db, str(user.id))

    if not user_mfa or not user_mfa.totp_enabled:
        logger.debug("MFA API status: TOTP not enabled for user_id=%s", user.id)
        return MFAStatusResponse(totp_enabled=False)

    status_result = await mfa_service.get_backup_codes_status(db, str(user.id))
    logger.debug("MFA API status: TOTP enabled for user_id=%s", user.id)

    return MFAStatusResponse(
        totp_enabled=True,
        backup_codes_remaining=status_result[0] if status_result else None,
        backup_codes_total=status_result[1] if status_result else None,
    )


@router.post("/mfa/totp/setup", response_model=TOTPSetupResponse)
async def setup_totp(
    db: Annotated[AsyncSession, Depends(get_db)],
    token_service: Annotated[TokenService, Depends(get_token_service)],
    mfa_service: Annotated[MFAService, Depends(get_mfa_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> TOTPSetupResponse:
    """Start TOTP setup. Returns secret and QR code."""
    access_token = _extract_bearer_token(authorization)
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user, jwt_sub = await get_current_user_from_token(db, token_service, access_token)

    # Get user email for QR code label
    email = None
    for e in user.emails:
        if e.is_primary:
            email = e.email
            break
    email = email or "user"

    # Check if already enabled
    user_mfa = await mfa_service.get_user_mfa(db, str(user.id))
    if user_mfa and user_mfa.totp_enabled:
        logger.warning("TOTP setup API failed: already enabled for user_id=%s", user.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TOTP is already enabled. Disable it first.",
        )

    secret, uri, qr_code = await mfa_service.setup_totp(db, str(user.id), email)
    await db.commit()

    logger.info("ACTION: mfa_totp_setup_api, user_id=%s", user.id)

    return TOTPSetupResponse(
        secret=secret,
        qr_code=qr_code,
    )


@router.post("/mfa/totp/verify", response_model=TOTPEnableResponse)
async def verify_and_enable_totp(
    data: TOTPVerifyRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    token_service: Annotated[TokenService, Depends(get_token_service)],
    mfa_service: Annotated[MFAService, Depends(get_mfa_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> TOTPEnableResponse:
    """Verify TOTP code and enable MFA. Returns backup codes."""
    access_token = _extract_bearer_token(authorization)
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user, jwt_sub = await get_current_user_from_token(db, token_service, access_token)

    backup_codes = await mfa_service.enable_totp(db, str(user.id), data.code)

    if backup_codes is None:
        logger.warning("TOTP enable API failed: invalid code for user_id=%s", user.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid code or TOTP not set up",
        )

    await db.commit()

    logger.info("ACTION: mfa_totp_enable_api, user_id=%s", user.id)

    return TOTPEnableResponse(
        message="TOTP enabled successfully",
        backup_codes=backup_codes,
    )


@router.post("/mfa/totp/disable")
async def disable_totp(
    data: TOTPVerifyRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    token_service: Annotated[TokenService, Depends(get_token_service)],
    mfa_service: Annotated[MFAService, Depends(get_mfa_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    """Disable TOTP. Requires current TOTP code."""
    access_token = _extract_bearer_token(authorization)
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user, jwt_sub = await get_current_user_from_token(db, token_service, access_token)

    success = await mfa_service.disable_totp(db, str(user.id), data.code)

    if not success:
        logger.warning("TOTP disable API failed: invalid code for user_id=%s", user.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid code or TOTP not enabled",
        )

    await db.commit()

    logger.info("ACTION: mfa_totp_disable_api, user_id=%s", user.id)

    return {"message": "TOTP disabled successfully"}


@router.post("/mfa/backup-codes/regenerate", response_model=BackupCodesResponse)
async def regenerate_backup_codes(
    data: TOTPVerifyRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    token_service: Annotated[TokenService, Depends(get_token_service)],
    mfa_service: Annotated[MFAService, Depends(get_mfa_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> BackupCodesResponse:
    """Regenerate backup codes. Requires current TOTP code."""
    access_token = _extract_bearer_token(authorization)
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user, jwt_sub = await get_current_user_from_token(db, token_service, access_token)

    backup_codes = await mfa_service.regenerate_backup_codes(db, str(user.id), data.code)

    if backup_codes is None:
        logger.warning("Backup codes regenerate API failed: invalid code for user_id=%s", user.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid code or TOTP not enabled",
        )

    await db.commit()

    logger.info("ACTION: mfa_backup_codes_regenerate_api, user_id=%s", user.id)

    return BackupCodesResponse(backup_codes=backup_codes)
