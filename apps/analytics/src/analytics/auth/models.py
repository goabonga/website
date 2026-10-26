# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Authentication models."""

from uuid import UUID

from pydantic import BaseModel


class User(BaseModel):
    """Authenticated user extracted from JWT claims.

    Supports both user tokens (with UUID subject) and machine tokens
    (client_credentials with client_id as subject).
    """

    id: UUID | str
    email: str | None = None
    name: str | None = None
    scopes: list[str] = []
    is_machine_client: bool = False

    @classmethod
    def from_jwt_claims(cls, claims: dict) -> "User":
        """Create User from JWT claims.

        Handles both:
        - User tokens: sub is a UUID
        - Machine tokens (client_credentials): sub is a client_id string
        """
        # Standard OIDC claims
        subject = claims.get("sub")
        if not subject:
            raise ValueError("JWT missing 'sub' claim")

        # Extract scopes from JWT (can be space-separated string or list)
        scope_claim = claims.get("scope", claims.get("scp", ""))
        if isinstance(scope_claim, str):
            scopes = scope_claim.split() if scope_claim else []
        elif isinstance(scope_claim, list):
            scopes = list(scope_claim)
        else:
            scopes = []

        # Try to parse subject as UUID (user token)
        # If it fails, it's a machine token with client_id as subject
        user_id: UUID | str
        is_machine = False
        try:
            user_id = UUID(subject) if isinstance(subject, str) else subject
        except ValueError:
            # Not a UUID - this is a machine client token
            user_id = subject
            is_machine = True

        return cls(
            id=user_id,
            email=claims.get("email"),
            name=claims.get("name") or claims.get("preferred_username"),
            scopes=scopes,
            is_machine_client=is_machine,
        )

    def has_scope(self, required_scope: str) -> bool:
        """Check if user has the required scope.

        Supports wildcard matching:
        - "*" matches everything (super admin)
        - "analytics:*" matches "analytics:read", "analytics:write", etc.
        - Exact match: "analytics:read" only matches "analytics:read"
        """
        resource = required_scope.split(":")[0] if ":" in required_scope else required_scope

        for scope in self.scopes:
            # Global wildcard
            if scope == "*":
                return True
            # Exact match
            if scope == required_scope:
                return True
            # Resource wildcard
            if scope == f"{resource}:*":
                return True

        return False

    def has_any_scope(self, required_scopes: list[str]) -> bool:
        """Check if user has any of the required scopes."""
        return any(self.has_scope(scope) for scope in required_scopes)

    def has_all_scopes(self, required_scopes: list[str]) -> bool:
        """Check if user has all of the required scopes."""
        return all(self.has_scope(scope) for scope in required_scopes)
