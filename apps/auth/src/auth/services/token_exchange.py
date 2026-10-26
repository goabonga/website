# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Token Exchange service (RFC 8693).

This service implements RFC 8693 OAuth 2.0 Token Exchange with scope escalation.
When a client requests scopes that are not in the subject token, the service
checks if the user has those scopes via RBAC (roles and permissions).

This allows users to authenticate with basic scopes (openid, profile, email)
and have APIs request additional scopes on their behalf based on their roles.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from auth.config import settings
from auth.db.models.oauth2 import AccessToken, OAuth2Client
from auth.db.models.rbac import Role
from auth.db.repositories.role import RoleRepository
from auth.db.repositories.token import TokenRepository

logger = logging.getLogger(__name__)

# Token types per RFC 8693
TOKEN_TYPE_ACCESS_TOKEN = "urn:ietf:params:oauth:token-type:access_token"
TOKEN_TYPE_REFRESH_TOKEN = "urn:ietf:params:oauth:token-type:refresh_token"
TOKEN_TYPE_ID_TOKEN = "urn:ietf:params:oauth:token-type:id_token"
TOKEN_TYPE_JWT = "urn:ietf:params:oauth:token-type:jwt"

# Grant type
TOKEN_EXCHANGE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:token-exchange"

# Supported subject token types
SUPPORTED_SUBJECT_TOKEN_TYPES = [
    TOKEN_TYPE_ACCESS_TOKEN,
    TOKEN_TYPE_JWT,
]

# Supported requested token types
SUPPORTED_REQUESTED_TOKEN_TYPES = [
    TOKEN_TYPE_ACCESS_TOKEN,
    TOKEN_TYPE_JWT,
]


class TokenExchangeError(Exception):
    """Token exchange error."""

    def __init__(self, error: str, description: str):
        self.error = error
        self.description = description
        super().__init__(description)


class TokenExchangeService:
    """Service for OAuth2 Token Exchange (RFC 8693)."""

    def __init__(
        self,
        repository: TokenRepository | None = None,
        role_repository: RoleRepository | None = None,
    ) -> None:
        """Initialize the service.

        Args:
            repository: Token repository (SQL access). Defaults to a fresh
                :class:`TokenRepository` instance.
            role_repository: Role repository used to look up RBAC
                assignments for scope escalation. Defaults to a fresh
                :class:`RoleRepository` instance.
        """
        self._repo = repository or TokenRepository()
        self._role_repo = role_repository or RoleRepository()

    async def validate_subject_token(
        self,
        db: AsyncSession,
        subject_token: str,
        subject_token_type: str,
        client: OAuth2Client,  # noqa: ARG002
    ) -> tuple[AccessToken | None, uuid.UUID | None, list[str]]:
        """Validate the subject token.

        Args:
            db: Database session.
            subject_token: The subject token to validate.
            subject_token_type: The type of the subject token.
            client: The requesting client.

        Returns:
            Tuple of (access_token_record, user_id, scopes).

        Raises:
            TokenExchangeError: If validation fails.
        """
        if subject_token_type not in SUPPORTED_SUBJECT_TOKEN_TYPES:
            logger.warning(
                "Token exchange failed: unsupported subject_token_type %s", subject_token_type
            )
            raise TokenExchangeError(
                "invalid_request",
                f"Unsupported subject_token_type: {subject_token_type}",
            )

        if subject_token_type == TOKEN_TYPE_ACCESS_TOKEN:
            # Look up the access token by JTI
            # The subject_token is the JWT, we need to extract the JTI
            import jwt

            try:
                # Decode without verification to get the JTI
                unverified = jwt.decode(
                    subject_token,
                    options={"verify_signature": False},
                )
                jti = unverified.get("jti")
                if not jti:
                    raise TokenExchangeError(
                        "invalid_request",
                        "Subject token missing jti claim",
                    )

                # Look up the token in the database
                token_record = await self._repo.find_active_access_token_by_jti(db, jti)

                if not token_record:
                    logger.warning("Token exchange failed: subject token not found or revoked")
                    raise TokenExchangeError(
                        "invalid_request",
                        "Subject token not found or revoked",
                    )

                # Check if expired
                if token_record.expires_at < datetime.now(UTC):
                    logger.warning("Token exchange failed: subject token expired")
                    raise TokenExchangeError(
                        "invalid_request",
                        "Subject token has expired",
                    )

                logger.info(
                    "Token exchange: subject token validated for user %s", token_record.user_id
                )
                return token_record, token_record.user_id, token_record.scopes

            except jwt.DecodeError as e:
                raise TokenExchangeError(
                    "invalid_request",
                    f"Failed to decode subject token: {e}",
                )

        elif subject_token_type == TOKEN_TYPE_JWT:
            # For JWT type, we just decode and extract claims
            # The token should be a valid JWT from a trusted issuer
            import jwt

            try:
                unverified = jwt.decode(
                    subject_token,
                    options={"verify_signature": False},
                )
                sub = unverified.get("sub")
                scope = unverified.get("scope", "")
                scopes = scope.split() if scope else []

                # Try to parse sub as UUID for user_id
                user_id = None
                if sub:
                    import contextlib

                    with contextlib.suppress(ValueError):
                        user_id = uuid.UUID(sub)

                return None, user_id, scopes

            except jwt.DecodeError as e:
                raise TokenExchangeError(
                    "invalid_request",
                    f"Failed to decode subject token: {e}",
                )

        raise TokenExchangeError(
            "invalid_request",
            "Unable to validate subject token",
        )

    def validate_actor_token(
        self,
        actor_token: str | None,
        actor_token_type: str | None,
    ) -> dict | None:
        """Validate the optional actor token.

        Args:
            actor_token: The actor token (optional).
            actor_token_type: The type of the actor token.

        Returns:
            Actor claims or None.

        Raises:
            TokenExchangeError: If validation fails.
        """
        if not actor_token:
            return None

        if not actor_token_type:
            raise TokenExchangeError(
                "invalid_request",
                "actor_token_type is required when actor_token is provided",
            )

        import jwt

        try:
            # Decode without verification to extract claims
            unverified = jwt.decode(
                actor_token,
                options={"verify_signature": False},
            )
            return {
                "sub": unverified.get("sub"),
                "client_id": unverified.get("client_id") or unverified.get("azp"),
            }
        except jwt.DecodeError as e:
            raise TokenExchangeError(
                "invalid_request",
                f"Failed to decode actor token: {e}",
            )

    async def get_user_scopes_from_roles(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> list[Role]:
        """Get all roles assigned to a user with their scopes.

        Args:
            db: Database session.
            user_id: The user's UUID.

        Returns:
            List of Role objects with scopes loaded.
        """
        user_roles = await self._role_repo.list_user_role_assignments_with_scopes(db, user_id)

        # Filter out expired role assignments
        roles = []
        for ur in user_roles:
            if not ur.is_expired:
                roles.append(ur.role)

        return roles

    def user_has_scope(self, roles: list[Role], required_scope: str) -> bool:
        """Check if user has a scope via their roles.

        Supports wildcard matching:
        - "*" matches everything
        - "users:*" matches "users:read", "users:write", etc.

        Args:
            roles: List of Role objects with scopes loaded.
            required_scope: The scope to check.

        Returns:
            True if the user has the scope.
        """
        return any(role.has_scope(required_scope) for role in roles)

    def scope_matches_allowed(self, scope: str, allowed_scopes: list[str]) -> bool:
        """Check if a scope is allowed by the client's allowed_scopes list.

        Supports wildcard matching in allowed_scopes:
        - "*" matches everything
        - "users:*" matches "users:read", "users:write", etc.
        - a group scope of the ``SCOPE_GROUPS`` setting matches the scopes of its resources

        Args:
            scope: The scope to check (e.g., "conversations:read").
            allowed_scopes: List of allowed scopes (may contain wildcards).

        Returns:
            True if the scope is allowed.
        """
        resource = scope.split(":")[0] if ":" in scope else scope

        for allowed in allowed_scopes:
            # Global wildcard
            if allowed == "*":
                return True
            # Exact match
            if allowed == scope:
                return True
            # Resource wildcard (e.g., "conversations:*" matches "conversations:read")
            if allowed == f"{resource}:*":
                return True
            # Group scope declared in the settings (SCOPE_GROUPS): it stands for every scope
            # of the listed resources
            if resource in settings.scope_groups.get(allowed, ()):
                return True

        return False

    async def determine_scopes(
        self,
        db: AsyncSession,
        requested_scope: str | None,
        subject_scopes: list[str],
        client: OAuth2Client,
        user_id: uuid.UUID | None = None,
    ) -> list[str]:
        """Determine the scopes for the exchanged token.

        This method implements scope escalation: if a client requests scopes
        that are not in the subject token but ARE in the client's allowed_scopes,
        we check if the user has those scopes via RBAC.

        Flow:
        1. Parse requested scopes (or use subject token scopes)
        2. Filter to scopes allowed for the client
        3. For each scope NOT in subject token, check user's RBAC permissions
        4. Grant scope if: in subject token OR user has permission via roles

        Args:
            db: Database session.
            requested_scope: Space-separated requested scopes.
            subject_scopes: Scopes from the subject token.
            client: The requesting client.
            user_id: The user's UUID (for RBAC lookup).

        Returns:
            List of granted scopes.

        Raises:
            TokenExchangeError: If scope validation fails.
        """
        requested_scopes = requested_scope.split() if requested_scope else subject_scopes

        # Filter to scopes allowed for the client (supports wildcards)
        client_allowed = [
            s for s in requested_scopes if self.scope_matches_allowed(s, client.allowed_scopes)
        ]

        if not client_allowed and requested_scopes:
            logger.warning(
                "Token exchange failed: requested scopes not allowed for client %s",
                client.client_id,
            )
            raise TokenExchangeError(
                "invalid_scope",
                "Requested scopes not allowed for this client",
            )

        # If no user_id, we can only grant scopes from subject token
        if not user_id:
            granted_scopes = [s for s in client_allowed if s in subject_scopes]
            if not granted_scopes and client_allowed:
                raise TokenExchangeError(
                    "invalid_scope",
                    "Cannot escalate scopes without user identity",
                )
            return granted_scopes

        # Load user's roles for RBAC check
        user_roles = await self.get_user_scopes_from_roles(db, user_id)

        granted_scopes = []
        denied_scopes = []

        for scope in client_allowed:
            # Scope is granted if:
            # 1. It's already in the subject token, OR
            # 2. The user has permission via RBAC
            if scope in subject_scopes:
                granted_scopes.append(scope)
                logger.debug("Scope %s granted (in subject token)", scope)
            elif self.user_has_scope(user_roles, scope):
                granted_scopes.append(scope)
                logger.debug("Scope %s granted (via RBAC)", scope)
            else:
                denied_scopes.append(scope)
                logger.debug("Scope %s denied (not authorized)", scope)

        if denied_scopes:
            logger.warning(
                "Token exchange: user %s denied scopes %s (not in subject token or RBAC)",
                user_id,
                denied_scopes,
            )

        if not granted_scopes and client_allowed:
            raise TokenExchangeError(
                "insufficient_scope",
                f"User does not have permission for requested scopes: {', '.join(denied_scopes)}",
            )

        logger.info(
            "Token exchange: granted scopes %s for user %s (escalated: %s)",
            granted_scopes,
            user_id,
            [s for s in granted_scopes if s not in subject_scopes],
        )

        return granted_scopes

    def validate_audience(
        self,
        audience: str | None,
        resource: str | None,
    ) -> str | None:
        """Validate and determine the target audience.

        Args:
            audience: Requested audience (logical name).
            resource: Requested resource (URI).

        Returns:
            The target audience/resource.
        """
        # For now, we just pass through the audience or resource
        # In a production system, you'd validate these against registered services
        return audience or resource
