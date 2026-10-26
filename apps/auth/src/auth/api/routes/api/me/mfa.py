# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""MFA management API endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.api.deps import get_db, get_mfa_service
from auth.api.routes.api.deps import get_current_user_bearer
from auth.api.schemas.api.common import MessageResponse
from auth.api.schemas.api.me import (
    BackupCodesResponse,
    MFAStatusResponse,
    TOTPEnableResponse,
    TOTPSetupResponse,
    TOTPVerifyRequest,
)
from auth.db.models.user import User
from auth.services.mfa import MFAService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mfa", tags=["me:mfa"])


@router.get("/", response_model=MFAStatusResponse)
async def get_mfa_status(
    user: Annotated[User, Depends(get_current_user_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
    mfa_service: Annotated[MFAService, Depends(get_mfa_service)],
) -> MFAStatusResponse:
    """Return the current MFA status for the authenticated user.

    Indicates whether TOTP is enabled and, if so, how many backup codes
    remain unused out of the total generated. When TOTP is disabled, backup
    code counts are returned as null.

    **Required scope:** any valid Bearer token

    **Example:**
    ```
    curl -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/me/mfa/
    ```
    """
    user_mfa = await mfa_service.get_user_mfa(db, str(user.id))

    if not user_mfa or not user_mfa.totp_enabled:
        return MFAStatusResponse(
            totp_enabled=False,
            backup_codes_remaining=None,
            backup_codes_total=None,
        )

    backup_status = await mfa_service.get_backup_codes_status(db, str(user.id))
    remaining, total = backup_status if backup_status else (None, None)

    return MFAStatusResponse(
        totp_enabled=True,
        backup_codes_remaining=remaining,
        backup_codes_total=total,
    )


@router.post("/totp/setup", response_model=TOTPSetupResponse)
async def setup_totp(
    user: Annotated[User, Depends(get_current_user_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
    mfa_service: Annotated[MFAService, Depends(get_mfa_service)],
) -> TOTPSetupResponse:
    """Initiate TOTP setup and return a one-time secret and QR code.

    Generates a new TOTP secret tied to the user's primary email address and
    returns it alongside a base64-encoded QR code PNG. The secret is only
    returned once — store it before calling the verify endpoint. TOTP is not
    active until confirmed via `POST /totp/verify`.

    **Required scope:** any valid Bearer token

    **Example:**
    ```
    curl -X POST -H "Authorization: Bearer <token>" \\
      https://auth.example.com/api/v1/me/mfa/totp/setup
    ```
    """
    primary_email = next((e.email for e in user.emails if e.is_primary), None)
    if not primary_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No primary email found for user",
        )

    secret, _uri, qr_code = await mfa_service.setup_totp(db, str(user.id), primary_email)
    await db.commit()

    logger.info("ACTION: mfa_totp_setup_api_v1, user_id=%s", user.id)

    return TOTPSetupResponse(secret=secret, qr_code=qr_code)


@router.post("/totp/verify", response_model=TOTPEnableResponse)
async def verify_and_enable_totp(
    body: TOTPVerifyRequest,
    user: Annotated[User, Depends(get_current_user_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
    mfa_service: Annotated[MFAService, Depends(get_mfa_service)],
) -> TOTPEnableResponse:
    """Verify a TOTP code and permanently enable TOTP-based MFA.

    Validates the 6-digit code against the secret provisioned by
    `POST /totp/setup`. On success, TOTP is activated and a set of one-time
    backup codes is returned — these codes are shown only once and cannot be
    retrieved again. Returns 400 if the code is invalid or setup was never
    initiated.

    **Required scope:** any valid Bearer token

    **Example:**
    ```
    curl -X POST -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"code": "123456"}' \\
      https://auth.example.com/api/v1/me/mfa/totp/verify
    ```
    """
    backup_codes = await mfa_service.enable_totp(db, str(user.id), body.code)

    if backup_codes is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid TOTP code or TOTP setup not initiated",
        )

    await db.commit()

    logger.info("ACTION: mfa_totp_enable_api_v1, user_id=%s", user.id)

    return TOTPEnableResponse(
        message="TOTP enabled successfully",
        backup_codes=backup_codes,
    )


@router.post("/totp/disable", response_model=MessageResponse)
async def disable_totp(
    body: TOTPVerifyRequest,
    user: Annotated[User, Depends(get_current_user_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
    mfa_service: Annotated[MFAService, Depends(get_mfa_service)],
) -> MessageResponse:
    """Disable TOTP-based MFA after confirming with a valid TOTP code.

    Requires the user to supply a current 6-digit TOTP code as proof of
    possession before deactivating MFA. All backup codes are invalidated at
    the same time. Returns 400 if the code is wrong or TOTP is not currently
    enabled.

    **Required scope:** any valid Bearer token

    **Example:**
    ```
    curl -X POST -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"code": "654321"}' \\
      https://auth.example.com/api/v1/me/mfa/totp/disable
    ```
    """
    success = await mfa_service.disable_totp(db, str(user.id), body.code)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid TOTP code or TOTP not enabled",
        )

    await db.commit()

    logger.info("ACTION: mfa_totp_disable_api_v1, user_id=%s", user.id)

    return MessageResponse(message="TOTP disabled successfully")


@router.post("/backup-codes", response_model=BackupCodesResponse)
async def regenerate_backup_codes(
    body: TOTPVerifyRequest,
    user: Annotated[User, Depends(get_current_user_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
    mfa_service: Annotated[MFAService, Depends(get_mfa_service)],
) -> BackupCodesResponse:
    """Regenerate all backup codes, invalidating the previous set.

    Requires a valid 6-digit TOTP code to authorize the rotation. All
    previously issued backup codes are permanently revoked and replaced by
    a fresh set. The new codes are returned only in this response — they
    cannot be retrieved again. Returns 400 if the TOTP code is invalid or
    MFA is not enabled.

    **Required scope:** any valid Bearer token

    **Example:**
    ```
    curl -X POST -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"code": "789012"}' \\
      https://auth.example.com/api/v1/me/mfa/backup-codes
    ```
    """
    codes = await mfa_service.regenerate_backup_codes(db, str(user.id), body.code)

    if codes is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid TOTP code or MFA not enabled",
        )

    await db.commit()

    logger.info("ACTION: mfa_backup_codes_regenerate_api_v1, user_id=%s", user.id)

    return BackupCodesResponse(backup_codes=codes)
