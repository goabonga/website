# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""MFA (TOTP / backup codes / email OTP) request and response schemas."""

from pydantic import BaseModel


class MFAStatusResponse(BaseModel):
    """MFA status response."""

    totp_enabled: bool
    backup_codes_remaining: int | None = None
    backup_codes_total: int | None = None


class TOTPSetupResponse(BaseModel):
    """TOTP setup response."""

    secret: str
    qr_code: str


class TOTPVerifyRequest(BaseModel):
    """TOTP verify request."""

    code: str


class TOTPEnableResponse(BaseModel):
    """TOTP enable response."""

    message: str
    backup_codes: list[str]


class BackupCodesResponse(BaseModel):
    """Backup codes response."""

    backup_codes: list[str]


class MFAVerifyRequest(BaseModel):
    """MFA verify request."""

    code: str


class EmailMFASendResponse(BaseModel):
    """Email MFA send response."""

    message: str
    email_masked: str
