# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Client for Auth service API."""

import logging
import re
from dataclasses import dataclass
from enum import StrEnum

import httpx

from knowledge.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class AuthAPIError(Exception):
    """Base exception for Auth API errors."""

    def __init__(self, message: str, error_code: str | None = None):
        self.message = message
        self.error_code = error_code
        super().__init__(message)


class PlanType(StrEnum):
    """Account plan types."""

    PERSONAL = "personal"
    ENTERPRISE = "enterprise"


@dataclass
class RegisterResult:
    """Result of user registration."""

    user_id: str
    email: str
    message: str


@dataclass
class TokenResult:
    """Result of token request."""

    access_token: str
    refresh_token: str | None
    expires_in: int
    token_type: str
    id_token: str | None = None


@dataclass
class ProfileResult:
    """User profile data."""

    sub: str
    nickname: str | None = None
    name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    middle_name: str | None = None
    preferred_username: str | None = None
    picture: str | None = None
    website: str | None = None
    gender: str | None = None
    birthdate: str | None = None
    zoneinfo: str | None = None
    locale: str | None = None
    phone_number: str | None = None


@dataclass
class MFAStatus:
    """MFA status data."""

    totp_enabled: bool
    backup_codes_remaining: int | None = None
    backup_codes_total: int | None = None


@dataclass
class TOTPSetupResult:
    """TOTP setup data."""

    secret: str
    qr_code: str


@dataclass
class TOTPEnableResult:
    """TOTP enable result with backup codes."""

    message: str
    backup_codes: list[str]


class AuthAPIClient:
    """HTTP client for Auth service API.

    Uses the confidential backend client for ROPC authentication.
    The frontend client is only used for standard OAuth2 flows (PKCE).
    """

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.oauth2_issuer).rstrip("/")
        # Confidential client for ROPC (backend-to-backend)
        self.client_id = settings.oauth2_client_id
        self.client_secret = settings.oauth2_client_secret

    async def register(
        self,
        email: str,
        password: str,
        nickname: str,
        firstname: str,
        lastname: str,
        profile_extra: dict | None = None,
    ) -> RegisterResult:
        """Register a new user.

        Args:
            email: User's email address.
            password: User's password.
            nickname: User's nickname.
            firstname: User's first name.
            lastname: User's last name.
            profile_extra: Optional extra profile fields (OIDC claims).

        Returns:
            RegisterResult with user_id, email, and message.

        Raises:
            AuthAPIError: If registration fails.
        """
        url = f"{self.base_url}/auth/register/api"

        # Build profile object with required and optional fields
        profile = {
            "nickname": nickname,
            "firstname": firstname,
            "lastname": lastname,
        }
        if profile_extra:
            profile.update(profile_extra)

        # Include registration source to track that user was created via Knowledge app
        registration_source = {
            "source": "api",
            "client_id": self.client_id,
            "client_name": "knowledge",
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    json={
                        "email": email,
                        "password": password,
                        "profile": profile,
                        "registration_source": registration_source,
                    },
                    timeout=30.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    logger.info("User registered successfully: email=%s", email)
                    return RegisterResult(
                        user_id=data["id"],
                        email=data["email"],
                        message=data["message"],
                    )

                # Handle error response
                try:
                    error_detail = response.json().get("detail", "Registration failed")
                except Exception:
                    error_detail = response.text or "Registration failed"

                logger.warning(
                    "Registration failed: status=%d, detail=%s",
                    response.status_code,
                    error_detail,
                )
                raise AuthAPIError(error_detail, error_code="registration_failed")

            except httpx.RequestError as e:
                logger.error("Auth API connection error: %s", e)
                raise AuthAPIError(
                    "Unable to connect to authentication service",
                    error_code="connection_error",
                )

    async def verify_email(self, email: str, code: str) -> bool:
        """Verify user's email with verification code.

        Args:
            email: User's email address.
            code: Verification code.

        Returns:
            True if verification successful.

        Raises:
            AuthAPIError: If verification fails.
        """
        url = f"{self.base_url}/auth/verify-email/api"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    json={"email": email, "code": code},
                    timeout=30.0,
                )

                if response.status_code == 200:
                    logger.info("Email verified successfully: email=%s", email)
                    return True

                # Handle error response
                try:
                    error_detail = response.json().get("detail", "Verification failed")
                except Exception:
                    error_detail = response.text or "Verification failed"

                logger.warning(
                    "Email verification failed: status=%d, detail=%s",
                    response.status_code,
                    error_detail,
                )
                raise AuthAPIError(error_detail, error_code="verification_failed")

            except httpx.RequestError as e:
                logger.error("Auth API connection error: %s", e)
                raise AuthAPIError(
                    "Unable to connect to authentication service",
                    error_code="connection_error",
                )

    async def resend_verification(self, email: str) -> bool:
        """Resend verification email.

        Args:
            email: User's email address.

        Returns:
            True (always, to prevent email enumeration).

        Raises:
            AuthAPIError: If request fails.
        """
        url = f"{self.base_url}/auth/resend-verification/api"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    json={"email": email},
                    timeout=30.0,
                )

                if response.status_code == 200:
                    logger.info("Verification email resent: email=%s", email)
                    return True

                logger.warning(
                    "Resend verification failed: status=%d",
                    response.status_code,
                )
                return True  # Don't expose failure to prevent enumeration

            except httpx.RequestError as e:
                logger.error("Auth API connection error: %s", e)
                raise AuthAPIError(
                    "Unable to connect to authentication service",
                    error_code="connection_error",
                )

    async def forgot_password(self, email: str, reset_base_url: str | None = None) -> bool:
        """Request password reset email.

        Args:
            email: User's email address.
            reset_base_url: Custom base URL for reset link (defaults to app_base_url).

        Returns:
            True (always, to prevent email enumeration).

        Raises:
            AuthAPIError: If request fails.
        """
        url = f"{self.base_url}/auth/forgot-password/api"

        # Use app_base_url so reset link points back to Knowledge
        base_url = reset_base_url or settings.app_base_url or None

        payload = {"email": email}
        if base_url:
            payload["reset_base_url"] = base_url

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    json=payload,
                    timeout=30.0,
                )

                if response.status_code == 200:
                    logger.info("Password reset email requested: email=%s", email)
                    return True

                logger.warning(
                    "Forgot password request failed: status=%d",
                    response.status_code,
                )
                return True  # Don't expose failure to prevent enumeration

            except httpx.RequestError as e:
                logger.error("Auth API connection error: %s", e)
                raise AuthAPIError(
                    "Unable to connect to authentication service",
                    error_code="connection_error",
                )

    async def reset_password(self, token: str, password: str) -> bool:
        """Reset user password with token.

        Args:
            token: Password reset token from email.
            password: New password.

        Returns:
            True if password reset successful.

        Raises:
            AuthAPIError: If reset fails (invalid/expired token or validation error).
        """
        url = f"{self.base_url}/auth/reset-password/api"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    json={"token": token, "password": password},
                    timeout=30.0,
                )

                if response.status_code == 200:
                    logger.info("Password reset successful")
                    return True

                # Handle error response
                try:
                    error_detail = response.json().get("detail", "Password reset failed")
                except Exception:
                    error_detail = response.text or "Password reset failed"

                logger.warning(
                    "Password reset failed: status=%d, detail=%s",
                    response.status_code,
                    error_detail,
                )
                raise AuthAPIError(error_detail, error_code="reset_failed")

            except httpx.RequestError as e:
                logger.error("Auth API connection error: %s", e)
                raise AuthAPIError(
                    "Unable to connect to authentication service",
                    error_code="connection_error",
                )

    async def login(
        self,
        email: str,
        password: str,
        otp: str | None = None,
        scopes: list[str] | None = None,
    ) -> TokenResult:
        """Authenticate user and get tokens (ROPC grant).

        Uses the confidential backend client with client credentials.
        Only requests standard OIDC scopes (openid, profile, email, offline_access).

        Args:
            email: User's email address.
            password: User's password.
            otp: Optional OTP code when MFA is enabled.
            scopes: Requested scopes (defaults to openid profile email offline_access).

        Returns:
            TokenResult with access_token, refresh_token, etc.

        Raises:
            AuthAPIError: If authentication fails.
        """
        url = f"{self.base_url}/oauth2/token"

        if scopes is None:
            scopes = ["openid", "profile", "email", "offline_access"]

        async with httpx.AsyncClient() as client:
            try:
                # Use HTTP Basic Auth for confidential client authentication
                payload = {
                    "grant_type": "password",
                    "username": email,
                    "password": password,
                    "scope": " ".join(scopes),
                }
                if otp:
                    payload["otp"] = otp

                response = await client.post(
                    url,
                    data=payload,
                    auth=(self.client_id, self.client_secret),
                    timeout=30.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    logger.info("User logged in successfully: email=%s", email)
                    return TokenResult(
                        access_token=data["access_token"],
                        refresh_token=data.get("refresh_token"),
                        expires_in=data.get("expires_in", 3600),
                        token_type=data.get("token_type", "Bearer"),
                        id_token=data.get("id_token"),
                    )

                # Handle error response
                try:
                    error_data = response.json()
                    detail = error_data.get("detail")
                    if isinstance(detail, dict):
                        # FastAPI OAuth errors are often wrapped in {"detail": {...}}.
                        error_desc = detail.get(
                            "error_description",
                            detail.get("detail", "Authentication failed"),
                        )
                        error_code = detail.get("error", error_data.get("error", "invalid_grant"))
                    else:
                        error_desc = error_data.get(
                            "error_description",
                            detail if detail is not None else "Authentication failed",
                        )
                        error_code = error_data.get("error", "invalid_grant")
                except Exception:
                    error_desc = "Authentication failed"
                    error_code = "invalid_grant"

                logger.warning(
                    "Login failed: status=%d, error=%s",
                    response.status_code,
                    error_desc,
                )
                raise AuthAPIError(str(error_desc), error_code=error_code)

            except httpx.RequestError as e:
                logger.error("Auth API connection error: %s", e)
                raise AuthAPIError(
                    "Unable to connect to authentication service",
                    error_code="connection_error",
                )

    async def send_login_mfa_email_code(self, email: str, password: str) -> str | None:
        """Trigger a login MFA email code using Auth's two-step login flow.

        This reuses the HTML login endpoint:
        1) submit credentials to create MFA challenge cookie
        2) request `send_email_code=1` with that challenge

        Args:
            email: User email.
            password: User password.

        Returns:
            Masked destination email when available (e.g. ``j***e@example.com``).

        Raises:
            AuthAPIError: If credentials are invalid, MFA challenge cannot be created,
                or email code cannot be sent.
        """
        url = f"{self.base_url}/auth/login"

        async with httpx.AsyncClient() as client:
            try:
                step1 = await client.post(
                    url,
                    data={"email": email, "password": password},
                    timeout=30.0,
                )

                if step1.status_code >= 400:
                    if "Invalid email or password" in step1.text:
                        raise AuthAPIError("Invalid email or password", error_code="invalid_grant")
                    raise AuthAPIError(
                        "Could not verify credentials for MFA.",
                        error_code="mfa_challenge_failed",
                    )

                challenge_cookie = client.cookies.get("mfa_login_challenge")
                if not challenge_cookie:
                    raise AuthAPIError(
                        "MFA is not enabled for this account.",
                        error_code="mfa_not_enabled",
                    )

                step2 = await client.post(
                    url,
                    data={"email": email, "send_email_code": "1"},
                    timeout=30.0,
                )

                if step2.status_code >= 400:
                    if "Failed to send MFA email" in step2.text:
                        raise AuthAPIError(
                            "Failed to send MFA email. Please try again.",
                            error_code="mfa_email_send_failed",
                        )
                    raise AuthAPIError(
                        "Unable to send MFA email code.",
                        error_code="mfa_email_send_failed",
                    )

                match = re.search(r"Verification code sent to ([^<]+)", step2.text)
                return match.group(1).strip() if match else None

            except httpx.RequestError as e:
                logger.error("Auth API connection error: %s", e)
                raise AuthAPIError(
                    "Unable to connect to authentication service",
                    error_code="connection_error",
                )

    async def get_userinfo(self, access_token: str) -> dict:
        """Get user info from Auth service.

        Args:
            access_token: Valid access token.

        Returns:
            User info claims.

        Raises:
            AuthAPIError: If request fails.
        """
        url = f"{self.base_url}/userinfo"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=30.0,
                )

                if response.status_code == 200:
                    return response.json()

                logger.warning(
                    "Get userinfo failed: status=%d",
                    response.status_code,
                )
                raise AuthAPIError(
                    "Failed to get user info",
                    error_code="userinfo_failed",
                )

            except httpx.RequestError as e:
                logger.error("Auth API connection error: %s", e)
                raise AuthAPIError(
                    "Unable to connect to authentication service",
                    error_code="connection_error",
                )

    # ===== Profile API =====

    async def get_profile(self, access_token: str) -> ProfileResult:
        """Get user profile from Auth service.

        Args:
            access_token: Valid access token.

        Returns:
            ProfileResult with user profile data.

        Raises:
            AuthAPIError: If request fails.
        """
        url = f"{self.base_url}/api/me/profile"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=30.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    return ProfileResult(
                        sub=data["sub"],
                        nickname=data.get("nickname"),
                        name=data.get("name"),
                        given_name=data.get("given_name"),
                        family_name=data.get("family_name"),
                        middle_name=data.get("middle_name"),
                        preferred_username=data.get("preferred_username"),
                        picture=data.get("picture"),
                        website=data.get("website"),
                        gender=data.get("gender"),
                        birthdate=data.get("birthdate"),
                        zoneinfo=data.get("zoneinfo"),
                        locale=data.get("locale"),
                        phone_number=data.get("phone_number"),
                    )

                logger.warning(
                    "Get profile failed: status=%d",
                    response.status_code,
                )
                raise AuthAPIError(
                    "Failed to get profile",
                    error_code="profile_failed",
                )

            except httpx.RequestError as e:
                logger.error("Auth API connection error: %s", e)
                raise AuthAPIError(
                    "Unable to connect to authentication service",
                    error_code="connection_error",
                )

    async def update_profile(
        self,
        access_token: str,
        nickname: str | None = None,
        given_name: str | None = None,
        family_name: str | None = None,
        middle_name: str | None = None,
        preferred_username: str | None = None,
        picture: str | None = None,
        website: str | None = None,
        gender: str | None = None,
        birthdate: str | None = None,
        zoneinfo: str | None = None,
        locale: str | None = None,
        phone_number: str | None = None,
    ) -> ProfileResult:
        """Update user profile via Auth service.

        Args:
            access_token: Valid access token.
            nickname: User's nickname.
            given_name: User's first name.
            family_name: User's last name.
            middle_name: User's middle name.
            preferred_username: User's preferred username.
            picture: URL to profile picture.
            website: User's website URL.
            gender: User's gender.
            birthdate: User's birthdate (YYYY-MM-DD).
            zoneinfo: User's timezone.
            locale: User's locale.
            phone_number: User's phone number.

        Returns:
            ProfileResult with updated profile data.

        Raises:
            AuthAPIError: If request fails.
        """
        url = f"{self.base_url}/api/me/profile"

        payload = {}
        if nickname is not None:
            payload["nickname"] = nickname
        if given_name is not None:
            payload["given_name"] = given_name
        if family_name is not None:
            payload["family_name"] = family_name
        if middle_name is not None:
            payload["middle_name"] = middle_name
        if preferred_username is not None:
            payload["preferred_username"] = preferred_username
        if picture is not None:
            payload["picture"] = picture
        if website is not None:
            payload["website"] = website
        if gender is not None:
            payload["gender"] = gender
        if birthdate is not None:
            payload["birthdate"] = birthdate
        if zoneinfo is not None:
            payload["zoneinfo"] = zoneinfo
        if locale is not None:
            payload["locale"] = locale
        if phone_number is not None:
            payload["phone_number"] = phone_number

        async with httpx.AsyncClient() as client:
            try:
                response = await client.put(
                    url,
                    headers={"Authorization": f"Bearer {access_token}"},
                    json=payload,
                    timeout=30.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    logger.info("Profile updated successfully")
                    return ProfileResult(
                        sub=data["sub"],
                        nickname=data.get("nickname"),
                        name=data.get("name"),
                        given_name=data.get("given_name"),
                        family_name=data.get("family_name"),
                        middle_name=data.get("middle_name"),
                        preferred_username=data.get("preferred_username"),
                        picture=data.get("picture"),
                        website=data.get("website"),
                        gender=data.get("gender"),
                        birthdate=data.get("birthdate"),
                        zoneinfo=data.get("zoneinfo"),
                        locale=data.get("locale"),
                        phone_number=data.get("phone_number"),
                    )

                # Handle error response
                try:
                    error_detail = response.json().get("detail", "Profile update failed")
                except Exception:
                    error_detail = response.text or "Profile update failed"

                logger.warning(
                    "Profile update failed: status=%d, detail=%s",
                    response.status_code,
                    error_detail,
                )
                raise AuthAPIError(error_detail, error_code="profile_update_failed")

            except httpx.RequestError as e:
                logger.error("Auth API connection error: %s", e)
                raise AuthAPIError(
                    "Unable to connect to authentication service",
                    error_code="connection_error",
                )

    # ===== Password API =====

    async def change_password(
        self,
        access_token: str,
        current_password: str,
        new_password: str,
    ) -> bool:
        """Change user password via Auth service.

        Args:
            access_token: Valid access token.
            current_password: Current password.
            new_password: New password.

        Returns:
            True if password changed successfully.

        Raises:
            AuthAPIError: If request fails.
        """
        url = f"{self.base_url}/api/me/password"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.put(
                    url,
                    headers={"Authorization": f"Bearer {access_token}"},
                    json={
                        "current_password": current_password,
                        "new_password": new_password,
                    },
                    timeout=30.0,
                )

                if response.status_code == 200:
                    logger.info("Password changed successfully")
                    return True

                # Handle error response
                try:
                    error_detail = response.json().get("detail", "Password change failed")
                except Exception:
                    error_detail = response.text or "Password change failed"

                logger.warning(
                    "Password change failed: status=%d, detail=%s",
                    response.status_code,
                    error_detail,
                )
                raise AuthAPIError(error_detail, error_code="password_change_failed")

            except httpx.RequestError as e:
                logger.error("Auth API connection error: %s", e)
                raise AuthAPIError(
                    "Unable to connect to authentication service",
                    error_code="connection_error",
                )

    # ===== MFA API =====

    async def get_mfa_status(self, access_token: str) -> MFAStatus:
        """Get MFA status from Auth service.

        Args:
            access_token: Valid access token.

        Returns:
            MFAStatus with TOTP status and backup codes info.

        Raises:
            AuthAPIError: If request fails.
        """
        url = f"{self.base_url}/api/me/mfa/status"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=30.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    return MFAStatus(
                        totp_enabled=data["totp_enabled"],
                        backup_codes_remaining=data.get("backup_codes_remaining"),
                        backup_codes_total=data.get("backup_codes_total"),
                    )

                logger.warning(
                    "Get MFA status failed: status=%d",
                    response.status_code,
                )
                raise AuthAPIError(
                    "Failed to get MFA status",
                    error_code="mfa_status_failed",
                )

            except httpx.RequestError as e:
                logger.error("Auth API connection error: %s", e)
                raise AuthAPIError(
                    "Unable to connect to authentication service",
                    error_code="connection_error",
                )

    async def setup_totp(self, access_token: str) -> TOTPSetupResult:
        """Start TOTP setup. Returns secret and QR code.

        Args:
            access_token: Valid access token.

        Returns:
            TOTPSetupResult with secret and QR code base64 image.

        Raises:
            AuthAPIError: If request fails.
        """
        url = f"{self.base_url}/api/me/mfa/totp/setup"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=30.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    return TOTPSetupResult(
                        secret=data["secret"],
                        qr_code=data["qr_code"],
                    )

                # Handle error response
                try:
                    error_detail = response.json().get("detail", "TOTP setup failed")
                except Exception:
                    error_detail = response.text or "TOTP setup failed"

                logger.warning(
                    "TOTP setup failed: status=%d, detail=%s",
                    response.status_code,
                    error_detail,
                )
                raise AuthAPIError(error_detail, error_code="totp_setup_failed")

            except httpx.RequestError as e:
                logger.error("Auth API connection error: %s", e)
                raise AuthAPIError(
                    "Unable to connect to authentication service",
                    error_code="connection_error",
                )

    async def verify_and_enable_totp(
        self,
        access_token: str,
        code: str,
    ) -> TOTPEnableResult:
        """Verify TOTP code and enable MFA. Returns backup codes.

        Args:
            access_token: Valid access token.
            code: TOTP code from authenticator app.

        Returns:
            TOTPEnableResult with success message and backup codes.

        Raises:
            AuthAPIError: If verification fails.
        """
        url = f"{self.base_url}/api/me/mfa/totp/verify"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {access_token}"},
                    json={"code": code},
                    timeout=30.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    logger.info("TOTP enabled successfully")
                    return TOTPEnableResult(
                        message=data["message"],
                        backup_codes=data["backup_codes"],
                    )

                # Handle error response
                try:
                    error_detail = response.json().get("detail", "TOTP verification failed")
                except Exception:
                    error_detail = response.text or "TOTP verification failed"

                logger.warning(
                    "TOTP verification failed: status=%d, detail=%s",
                    response.status_code,
                    error_detail,
                )
                raise AuthAPIError(error_detail, error_code="totp_verify_failed")

            except httpx.RequestError as e:
                logger.error("Auth API connection error: %s", e)
                raise AuthAPIError(
                    "Unable to connect to authentication service",
                    error_code="connection_error",
                )

    async def disable_totp(self, access_token: str, code: str) -> bool:
        """Disable TOTP. Requires current TOTP code.

        Args:
            access_token: Valid access token.
            code: Current TOTP code.

        Returns:
            True if TOTP disabled successfully.

        Raises:
            AuthAPIError: If request fails.
        """
        url = f"{self.base_url}/api/me/mfa/totp/disable"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {access_token}"},
                    json={"code": code},
                    timeout=30.0,
                )

                if response.status_code == 200:
                    logger.info("TOTP disabled successfully")
                    return True

                # Handle error response
                try:
                    error_detail = response.json().get("detail", "TOTP disable failed")
                except Exception:
                    error_detail = response.text or "TOTP disable failed"

                logger.warning(
                    "TOTP disable failed: status=%d, detail=%s",
                    response.status_code,
                    error_detail,
                )
                raise AuthAPIError(error_detail, error_code="totp_disable_failed")

            except httpx.RequestError as e:
                logger.error("Auth API connection error: %s", e)
                raise AuthAPIError(
                    "Unable to connect to authentication service",
                    error_code="connection_error",
                )

    async def regenerate_backup_codes(
        self,
        access_token: str,
        code: str,
    ) -> list[str]:
        """Regenerate backup codes. Requires current TOTP code.

        Args:
            access_token: Valid access token.
            code: Current TOTP code.

        Returns:
            List of new backup codes.

        Raises:
            AuthAPIError: If request fails.
        """
        url = f"{self.base_url}/api/me/mfa/backup-codes/regenerate"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {access_token}"},
                    json={"code": code},
                    timeout=30.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    logger.info("Backup codes regenerated successfully")
                    return data["backup_codes"]

                # Handle error response
                try:
                    error_detail = response.json().get("detail", "Backup codes regeneration failed")
                except Exception:
                    error_detail = response.text or "Backup codes regeneration failed"

                logger.warning(
                    "Backup codes regeneration failed: status=%d, detail=%s",
                    response.status_code,
                    error_detail,
                )
                raise AuthAPIError(error_detail, error_code="backup_codes_failed")

            except httpx.RequestError as e:
                logger.error("Auth API connection error: %s", e)
                raise AuthAPIError(
                    "Unable to connect to authentication service",
                    error_code="connection_error",
                )


def get_auth_api_client() -> AuthAPIClient:
    """Get AuthAPIClient instance."""
    return AuthAPIClient()
