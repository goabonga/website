# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""OAuth2 client service."""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from builtins import list as BuiltinList
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy.ext.asyncio import AsyncSession

from auth.config import settings
from auth.db.models.oauth2 import AuthorizationCode, OAuth2Client
from auth.db.repositories.client import OAuth2ClientRepository

logger = logging.getLogger(__name__)


def generate_client_id() -> str:
    """Generate a random client ID.

    Returns:
        32-character hex string.
    """
    return secrets.token_hex(16)


def generate_client_secret() -> str:
    """Generate a random client secret.

    Returns:
        64-character hex string.
    """
    return secrets.token_hex(32)


def generate_authorization_code() -> str:
    """Generate a random authorization code.

    Returns:
        64-character hex string.
    """
    return secrets.token_hex(32)


def hash_code(code: str) -> str:
    """Hash a code using SHA-256.

    Args:
        code: Plain text code.

    Returns:
        SHA-256 hash of the code.
    """
    return hashlib.sha256(code.encode()).hexdigest()


class OAuth2ClientService:
    """Service for OAuth2 client operations.

    Orchestrates client-related business flows (secret hashing, redirect URI
    validation, scope/grant checks, authorization code issuance). SQL access
    to ``oauth2_clients`` is delegated to :class:`OAuth2ClientRepository`.
    """

    def __init__(self, repository: OAuth2ClientRepository | None = None) -> None:
        """Initialize the service.

        Args:
            repository: Optional repository instance. Defaults to a fresh
                :class:`OAuth2ClientRepository` (stateless, safe to share).
        """
        self._hasher = PasswordHasher()
        self._repo = repository or OAuth2ClientRepository()

    # ------------------------------------------------------------------
    # Read passthroughs (delegate to repository)
    # ------------------------------------------------------------------

    async def get_client_by_client_id(
        self,
        db: AsyncSession,
        client_id: str,
    ) -> OAuth2Client | None:
        """Get a client by its public ``client_id`` string."""
        return await self._repo.find_by_client_id(db, client_id)

    async def get_by_id(
        self,
        db: AsyncSession,
        client_uuid: uuid.UUID,
    ) -> OAuth2Client | None:
        """Get a client by its internal UUID."""
        return await self._repo.find_by_id(db, client_uuid)

    async def get_by_id_or_client_id(
        self,
        db: AsyncSession,
        identifier: str,
    ) -> OAuth2Client | None:
        """Get a client by either UUID or public ``client_id`` string."""
        return await self._repo.find_by_id_or_client_id(db, identifier)

    async def get_scoped_to_tenant(
        self,
        db: AsyncSession,
        client_uuid: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> OAuth2Client | None:
        """Get a client by internal UUID scoped to ``tenant_id``."""
        return await self._repo.find_scoped_to_tenant(db, client_uuid, tenant_id)

    async def list(
        self,
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
        tenant_id: uuid.UUID | None = None,
        filter_no_tenant: bool = False,
        search: str | None = None,
    ) -> tuple[BuiltinList[OAuth2Client], int]:
        """List clients with filters and pagination. See OAuth2ClientRepository.list."""
        return await self._repo.list(
            db,
            page=page,
            page_size=page_size,
            tenant_id=tenant_id,
            filter_no_tenant=filter_no_tenant,
            search=search,
        )

    async def count(
        self,
        db: AsyncSession,
        *,
        is_active: bool | None = None,
    ) -> int:
        """Count OAuth2 clients, optionally restricted by ``is_active``."""
        return await self._repo.count(db, is_active=is_active)

    async def list_active_cors_tuples(
        self,
        db: AsyncSession,
    ) -> BuiltinList[tuple[BuiltinList[str] | None, BuiltinList[str]]]:
        """List ``(allowed_origins, redirect_uris)`` for every active client.

        Used by the CORS middleware; thin passthrough to the repository.
        """
        return await self._repo.list_active_cors_tuples(db)

    async def add(self, db: AsyncSession, client: OAuth2Client) -> None:
        """Stage a new client row and flush to obtain its generated ID."""
        await self._repo.add(db, client)

    async def delete(self, db: AsyncSession, client: OAuth2Client) -> None:
        """Stage a client deletion (caller owns the commit)."""
        await self._repo.delete(db, client)

    async def create_client(
        self,
        db: AsyncSession,
        name: str,
        redirect_uris: BuiltinList[str],
        allowed_scopes: BuiltinList[str] | None = None,
        allowed_grant_types: BuiltinList[str] | None = None,
        is_confidential: bool = True,
        require_pkce: bool = True,
        require_consent: bool = True,
        description: str | None = None,
        allowed_origins: BuiltinList[str] | None = None,
    ) -> tuple[OAuth2Client, str | None]:
        """Create a new OAuth2 client.

        Args:
            db: Database session.
            name: Client name.
            redirect_uris: List of allowed redirect URIs.
            allowed_scopes: List of allowed scopes.
            allowed_grant_types: List of allowed grant types.
            is_confidential: Whether the client is confidential.
            require_pkce: Whether PKCE is required.
            require_consent: Whether user consent is required.
            description: Client description.
            allowed_origins: List of allowed CORS origins for browser-based flows.

        Returns:
            Tuple of (OAuth2Client, client_secret or None for public clients).
        """
        client_id = generate_client_id()
        client_secret = None
        client_secret_hash = None

        if is_confidential:
            client_secret = generate_client_secret()
            client_secret_hash = self._hasher.hash(client_secret)

        client = OAuth2Client(
            client_id=client_id,
            client_secret_hash=client_secret_hash,
            name=name,
            description=description,
            redirect_uris=redirect_uris,
            allowed_scopes=allowed_scopes or ["openid", "profile", "email"],
            allowed_grant_types=allowed_grant_types or ["authorization_code", "refresh_token"],
            is_confidential=is_confidential,
            require_pkce=require_pkce,
            require_consent=require_consent,
            allowed_origins=allowed_origins,
        )

        await self._repo.add(db, client)

        logger.info(
            "OAuth2 client created: client_id=%s name=%s confidential=%s",
            client.client_id,
            name,
            is_confidential,
        )
        return client, client_secret

    def verify_client_secret(
        self,
        client: OAuth2Client,
        secret: str,
    ) -> bool:
        """Verify a client secret.

        Args:
            client: The OAuth2 client.
            secret: The secret to verify.

        Returns:
            True if the secret is valid.
        """
        if not client.client_secret_hash:
            logger.warning(
                "Client secret verification failed: no secret configured for client %s",
                client.client_id,
            )
            return False

        try:
            self._hasher.verify(client.client_secret_hash, secret)
            return True
        except VerifyMismatchError:
            logger.warning(
                "Client secret verification failed: invalid secret for client %s", client.client_id
            )
            return False
        except InvalidHashError:
            logger.error(
                "Client secret verification failed: invalid hash format for client %s",
                client.client_id,
            )
            return False

    def validate_redirect_uri(
        self,
        client: OAuth2Client,
        redirect_uri: str,
    ) -> bool:
        """Validate a redirect URI against client's allowed URIs.

        Args:
            client: The OAuth2 client.
            redirect_uri: The redirect URI to validate.

        Returns:
            True if the redirect URI is allowed.
        """
        return redirect_uri in client.redirect_uris

    def validate_scopes(
        self,
        client: OAuth2Client,
        scopes: BuiltinList[str],
    ) -> bool:
        """Validate requested scopes against client's allowed scopes.

        Supports wildcard matching:
        - "*" matches any scope (super admin)
        - "resource:*" matches "resource:read", "resource:write", etc.
        - "module:resource:*" matches "module:resource:action", etc.

        Args:
            client: The OAuth2 client.
            scopes: The requested scopes.

        Returns:
            True if all scopes are allowed.
        """
        allowed_scopes = client.allowed_scopes or []
        if not scopes:
            return True
        if not allowed_scopes:
            return False
        return all(self._scope_matches(scope, allowed_scopes) for scope in scopes)

    def _scope_matches(self, scope: str, allowed_scopes: BuiltinList[str]) -> bool:
        """Check if a scope matches any of the allowed scopes.

        Args:
            scope: The scope to check.
            allowed_scopes: List of allowed scopes (may contain wildcards).

        Returns:
            True if the scope is allowed.
        """
        # Exact match
        if scope in allowed_scopes:
            return True

        # Global wildcard
        if "*" in allowed_scopes:
            return True

        # Check wildcard patterns (e.g., "billing:*" matches "billing:write")
        scope_parts = scope.split(":")
        if len(scope_parts) >= 2:
            # Build wildcard patterns from most specific to least specific
            # e.g., for "module:resource:action":
            #   - "module:resource:*"
            #   - "module:*"
            for i in range(len(scope_parts) - 1, 0, -1):
                wildcard = ":".join(scope_parts[:i]) + ":*"
                if wildcard in allowed_scopes:
                    return True

        return False

    def validate_grant_type(
        self,
        client: OAuth2Client,
        grant_type: str,
    ) -> bool:
        """Validate a grant type against client's allowed grant types.

        Args:
            client: The OAuth2 client.
            grant_type: The grant type to validate.

        Returns:
            True if the grant type is allowed.
        """
        allowed_grant_types = client.allowed_grant_types or []
        return grant_type in allowed_grant_types

    async def create_authorization_code(
        self,
        db: AsyncSession,
        client: OAuth2Client,
        user_id: str,
        redirect_uri: str,
        scopes: BuiltinList[str],
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
        nonce: str | None = None,
        state: str | None = None,
    ) -> str:
        """Create an authorization code.

        Args:
            db: Database session.
            client: The OAuth2 client.
            user_id: The user ID.
            redirect_uri: The redirect URI.
            scopes: The authorized scopes.
            code_challenge: PKCE code challenge.
            code_challenge_method: PKCE challenge method.
            nonce: OIDC nonce.
            state: OAuth2 state.

        Returns:
            The plain text authorization code.
        """
        code = generate_authorization_code()
        code_hash = hash_code(code)

        auth_code = AuthorizationCode(
            code_hash=code_hash,
            client_id=client.id,
            user_id=user_id,
            redirect_uri=redirect_uri,
            scopes=scopes,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            nonce=nonce,
            state=state,
            expires_at=datetime.now(UTC)
            + timedelta(minutes=settings.authorization_code_expiry_minutes),
        )

        await self._repo.add_authorization_code(db, auth_code)

        logger.info("Authorization code created for client %s user %s", client.client_id, user_id)
        return code

    async def get_authorization_code(
        self,
        db: AsyncSession,
        code: str,
    ) -> AuthorizationCode | None:
        """Get an authorization code by code value.

        Args:
            db: Database session.
            code: The plain text authorization code.

        Returns:
            AuthorizationCode if found and valid, None otherwise.
        """
        code_hash = hash_code(code)
        return await self._repo.find_valid_authorization_code(db, code_hash)

    async def consume_authorization_code(
        self,
        db: AsyncSession,
        auth_code: AuthorizationCode,
    ) -> None:
        """Mark an authorization code as used.

        Args:
            db: Database session.
            auth_code: The authorization code to consume.
        """
        auth_code.used_at = datetime.now(UTC)
        await db.flush()
        logger.info("Authorization code consumed: id=%s", auth_code.id)
