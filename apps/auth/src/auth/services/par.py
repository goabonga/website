# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Pushed Authorization Request (PAR) service (RFC 9126)."""

import logging
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from auth.config import settings
from auth.db.models.oauth2 import OAuth2Client, PARRequest
from auth.db.repositories.par import PARRepository

logger = logging.getLogger(__name__)

# PAR request URI prefix per RFC 9126
PAR_REQUEST_URI_PREFIX = "urn:ietf:params:oauth:request_uri:"


def generate_request_uri() -> str:
    """Generate a unique request_uri for PAR.

    Format: urn:ietf:params:oauth:request_uri:<random>

    Returns:
        A unique request URI string.
    """
    random_part = secrets.token_urlsafe(32)
    return f"{PAR_REQUEST_URI_PREFIX}{random_part}"


class PARService:
    """Service for managing Pushed Authorization Requests."""

    def __init__(self, repository: PARRepository | None = None) -> None:
        self._repo = repository or PARRepository()

    async def create_par_request(
        self,
        db: AsyncSession,
        client: OAuth2Client,
        response_type: str,
        redirect_uri: str,
        scopes: list[str],
        state: str | None = None,
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
        nonce: str | None = None,
        prompt: str | None = None,
    ) -> tuple[str, int]:
        """Create a new PAR request.

        Args:
            db: Database session.
            client: The OAuth2 client.
            response_type: The response type (must be "code").
            redirect_uri: The redirect URI.
            scopes: List of requested scopes.
            state: Optional state parameter.
            code_challenge: PKCE code challenge.
            code_challenge_method: PKCE challenge method.
            nonce: OIDC nonce.
            prompt: Prompt parameter.

        Returns:
            Tuple of (request_uri, expires_in seconds).
        """
        request_uri = generate_request_uri()
        expires_at = datetime.now(UTC) + timedelta(seconds=settings.par_request_expiry_seconds)

        par_request = PARRequest(
            request_uri=request_uri,
            client_id=client.id,
            response_type=response_type,
            redirect_uri=redirect_uri,
            scopes=scopes,
            state=state,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            nonce=nonce,
            prompt=prompt,
            expires_at=expires_at,
        )

        await self._repo.add(db, par_request)

        logger.info("PAR request created for client %s", client.client_id)
        return request_uri, settings.par_request_expiry_seconds

    async def get_par_request(
        self,
        db: AsyncSession,
        request_uri: str,
    ) -> PARRequest | None:
        """Get a PAR request by request_uri.

        Args:
            db: Database session.
            request_uri: The request URI to look up.

        Returns:
            The PAR request if found and valid, None otherwise.
        """
        return await self._repo.find_by_uri(db, request_uri)

    async def get_par_request_for_client(
        self,
        db: AsyncSession,
        request_uri: str,
        client_id: str,
    ) -> PARRequest | None:
        """Get a PAR request by request_uri and verify client.

        Args:
            db: Database session.
            request_uri: The request URI to look up.
            client_id: The client_id string to verify.

        Returns:
            The PAR request if found, valid, and belongs to client; None otherwise.
        """
        return await self._repo.find_by_uri_and_client(db, request_uri, client_id)

    def is_expired(self, par_request: PARRequest) -> bool:
        """Check if a PAR request has expired.

        Args:
            par_request: The PAR request to check.

        Returns:
            True if expired, False otherwise.
        """
        return datetime.now(UTC) > par_request.expires_at

    def is_used(self, par_request: PARRequest) -> bool:
        """Check if a PAR request has already been used.

        Args:
            par_request: The PAR request to check.

        Returns:
            True if used, False otherwise.
        """
        return par_request.used_at is not None

    async def mark_as_used(
        self,
        db: AsyncSession,
        par_request: PARRequest,
    ) -> None:
        """Mark a PAR request as used.

        Args:
            db: Database session.
            par_request: The PAR request to mark as used.
        """
        par_request.used_at = datetime.now(UTC)
        await db.flush()
        logger.info("PAR request consumed: id=%s", par_request.id)

    async def delete_expired(self, db: AsyncSession) -> int:
        """Delete expired PAR requests.

        Args:
            db: Database session.

        Returns:
            Number of deleted requests.
        """
        expired = await self._repo.list_expired(db, datetime.now(UTC))

        count = len(expired)
        for par in expired:
            await self._repo.delete(db, par)

        await db.flush()
        return count
