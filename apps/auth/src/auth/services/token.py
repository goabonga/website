# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Token service for JWT creation and validation."""

import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from auth.config import settings
from auth.db.models.oauth2 import AccessToken, OAuth2Client, RefreshToken
from auth.db.repositories.token import TokenRepository
from auth.services.jwks import JWKSService
from auth.services.pairwise import PairwiseSubjectService

logger = logging.getLogger(__name__)


def generate_token() -> str:
    """Generate a random token.

    Returns:
        64-character hex string.
    """
    return secrets.token_hex(32)


def hash_token(token: str) -> str:
    """Hash a token using SHA-256.

    Args:
        token: Plain text token.

    Returns:
        SHA-256 hash of the token.
    """
    return hashlib.sha256(token.encode()).hexdigest()


class TokenService:
    """Service for creating and validating OAuth2 tokens."""

    def __init__(
        self,
        jwks_service: JWKSService,
        repository: TokenRepository | None = None,
    ) -> None:
        """Initialize the service.

        Args:
            jwks_service: JWKS service for signing tokens.
            repository: Token repository (SQL access). Defaults to a fresh
                :class:`TokenRepository` instance.
        """
        self._jwks_service = jwks_service
        self._repo = repository or TokenRepository()

    async def create_access_token(
        self,
        db: AsyncSession,
        client: OAuth2Client,
        scopes: list[str],
        user_id: uuid.UUID | None = None,
        nonce: str | None = None,
        audience: str | None = None,
        actor: dict | None = None,
        issuer: str | None = None,
    ) -> tuple[str, AccessToken]:
        """Create a new access token (JWT).

        Args:
            db: Database session.
            client: OAuth2 client.
            scopes: Token scopes.
            user_id: User ID (None for client credentials).
            nonce: OIDC nonce for ID token.
            audience: Target audience for token exchange (RFC 8693).
            actor: Actor claims for delegation (RFC 8693).
            issuer: Token issuer URL (derived from tenant config, not Host header).

        Returns:
            Tuple of (JWT string, AccessToken model).

        Raises:
            ValueError: If no active signing key is available.
        """
        # Get active signing key
        jwk = await self._jwks_service.get_active_key(db)
        if not jwk:
            raise ValueError("No active signing key available")

        # Generate token ID
        jti = str(uuid.uuid4())

        # Calculate expiration (use per-client setting if defined, otherwise global config)
        now = datetime.now(UTC)
        if client.access_token_expiry_seconds is not None:
            expires_at = now + timedelta(seconds=client.access_token_expiry_seconds)
        else:
            expires_at = now + timedelta(minutes=settings.access_token_expiry_minutes)

        # Determine subject claim — always use pairwise sub for user tokens
        if user_id is not None:
            pairwise_service = PairwiseSubjectService()
            sub = await pairwise_service.get_sub_for_client(db, user_id, client)
        else:
            sub = client.client_id

        # Build JWT payload
        # Use provided issuer (from tenant config) or fall back to settings
        effective_issuer = issuer or settings.issuer or "http://localhost:8000"
        payload: dict[str, Any] = {
            "iss": effective_issuer,
            "sub": sub,
            "aud": audience or client.client_id,
            "exp": int(expires_at.timestamp()),
            "iat": int(now.timestamp()),
            "jti": jti,
            "scope": " ".join(scopes),
            "client_id": client.client_id,
        }

        # Add nonce if provided (for OIDC)
        if nonce:
            payload["nonce"] = nonce

        # Add actor claim for delegation (RFC 8693)
        if actor:
            payload["act"] = actor

        # Sign token
        private_key = self._jwks_service.decrypt_private_key(jwk)
        token = jwt.encode(
            payload,
            private_key,
            algorithm="RS256",
            headers={"kid": jwk.kid},
        )

        # Store token metadata
        access_token = AccessToken(
            jti=jti,
            client_id=client.id,
            user_id=user_id,
            scopes=scopes,
            expires_at=expires_at,
        )
        await self._repo.add_access_token(db, access_token)

        logger.info(
            "ACTION: token_access_create, user_id=%s, client_id=%s, jti=%s",
            user_id,
            client.client_id,
            jti,
        )
        return token, access_token

    async def create_refresh_token(
        self,
        db: AsyncSession,
        access_token: AccessToken,
        client: OAuth2Client,
        user_id: uuid.UUID | None = None,
    ) -> tuple[str, RefreshToken]:
        """Create a new refresh token.

        Args:
            db: Database session.
            access_token: Associated access token.
            client: OAuth2 client.
            user_id: User ID (None for client credentials).

        Returns:
            Tuple of (plain token string, RefreshToken model).
        """
        # Generate token
        token = generate_token()
        token_hash = hash_token(token)

        # Calculate expiration (use per-client setting if defined, otherwise global config)
        if client.refresh_token_expiry_seconds is not None:
            expires_at = datetime.now(UTC) + timedelta(seconds=client.refresh_token_expiry_seconds)
        else:
            expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expiry_days)

        # Store token
        refresh_token = RefreshToken(
            token_hash=token_hash,
            access_token_id=access_token.id,
            client_id=client.id,
            user_id=user_id,
            scopes=access_token.scopes,
            expires_at=expires_at,
        )
        await self._repo.add_refresh_token(db, refresh_token)

        logger.info(
            "ACTION: token_refresh_create, user_id=%s, client_id=%s", user_id, client.client_id
        )
        return token, refresh_token

    async def create_token_pair(
        self,
        db: AsyncSession,
        client: OAuth2Client,
        scopes: list[str],
        user_id: uuid.UUID | None = None,
        nonce: str | None = None,
        audience: str | None = None,
        actor: dict | None = None,
        issuer: str | None = None,
    ) -> tuple[str, str, int]:
        """Create an access token and refresh token pair.

        Args:
            db: Database session.
            client: OAuth2 client.
            scopes: Token scopes.
            user_id: User ID (None for client credentials).
            nonce: OIDC nonce for ID token.
            audience: Target audience for token exchange (RFC 8693).
            actor: Actor claims for delegation (RFC 8693).
            issuer: Token issuer URL (derived from tenant config, not Host header).

        Returns:
            Tuple of (access_token, refresh_token, expires_in).
        """
        access_jwt, access_token = await self.create_access_token(
            db, client, scopes, user_id, nonce, audience, actor, issuer
        )
        refresh_plain, _ = await self.create_refresh_token(db, access_token, client, user_id)

        # Calculate expires_in (use per-client setting if defined, otherwise global config)
        if client.access_token_expiry_seconds is not None:
            expires_in = client.access_token_expiry_seconds
        else:
            expires_in = settings.access_token_expiry_minutes * 60

        return access_jwt, refresh_plain, expires_in

    async def get_refresh_token(
        self,
        db: AsyncSession,
        token: str,
    ) -> RefreshToken | None:
        """Get a refresh token by value.

        Args:
            db: Database session.
            token: Plain text token.

        Returns:
            RefreshToken if found and valid, None otherwise.
        """
        token_hash = hash_token(token)
        now = datetime.now(UTC)
        return await self._repo.find_valid_refresh_token_by_hash(db, token_hash, now=now)

    async def consume_refresh_token(
        self,
        db: AsyncSession,
        refresh_token: RefreshToken,
    ) -> None:
        """Mark a refresh token as used (for rotation).

        Args:
            db: Database session.
            refresh_token: Token to consume.
        """
        refresh_token.used_at = datetime.now(UTC)
        await db.flush()

    async def get_access_token_by_jti(
        self,
        db: AsyncSession,
        jti: str,
    ) -> AccessToken | None:
        """Get an access token by JTI.

        Args:
            db: Database session.
            jti: Token ID.

        Returns:
            AccessToken if found, None otherwise.
        """
        return await self._repo.find_access_token_by_jti(db, jti)

    async def revoke_access_token(
        self,
        db: AsyncSession,
        jti: str,
    ) -> bool:
        """Revoke an access token by JTI.

        Args:
            db: Database session.
            jti: Token ID.

        Returns:
            True if revoked, False if not found.
        """
        access_token = await self.get_access_token_by_jti(db, jti)

        if not access_token:
            logger.warning("Access token revocation failed: jti not found: %s", jti)
            return False

        access_token.revoked_at = datetime.now(UTC)
        await db.flush()
        logger.info("ACTION: token_access_revoke, jti=%s, user_id=%s", jti, access_token.user_id)
        return True

    async def revoke_refresh_token(
        self,
        db: AsyncSession,
        token: str,
    ) -> bool:
        """Revoke a refresh token and all associated access tokens.

        When a refresh token is revoked, all access tokens for the same
        client/user pair are also revoked to ensure complete revocation.

        Args:
            db: Database session.
            token: Plain text token.

        Returns:
            True if revoked, False if not found.
        """
        token_hash = hash_token(token)
        refresh_token = await self._repo.find_refresh_token_by_hash(db, token_hash)

        if not refresh_token:
            logger.warning("Refresh token revocation failed: token not found")
            return False

        now = datetime.now(UTC)
        refresh_token.revoked_at = now

        # Also revoke all access tokens for this client/user pair
        await self._repo.revoke_access_tokens_for_refresh_cascade(
            db,
            client_id=refresh_token.client_id,
            user_id=refresh_token.user_id,
            now=now,
        )

        await db.flush()
        logger.info(
            "ACTION: token_refresh_revoke, user_id=%s, client_id=%s",
            refresh_token.user_id,
            refresh_token.client_id,
        )
        return True

    async def refresh_tokens(
        self,
        db: AsyncSession,
        refresh_token: RefreshToken,
        client: OAuth2Client,
        scopes: list[str] | None = None,
        issuer: str | None = None,
    ) -> tuple[str, str, int]:
        """Refresh tokens using a refresh token.

        Args:
            db: Database session.
            refresh_token: Valid refresh token.
            client: OAuth2 client.
            scopes: Optional new scopes (must be subset of original).
            issuer: Token issuer URL (derived from tenant config, not Host header).

        Returns:
            Tuple of (new_access_token, new_refresh_token, expires_in).
        """
        # Use original scopes if not specified
        token_scopes = scopes or refresh_token.scopes

        # Validate scopes are subset of original
        if scopes and not set(scopes).issubset(set(refresh_token.scopes)):
            logger.warning(
                "Token refresh failed: requested scopes exceed original for client %s",
                client.client_id,
            )
            raise ValueError("Requested scopes exceed original token scopes")

        # Mark old token as used (rotation)
        await self.consume_refresh_token(db, refresh_token)

        logger.info(
            "ACTION: token_refresh, user_id=%s, client_id=%s",
            refresh_token.user_id,
            client.client_id,
        )
        # Create new token pair
        return await self.create_token_pair(
            db, client, token_scopes, refresh_token.user_id, issuer=issuer
        )

    async def validate_access_token(
        self,
        db: AsyncSession,
        token: str,
    ) -> dict[str, Any] | None:
        """Validate an access token (JWT).

        Args:
            db: Database session.
            token: JWT string.

        Returns:
            Token payload if valid, None otherwise.
        """
        try:
            # Decode header to get kid
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")

            if not kid:
                return None

            # Get the key
            jwk = await self._jwks_service.get_key_by_kid(db, kid)
            if not jwk or jwk.revoked_at:
                return None

            # Verify token
            public_key = jwk.public_key_pem
            payload = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                options={"require": ["exp", "iat", "iss", "sub", "jti"]},
            )

            # Check if token is revoked
            jti = payload.get("jti")
            if jti:
                revoked = await self._repo.find_revoked_access_token_by_jti(db, jti)
                if revoked:
                    logger.warning("Token validation failed: token has been revoked: jti=%s", jti)
                    return None

            return payload

        except jwt.InvalidTokenError as e:
            logger.warning("Token validation failed: %s", str(e))
            return None

    async def create_id_token(
        self,
        db: AsyncSession,
        client: OAuth2Client,
        user_id: uuid.UUID,
        nonce: str | None = None,
        auth_time: datetime | None = None,
        access_token: str | None = None,
        issuer: str | None = None,
    ) -> str:
        """Create an OIDC ID token.

        Args:
            db: Database session.
            client: OAuth2 client.
            user_id: User ID.
            nonce: OIDC nonce.
            auth_time: Authentication timestamp.
            access_token: Access token for at_hash claim.
            issuer: Token issuer URL (derived from tenant config, not Host header).

        Returns:
            ID token JWT string.
        """
        # Get active signing key
        jwk = await self._jwks_service.get_active_key(db)
        if not jwk:
            raise ValueError("No active signing key available")

        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=settings.id_token_expiry_minutes)

        # Always use pairwise sub for ID tokens
        pairwise_service = PairwiseSubjectService()
        sub = await pairwise_service.get_sub_for_client(db, user_id, client)

        # Build ID token payload
        # Use provided issuer (from tenant config) or fall back to settings
        effective_issuer = issuer or settings.issuer or "http://localhost:8000"
        payload: dict[str, Any] = {
            "iss": effective_issuer,
            "sub": sub,
            "aud": client.client_id,
            "exp": int(expires_at.timestamp()),
            "iat": int(now.timestamp()),
        }

        if nonce:
            payload["nonce"] = nonce

        if auth_time:
            payload["auth_time"] = int(auth_time.timestamp())

        # Add at_hash if access token provided
        if access_token:
            # Hash the access token and take first half
            token_hash = hashlib.sha256(access_token.encode()).digest()
            import base64

            at_hash = base64.urlsafe_b64encode(token_hash[:16]).rstrip(b"=").decode()
            payload["at_hash"] = at_hash

        # Sign token
        private_key = self._jwks_service.decrypt_private_key(jwk)
        return jwt.encode(
            payload,
            private_key,
            algorithm="RS256",
            headers={"kid": jwk.kid},
        )

    async def get_user_authorized_clients(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> list[dict]:
        """Get all OAuth2 clients the user has authorized.

        Returns clients that have valid (non-revoked, non-expired) tokens
        for the user.

        Args:
            db: Database session.
            user_id: User ID.

        Returns:
            List of dicts with client info, scopes, and authorization dates.
        """
        now = datetime.now(UTC)

        # Get all distinct clients with active tokens for this user.
        # Access tokens are the source of truth for authorized clients.
        client_data = await self._repo.aggregate_authorized_clients_for_user(db, user_id, now=now)

        if not client_data:
            return []

        # Get client details
        client_ids = [row.client_id for row in client_data]
        clients_list = await self._repo.find_clients_by_ids(db, client_ids)
        clients = {c.id: c for c in clients_list}

        # Get the most recent scopes for each client
        authorized_clients = []
        for row in client_data:
            client = clients.get(row.client_id)
            if not client:
                continue

            # Get the most recent active token's scopes
            scopes_row = await self._repo.find_latest_active_scopes(
                db, user_id, row.client_id, now=now
            )
            scopes = scopes_row if scopes_row else []

            authorized_clients.append(
                {
                    "client_id": client.client_id,
                    "name": client.name,
                    "description": client.description,
                    "homepage_url": client.homepage_url,
                    "scopes": scopes,
                    "authorized_at": row.first_authorized,
                    "last_used": row.last_used,
                }
            )

        return authorized_clients

    async def revoke_client_access(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        client_id: str,
    ) -> int:
        """Revoke all tokens for a specific client for a user.

        Args:
            db: Database session.
            user_id: User ID.
            client_id: OAuth2 client ID (string, not UUID).

        Returns:
            Number of tokens revoked.
        """
        now = datetime.now(UTC)

        # Find the client by client_id string
        client = await self._repo.find_client_by_string_id(db, client_id)

        if not client:
            logger.warning(
                "Client access revocation failed: client not found: %s",
                client_id,
            )
            return 0

        # Revoke all access tokens for this user/client
        access_tokens = await self._repo.list_active_access_tokens_for_user_client(
            db, user_id, client.id
        )
        for token in access_tokens:
            token.revoked_at = now

        # Revoke all refresh tokens for this user/client
        refresh_tokens = await self._repo.list_active_refresh_tokens_for_user_client(
            db, user_id, client.id
        )
        for refresh_token in refresh_tokens:
            refresh_token.revoked_at = now

        await db.flush()

        total_revoked = len(access_tokens) + len(refresh_tokens)
        logger.info(
            "ACTION: token_client_access_revoke, user_id=%s, client_id=%s, tokens_revoked=%d",
            user_id,
            client_id,
            total_revoked,
        )
        return total_revoked
