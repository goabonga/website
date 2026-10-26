# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Federation service for external identity providers."""

import hashlib
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from auth.core.encryption import decrypt_value
from auth.db.models.tenant import (
    FederatedIdentity,
    IdentityProvider,
    IdentityProviderType,
    TenantMember,
    WebhookEvent,
)
from auth.db.models.user import User, UserEmail, UserProfile
from auth.db.repositories.federation import FederationRepository
from auth.db.repositories.tenant import TenantRepository
from auth.db.repositories.user import UserRepository
from auth.services.tenant_role import tenant_role_service
from auth.services.webhook import safe_dispatch as dispatch_webhook_event

logger = logging.getLogger(__name__)


@dataclass
class OIDCDiscoveryDocument:
    """OIDC Discovery document (well-known configuration)."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str | None
    jwks_uri: str
    scopes_supported: list[str] | None = None
    response_types_supported: list[str] | None = None
    claims_supported: list[str] | None = None


@dataclass
class FederationState:
    """State for federation flow (stored in session or cache)."""

    tenant_slug: str
    idp_id: str
    original_state: str | None  # Original OAuth2 state from client
    redirect_uri: str | None  # Where to redirect after federation
    nonce: str
    code_verifier: str | None = None  # PKCE code verifier


@dataclass
class FederatedUserInfo:
    """User information extracted from IdP response."""

    subject: str  # IdP's unique user identifier
    email: str | None
    email_verified: bool
    name: str | None
    given_name: str | None
    family_name: str | None
    picture: str | None
    username: str | None
    raw_claims: dict[str, Any]


class FederationService:
    """Service for handling federated identity provider authentication.

    SQL access is delegated to :class:`FederationRepository`; this service
    owns the business flow (JIT provisioning, account linking, tenant
    auto-enrolment) and transaction boundaries.
    """

    def __init__(
        self,
        repository: FederationRepository | None = None,
        *,
        user_repository: UserRepository | None = None,
        tenant_repository: TenantRepository | None = None,
    ) -> None:
        self._repo = repository or FederationRepository()
        self._user_repo = user_repository or UserRepository()
        self._tenant_repo = tenant_repository or TenantRepository()

    # Well-known endpoints for social providers
    PROVIDER_CONFIGS: dict[IdentityProviderType, dict[str, str]] = {
        IdentityProviderType.GOOGLE: {
            "discovery_url": "https://accounts.google.com/.well-known/openid-configuration",
            "scopes": "openid profile email",
        },
        IdentityProviderType.GITHUB: {
            "authorization_endpoint": "https://github.com/login/oauth/authorize",
            "token_endpoint": "https://github.com/login/oauth/access_token",
            "userinfo_endpoint": "https://api.github.com/user",
            "scopes": "read:user user:email",
        },
        IdentityProviderType.MICROSOFT: {
            "discovery_url": "https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration",
            "scopes": "openid profile email",
        },
    }

    async def get_tenant_identity_providers(
        self, db: AsyncSession, tenant_slug: str
    ) -> list[IdentityProvider]:
        """Get all active identity providers for a tenant.

        Args:
            db: Database session.
            tenant_slug: Tenant slug.

        Returns:
            List of active identity providers.
        """
        return await self._repo.list_idps_for_tenant_slug(db, tenant_slug)

    async def get_identity_provider(self, db: AsyncSession, idp_id: str) -> IdentityProvider | None:
        """Get an identity provider by ID.

        Args:
            db: Database session.
            idp_id: Identity provider ID.

        Returns:
            Identity provider if found.
        """
        return await self._repo.find_idp_by_id(db, idp_id)

    # ------------------------------------------------------------------
    # Federated identity reads/writes (account-settings flows)
    # ------------------------------------------------------------------

    async def list_user_federated_identities(
        self,
        db: AsyncSession,
        user_id: "uuid.UUID",
    ) -> list[FederatedIdentity]:
        """Return a user's federated identities with IdP and tenant eager-loaded.

        Used by the settings page to render the cross-tenant "linked accounts"
        summary alongside each membership.
        """
        return await self._repo.list_identities_for_user(db, user_id)

    async def list_federated_identities_for_user_in_tenant(
        self,
        db: AsyncSession,
        user_id: "uuid.UUID",
        tenant_id: "uuid.UUID",
    ) -> list[FederatedIdentity]:
        """List a user's federated identities whose IdP belongs to ``tenant_id``."""
        return await self._repo.list_identities_for_user_in_tenant(db, user_id, tenant_id)

    async def get_federated_identity(
        self,
        db: AsyncSession,
        user_id: "uuid.UUID",
        idp_id: "uuid.UUID",
    ) -> FederatedIdentity | None:
        """Fetch a single federated identity by (user_id, idp_id)."""
        return await self._repo.find_federated_identity(db, user_id, idp_id)

    async def delete_federated_identity(
        self,
        db: AsyncSession,
        federated_identity: FederatedIdentity,
    ) -> None:
        """Stage a ``FederatedIdentity`` deletion (caller owns the commit)."""
        await self._repo.delete(db, federated_identity)

    async def fetch_oidc_discovery(self, discovery_url: str) -> OIDCDiscoveryDocument:
        """Fetch and parse OIDC discovery document.

        Args:
            discovery_url: URL to the .well-known/openid-configuration.

        Returns:
            Parsed discovery document.

        Raises:
            httpx.HTTPError: If the request fails.
            ValueError: If the document is invalid.
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(discovery_url)
            response.raise_for_status()
            data = response.json()

        return OIDCDiscoveryDocument(
            issuer=data["issuer"],
            authorization_endpoint=data["authorization_endpoint"],
            token_endpoint=data["token_endpoint"],
            userinfo_endpoint=data.get("userinfo_endpoint"),
            jwks_uri=data["jwks_uri"],
            scopes_supported=data.get("scopes_supported"),
            response_types_supported=data.get("response_types_supported"),
            claims_supported=data.get("claims_supported"),
        )

    async def get_authorization_url(
        self,
        idp: IdentityProvider,
        callback_url: str,
        state: str,
        nonce: str,
        code_verifier: str | None = None,
    ) -> str:
        """Generate the authorization URL for an identity provider.

        Args:
            idp: Identity provider configuration.
            callback_url: Callback URL for the IdP to redirect to.
            state: State parameter for CSRF protection.
            nonce: Nonce for ID token validation.
            code_verifier: Optional PKCE code verifier.

        Returns:
            Authorization URL to redirect the user to.
        """
        # Get authorization endpoint
        auth_endpoint = await self._get_authorization_endpoint(idp)

        # Build scopes
        scopes = idp.scopes or ["openid", "profile", "email"]

        # Build query parameters
        params: dict[str, str] = {
            "client_id": idp.client_id,
            "redirect_uri": callback_url,
            "response_type": "code",
            "scope": " ".join(scopes),
            "state": state,
        }

        # Add nonce for OIDC providers
        if idp.provider_type != IdentityProviderType.GITHUB:
            params["nonce"] = nonce

        # Add PKCE if code_verifier is provided
        if code_verifier:
            code_challenge = self._generate_code_challenge(code_verifier)
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"

        return f"{auth_endpoint}?{urlencode(params)}"

    async def exchange_code_for_tokens(
        self,
        idp: IdentityProvider,
        code: str,
        callback_url: str,
        code_verifier: str | None = None,
    ) -> dict[str, Any]:
        """Exchange authorization code for tokens.

        Args:
            idp: Identity provider configuration.
            code: Authorization code from IdP.
            callback_url: Callback URL used in authorization request.
            code_verifier: Optional PKCE code verifier.

        Returns:
            Token response from IdP.
        """
        token_endpoint = await self._get_token_endpoint(idp)

        # Build request body
        data: dict[str, str] = {
            "grant_type": "authorization_code",
            "client_id": idp.client_id,
            "code": code,
            "redirect_uri": callback_url,
        }

        # Add client secret if available
        if idp.client_secret_encrypted:
            client_secret = decrypt_value(idp.client_secret_encrypted)
            data["client_secret"] = client_secret

        # Add PKCE verifier if provided
        if code_verifier:
            data["code_verifier"] = code_verifier

        # Determine content type based on provider
        headers = {"Accept": "application/json"}
        if idp.provider_type == IdentityProviderType.GITHUB:
            headers["Accept"] = "application/json"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                token_endpoint,
                data=data,
                headers=headers,
            )
            response.raise_for_status()
            return response.json()

    async def get_user_info(
        self,
        idp: IdentityProvider,
        access_token: str,
        id_token: str | None = None,
    ) -> FederatedUserInfo:
        """Get user information from IdP.

        Args:
            idp: Identity provider configuration.
            access_token: Access token from IdP.
            id_token: Optional ID token (for OIDC providers).

        Returns:
            Extracted user information.
        """
        # Try to extract claims from ID token first (if available)
        claims: dict[str, Any] = {}
        if id_token:
            # Decode without verification (we trust the IdP's token endpoint)
            claims = jwt.decode(
                id_token,
                options={"verify_signature": False},
                algorithms=["RS256", "HS256", "ES256"],
            )

        # Fetch additional info from userinfo endpoint if available
        userinfo_endpoint = await self._get_userinfo_endpoint(idp)
        if userinfo_endpoint:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    userinfo_endpoint,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if response.status_code == 200:
                    userinfo = response.json()
                    # Merge with ID token claims (userinfo takes precedence)
                    claims.update(userinfo)

        # Special handling for GitHub (non-OIDC)
        if idp.provider_type == IdentityProviderType.GITHUB:
            return await self._get_github_user_info(access_token, claims)

        # Apply attribute mapping
        claims = self._apply_attribute_mapping(claims, idp.attribute_mapping)

        return FederatedUserInfo(
            subject=str(claims.get("sub", "")),
            email=claims.get("email"),
            email_verified=claims.get("email_verified", False),
            name=claims.get("name"),
            given_name=claims.get("given_name"),
            family_name=claims.get("family_name"),
            picture=claims.get("picture"),
            username=claims.get("preferred_username"),
            raw_claims=claims,
        )

    async def find_or_create_user(
        self,
        db: AsyncSession,
        idp: IdentityProvider,
        user_info: FederatedUserInfo,
        tenant_slug: str,
    ) -> tuple[User, FederatedIdentity, bool]:
        """Find existing user or create new one via JIT provisioning.

        Args:
            db: Database session.
            idp: Identity provider.
            user_info: User information from IdP.
            tenant_slug: Tenant slug for membership.

        Returns:
            Tuple of (user, federated_identity, is_new_user).
        """
        now = datetime.now(UTC)

        # 1. Check for existing federated identity
        federated_identity = await self._repo.find_identity_by_subject(
            db, idp.id, user_info.subject
        )

        if federated_identity:
            # Update last login
            federated_identity.last_login_at = now
            federated_identity.raw_claims = user_info.raw_claims

            # Get associated user
            existing_user = await self._repo.find_user_by_id(db, federated_identity.user_id)
            if existing_user is None:
                raise RuntimeError(
                    f"Federated identity {federated_identity.id} references missing user "
                    f"{federated_identity.user_id}"
                )

            await db.commit()
            logger.info(
                "Existing federated identity found: user_id=%s, idp_id=%s",
                existing_user.id,
                idp.id,
            )
            return existing_user, federated_identity, False

        # 2. If auto_provision is disabled, deny access
        if not idp.auto_provision:
            raise ValueError(
                "Auto-provisioning is disabled for this identity provider. "
                "Please contact your administrator to link your account."
            )

        # 3. Check for existing user by email (for account linking)
        user: User | None = None
        if user_info.email and idp.allow_linking:
            user = await self._repo.find_user_by_email(db, user_info.email)

            if user:
                logger.info(
                    "Linking federated identity to existing user: user_id=%s, email=%s",
                    user.id,
                    user_info.email,
                )

        # 4. Create new user if not found
        is_new_user = False
        if not user:
            user = User(is_active=True)
            await self._user_repo.add(db, user)
            is_new_user = True

            # Create email record if available
            if user_info.email:
                user_email = UserEmail(
                    user_id=user.id,
                    email=user_info.email.lower(),
                    is_primary=True,
                    is_verified=user_info.email_verified,
                    verified_at=now if user_info.email_verified else None,
                )
                await self._user_repo.add_email(db, user_email)

            # Create profile with user info
            profile = UserProfile(
                user_id=user.id,
                name=user_info.name,
                given_name=user_info.given_name,
                family_name=user_info.family_name,
                picture_url=user_info.picture,
                preferred_username=user_info.username,
            )
            await self._user_repo.add_profile(db, profile)

            logger.info("Created new user via JIT provisioning: user_id=%s", user.id)

        # 5. Create federated identity link
        federated_identity = FederatedIdentity(
            user_id=user.id,
            identity_provider_id=idp.id,
            external_subject=user_info.subject,
            external_email=user_info.email,
            external_username=user_info.username,
            raw_claims=user_info.raw_claims,
            linked_at=now,
            last_login_at=now,
        )
        await self._repo.add(db, federated_identity)

        # 6. Add user to tenant if not already a member
        tenant = await self._repo.find_tenant_by_slug(db, tenant_slug)

        if tenant:
            membership = await self._repo.find_tenant_membership(db, tenant.id, user.id)

            if not membership:
                default_role = await tenant_role_service.resolve_default_registration_role(
                    db, tenant.id
                )
                if default_role:
                    membership = TenantMember(
                        tenant_id=tenant.id,
                        user_id=user.id,
                        role_id=default_role.id,
                        joined_at=now,
                    )
                    await self._tenant_repo.add_member(db, membership)
                    logger.info(
                        "Added user to tenant: user_id=%s, tenant=%s, role=%s",
                        user.id,
                        tenant_slug,
                        default_role.name,
                    )
                    await dispatch_webhook_event(
                        db,
                        tenant_id=tenant.id,
                        event=WebhookEvent.MEMBER_ADDED,
                        data={
                            "tenant_id": str(tenant.id),
                            "user_id": str(user.id),
                            "role_id": str(default_role.id),
                            "role_name": default_role.name,
                            "source": "federation_auto_provision",
                            "idp_id": str(idp.id) if idp else None,
                        },
                    )
                else:
                    logger.warning(
                        "No default role found for tenant %s, user not added",
                        tenant_slug,
                    )

        await db.commit()
        await db.refresh(user)
        await db.refresh(federated_identity)

        return user, federated_identity, is_new_user

    async def _get_authorization_endpoint(self, idp: IdentityProvider) -> str:
        """Get authorization endpoint for an IdP."""
        if idp.authorization_endpoint:
            return idp.authorization_endpoint

        # Try discovery URL
        if idp.discovery_url:
            discovery = await self.fetch_oidc_discovery(idp.discovery_url)
            return discovery.authorization_endpoint

        # Fall back to provider defaults
        config = self.PROVIDER_CONFIGS.get(idp.provider_type, {})
        if "discovery_url" in config:
            discovery = await self.fetch_oidc_discovery(config["discovery_url"])
            return discovery.authorization_endpoint

        if "authorization_endpoint" in config:
            return config["authorization_endpoint"]

        raise ValueError(f"Cannot determine authorization endpoint for IdP: {idp.name}")

    async def _get_token_endpoint(self, idp: IdentityProvider) -> str:
        """Get token endpoint for an IdP."""
        if idp.token_endpoint:
            return idp.token_endpoint

        if idp.discovery_url:
            discovery = await self.fetch_oidc_discovery(idp.discovery_url)
            return discovery.token_endpoint

        config = self.PROVIDER_CONFIGS.get(idp.provider_type, {})
        if "discovery_url" in config:
            discovery = await self.fetch_oidc_discovery(config["discovery_url"])
            return discovery.token_endpoint

        if "token_endpoint" in config:
            return config["token_endpoint"]

        raise ValueError(f"Cannot determine token endpoint for IdP: {idp.name}")

    async def _get_userinfo_endpoint(self, idp: IdentityProvider) -> str | None:
        """Get userinfo endpoint for an IdP (if available)."""
        if idp.userinfo_endpoint:
            return idp.userinfo_endpoint

        if idp.discovery_url:
            discovery = await self.fetch_oidc_discovery(idp.discovery_url)
            return discovery.userinfo_endpoint

        config = self.PROVIDER_CONFIGS.get(idp.provider_type, {})
        if "discovery_url" in config:
            discovery = await self.fetch_oidc_discovery(config["discovery_url"])
            return discovery.userinfo_endpoint

        return config.get("userinfo_endpoint")

    async def _get_github_user_info(
        self, access_token: str, _claims: dict[str, Any]
    ) -> FederatedUserInfo:
        """Get user info from GitHub API.

        GitHub is not OIDC-compliant, so we need special handling.
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Get user profile
            response = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            response.raise_for_status()
            user_data = response.json()

            # Get user emails (primary email)
            email_response = await client.get(
                "https://api.github.com/user/emails",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            emails = email_response.json() if email_response.status_code == 200 else []

        # Find primary email
        primary_email = None
        email_verified = False
        for email_data in emails:
            if email_data.get("primary"):
                primary_email = email_data.get("email")
                email_verified = email_data.get("verified", False)
                break

        # Parse name
        name = user_data.get("name", "")
        name_parts = name.split(" ", 1) if name else ["", ""]
        given_name = name_parts[0] if len(name_parts) > 0 else None
        family_name = name_parts[1] if len(name_parts) > 1 else None

        return FederatedUserInfo(
            subject=str(user_data.get("id")),
            email=primary_email,
            email_verified=email_verified,
            name=name or None,
            given_name=given_name,
            family_name=family_name,
            picture=user_data.get("avatar_url"),
            username=user_data.get("login"),
            raw_claims=user_data,
        )

    def _apply_attribute_mapping(
        self, claims: dict[str, Any], mapping: dict[str, str] | None
    ) -> dict[str, Any]:
        """Apply attribute mapping to transform IdP claims to standard claims.

        Args:
            claims: Raw claims from IdP.
            mapping: Mapping from IdP claim names to standard names.
                     e.g., {"mail": "email", "displayName": "name"}

        Returns:
            Transformed claims with standard names.
        """
        if not mapping:
            return claims

        result = dict(claims)
        for idp_claim, standard_claim in mapping.items():
            if idp_claim in claims and standard_claim not in result:
                result[standard_claim] = claims[idp_claim]

        return result

    def _generate_code_challenge(self, code_verifier: str) -> str:
        """Generate S256 PKCE code challenge from verifier."""
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        import base64

        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    @staticmethod
    def generate_state() -> str:
        """Generate a secure random state parameter."""
        return secrets.token_urlsafe(32)

    @staticmethod
    def generate_nonce() -> str:
        """Generate a secure random nonce."""
        return secrets.token_urlsafe(32)

    @staticmethod
    def generate_code_verifier() -> str:
        """Generate a PKCE code verifier."""
        return secrets.token_urlsafe(64)


# Service singleton
federation_service = FederationService()
