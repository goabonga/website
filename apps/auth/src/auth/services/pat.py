# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Personal Access Token service."""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from auth.db.models.pat import PATExpirationPreset, PersonalAccessToken
from auth.db.models.tenant import WebhookEvent
from auth.db.repositories.pat import PATRepository
from auth.services.webhook import safe_dispatch as dispatch_webhook_event

logger = logging.getLogger(__name__)

# Token prefix for identification
PAT_PREFIX = "gab_pat_"

# Expiration presets in days
EXPIRATION_DAYS: dict[PATExpirationPreset, int | None] = {
    PATExpirationPreset.DAYS_7: 7,
    PATExpirationPreset.DAYS_30: 30,
    PATExpirationPreset.DAYS_60: 60,
    PATExpirationPreset.DAYS_90: 90,
    PATExpirationPreset.DAYS_365: 365,
    PATExpirationPreset.NO_EXPIRATION: None,
}


def generate_pat_token() -> str:
    """Generate a new PAT token.

    Format: gab_pat_<64_hex_chars>

    Returns:
        Full token string (only returned once at creation).
    """
    random_bytes = secrets.token_bytes(32)
    return f"{PAT_PREFIX}{random_bytes.hex()}"


def hash_pat_token(token: str) -> str:
    """Hash a PAT token for storage.

    Args:
        token: Full token string (including prefix).

    Returns:
        SHA-256 hash of the token.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def get_token_suffix(token: str) -> str:
    """Get the last 4 characters of the token for display.

    Args:
        token: Full token string.

    Returns:
        Last 4 characters of the token.
    """
    return token[-4:]


def calculate_expiration(
    preset: PATExpirationPreset,
    custom_days: int | None = None,
) -> datetime | None:
    """Calculate expiration datetime from preset.

    Args:
        preset: Expiration preset.
        custom_days: Custom days if preset is CUSTOM.

    Returns:
        Expiration datetime or None for no expiration.
    """
    if preset == PATExpirationPreset.NO_EXPIRATION:
        return None

    days: int | None
    if preset == PATExpirationPreset.CUSTOM and custom_days:
        days = custom_days
    else:
        days = EXPIRATION_DAYS.get(preset)

    if days is None:
        return None

    return datetime.now(UTC) + timedelta(days=days)


class PersonalAccessTokenService:
    """Service for managing Personal Access Tokens.

    Orchestrates PAT-related business flows (token generation, hashing,
    validation, revocation, webhook dispatch). SQL access is delegated to
    :class:`PATRepository`; this service owns transaction boundaries and
    never calls ``db.execute`` directly.
    """

    def __init__(self, repository: PATRepository | None = None) -> None:
        self._repo = repository or PATRepository()

    async def create_token(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        name: str,
        scopes: list[str],
        description: str | None = None,
        expiration_preset: PATExpirationPreset = PATExpirationPreset.DAYS_90,
        custom_expiration_days: int | None = None,
        tenant_id: uuid.UUID | None = None,
        target_client_id: uuid.UUID | None = None,
    ) -> tuple[PersonalAccessToken, str]:
        """Create a new Personal Access Token.

        Args:
            db: Database session.
            user_id: Owner user ID.
            name: Token name.
            scopes: List of scope names.
            description: Optional description.
            expiration_preset: Expiration preset.
            custom_expiration_days: Custom days if preset is CUSTOM.
            tenant_id: Optional tenant restriction.
            target_client_id: Optional client restriction.

        Returns:
            Tuple of (PersonalAccessToken model, plain token string).
            The plain token is only returned once at creation.
        """
        # Generate token
        plain_token = generate_pat_token()
        token_hash = hash_pat_token(plain_token)
        token_suffix = get_token_suffix(plain_token)

        # Calculate expiration
        expires_at = calculate_expiration(expiration_preset, custom_expiration_days)

        # Create model
        pat = PersonalAccessToken(
            user_id=user_id,
            name=name,
            description=description,
            token_hash=token_hash,
            token_suffix=token_suffix,
            scopes=scopes,
            expires_at=expires_at,
            tenant_id=tenant_id,
            target_client_id=target_client_id,
        )

        await self._repo.add(db, pat)

        logger.info(
            "ACTION: pat_create, user_id=%s, pat_id=%s, name=%s, scopes=%s",
            user_id,
            pat.id,
            name,
            scopes,
        )

        await dispatch_webhook_event(
            db,
            tenant_id=pat.tenant_id,
            event=WebhookEvent.PAT_CREATED,
            data={
                "pat_id": str(pat.id),
                "user_id": str(user_id),
                "name": name,
                "scopes": list(scopes),
                "tenant_id": str(pat.tenant_id) if pat.tenant_id else None,
                "target_client_id": str(target_client_id) if target_client_id else None,
            },
        )

        return pat, plain_token

    async def get_token_by_id(
        self,
        db: AsyncSession,
        token_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> PersonalAccessToken | None:
        """Get a PAT by ID.

        Args:
            db: Database session.
            token_id: Token UUID.
            user_id: Optional user filter (for ownership check).

        Returns:
            PersonalAccessToken or None if not found.
        """
        if user_id is not None:
            return await self._repo.find_by_id_and_user(db, token_id, user_id)
        return await self._repo.find_by_id(db, token_id)

    async def validate_token(
        self,
        db: AsyncSession,
        token: str,
        required_scope: str | None = None,
    ) -> PersonalAccessToken | None:
        """Validate a PAT and return it if valid.

        Does NOT update last_used_at - call update_token_usage separately
        to allow the caller to control the transaction.

        Args:
            db: Database session.
            token: Plain token string.
            required_scope: Optional scope to check.

        Returns:
            PersonalAccessToken if valid, None otherwise.
        """
        # Check prefix
        if not token.startswith(PAT_PREFIX):
            return None

        token_hash = hash_pat_token(token)
        now = datetime.now(UTC)

        pat = await self._repo.find_active_by_token_hash(db, token_hash, now)

        if not pat:
            return None

        # Check user is active
        if not pat.user.is_active:
            logger.warning(
                "PAT validation failed: user disabled, pat_id=%s, user_id=%s",
                pat.id,
                pat.user_id,
            )
            return None

        # Check scope if required
        if required_scope and not self._scope_matches(pat.scopes, required_scope):
            logger.warning(
                "PAT validation failed: missing scope %s, pat_id=%s",
                required_scope,
                pat.id,
            )
            return None

        return pat

    async def update_token_usage(
        self,
        db: AsyncSession,
        pat: PersonalAccessToken,
        ip_address: str | None = None,
    ) -> None:
        """Update token usage statistics.

        Args:
            db: Database session.
            pat: Token to update.
            ip_address: Client IP address.
        """
        now = datetime.now(UTC)
        pat.last_used_at = now
        pat.last_used_ip = ip_address
        pat.use_count += 1
        await db.flush()

    async def update_token_scopes(
        self,
        db: AsyncSession,
        token_id: uuid.UUID,
        user_id: uuid.UUID,
        scopes: list[str],
    ) -> PersonalAccessToken | None:
        """Update scopes for an existing PAT.

        Args:
            db: Database session.
            token_id: Token UUID.
            user_id: Owner user ID (for ownership check).
            scopes: New list of scope names.

        Returns:
            Updated PersonalAccessToken or None if not found/revoked.
        """
        pat = await self.get_token_by_id(db, token_id, user_id)
        if not pat or pat.revoked_at is not None:
            return None

        pat.scopes = scopes
        await db.flush()

        logger.info(
            "ACTION: pat_update_scopes, user_id=%s, pat_id=%s, scopes=%s",
            user_id,
            token_id,
            scopes,
        )

        return pat

    def _scope_matches(self, scopes: list[str], required: str) -> bool:
        """Check if scopes include the required scope (with wildcard support)."""
        for scope in scopes:
            if scope == required:
                return True
            if scope == "*":
                return True
            if scope.endswith(":*"):
                prefix = scope[:-1]
                if required.startswith(prefix):
                    return True
        return False

    async def list_user_tokens(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        include_revoked: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[PersonalAccessToken], int]:
        """List all PATs for a user.

        Args:
            db: Database session.
            user_id: User ID.
            include_revoked: Include revoked tokens.
            offset: Pagination offset.
            limit: Pagination limit.

        Returns:
            Tuple of (tokens list, total count).
        """
        return await self._repo.list_by_user(
            db,
            user_id,
            include_revoked=include_revoked,
            offset=offset,
            limit=limit,
        )

    async def list_all_tokens(
        self,
        db: AsyncSession,
        user_id: uuid.UUID | None = None,
        include_revoked: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[PersonalAccessToken], int]:
        """List all PATs (admin view).

        Args:
            db: Database session.
            user_id: Optional user filter.
            include_revoked: Include revoked tokens.
            offset: Pagination offset.
            limit: Pagination limit.

        Returns:
            Tuple of (tokens list, total count).
        """
        return await self._repo.list_all(
            db,
            user_id=user_id,
            include_revoked=include_revoked,
            offset=offset,
            limit=limit,
        )

    async def revoke_token(
        self,
        db: AsyncSession,
        token_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        revoked_by: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> bool:
        """Revoke a PAT.

        Args:
            db: Database session.
            token_id: Token UUID.
            user_id: Optional user filter (ownership check).
            revoked_by: User who revoked (for admin actions).
            reason: Optional revocation reason.

        Returns:
            True if revoked, False if not found.
        """
        pat = await self.get_token_by_id(db, token_id, user_id)

        if not pat:
            return False

        if pat.revoked_at:
            return True  # Already revoked

        now = datetime.now(UTC)
        pat.revoked_at = now
        pat.revoked_by = revoked_by
        pat.revocation_reason = reason

        await db.flush()

        logger.info(
            "ACTION: pat_revoke, pat_id=%s, user_id=%s, revoked_by=%s, reason=%s",
            token_id,
            pat.user_id,
            revoked_by,
            reason,
        )

        await dispatch_webhook_event(
            db,
            tenant_id=pat.tenant_id,
            event=WebhookEvent.PAT_REVOKED,
            data={
                "pat_id": str(pat.id),
                "user_id": str(pat.user_id),
                "revoked_by": str(revoked_by) if revoked_by else None,
                "reason": reason,
                "tenant_id": str(pat.tenant_id) if pat.tenant_id else None,
            },
        )

        return True

    async def regenerate_token(
        self,
        db: AsyncSession,
        token_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> tuple[PersonalAccessToken, str] | None:
        """Regenerate a PAT (revoke old, create new with same settings).

        Args:
            db: Database session.
            token_id: Token to regenerate.
            user_id: Owner user ID.

        Returns:
            Tuple of (new token model, new plain token) or None if not found.
        """
        old_pat = await self.get_token_by_id(db, token_id, user_id)

        if not old_pat:
            return None

        # Revoke old token
        await self.revoke_token(
            db,
            token_id,
            user_id,
            revoked_by=user_id,
            reason="Regenerated",
        )

        # Create new token with same settings
        new_pat, plain_token = await self.create_token(
            db=db,
            user_id=user_id,
            name=old_pat.name,
            scopes=list(old_pat.scopes),
            description=old_pat.description,
            expiration_preset=PATExpirationPreset.CUSTOM,
            custom_expiration_days=None,
            tenant_id=old_pat.tenant_id,
            target_client_id=old_pat.target_client_id,
        )

        # Copy expiration from old token (keep same expiration date)
        new_pat.expires_at = old_pat.expires_at

        logger.info(
            "ACTION: pat_regenerate, old_pat_id=%s, new_pat_id=%s, user_id=%s",
            token_id,
            new_pat.id,
            user_id,
        )

        return new_pat, plain_token

    async def bulk_revoke(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        revoked_by: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> int:
        """Revoke all PATs for a user.

        Args:
            db: Database session.
            user_id: User whose tokens to revoke.
            revoked_by: User who revoked.
            reason: Revocation reason.

        Returns:
            Number of tokens revoked.
        """
        now = datetime.now(UTC)

        tokens = await self._repo.list_active_by_user(db, user_id)

        for token in tokens:
            token.revoked_at = now
            token.revoked_by = revoked_by
            token.revocation_reason = reason

        await db.flush()

        logger.info(
            "ACTION: pat_bulk_revoke, user_id=%s, count=%d, revoked_by=%s",
            user_id,
            len(tokens),
            revoked_by,
        )

        return len(tokens)

    async def bulk_revoke_all(
        self,
        db: AsyncSession,
        revoked_by: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> int:
        """Revoke every active PAT across all users.

        Args:
            db: Database session.
            revoked_by: User who revoked (typically an admin).
            reason: Revocation reason stored on each token.

        Returns:
            Number of tokens revoked.
        """
        now = datetime.now(UTC)

        tokens = await self._repo.list_active(db)

        for token in tokens:
            token.revoked_at = now
            token.revoked_by = revoked_by
            token.revocation_reason = reason

        await db.flush()

        logger.info(
            "ACTION: pat_bulk_revoke_all, count=%d, revoked_by=%s",
            len(tokens),
            revoked_by,
        )

        return len(tokens)

    async def cleanup_expired_tokens(
        self,
        db: AsyncSession,
        expired_grace_days: int = 30,
        revoked_grace_days: int = 90,
    ) -> dict[str, int]:
        """Delete expired and revoked tokens.

        Args:
            db: Database session.
            expired_grace_days: Days to keep expired tokens.
            revoked_grace_days: Days to keep revoked tokens.

        Returns:
            Dict with counts of deleted tokens by category.
        """
        now = datetime.now(UTC)
        expired_cutoff = now - timedelta(days=expired_grace_days)
        revoked_cutoff = now - timedelta(days=revoked_grace_days)

        tokens = await self._repo.list_for_cleanup(
            db,
            expired_cutoff=expired_cutoff,
            revoked_cutoff=revoked_cutoff,
        )

        expired_count = 0
        revoked_count = 0

        for token in tokens:
            if token.revoked_at and token.revoked_at < revoked_cutoff:
                revoked_count += 1
            elif token.expires_at and token.expires_at < expired_cutoff:
                expired_count += 1
            await self._repo.delete(db, token)

        await db.flush()

        logger.info(
            "ACTION: pat_cleanup, expired_deleted=%d, revoked_deleted=%d",
            expired_count,
            revoked_count,
        )

        return {
            "expired_deleted": expired_count,
            "revoked_deleted": revoked_count,
            "total_deleted": expired_count + revoked_count,
        }
