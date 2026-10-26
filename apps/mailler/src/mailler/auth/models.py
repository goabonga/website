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
    client_id: str | None = None

    @classmethod
    def from_jwt_claims(cls, claims: dict) -> "User":
        """Create User from JWT claims.

        Handles both:
        - User tokens: sub is a UUID
        - Machine tokens (client_credentials): sub is a client_id string
        """
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

        # Detect machine client tokens:
        # 1. If client_id claim exists AND equals sub -> machine token
        # 2. If sub cannot be parsed as UUID -> machine token
        client_id = claims.get("client_id") or claims.get("azp")
        user_id: UUID | str
        is_machine = False

        if client_id and str(client_id) == str(subject):
            is_machine = True
            user_id = subject
        else:
            try:
                user_id = UUID(subject) if isinstance(subject, str) else subject
            except ValueError:
                user_id = subject
                is_machine = True

        return cls(
            id=user_id,
            email=claims.get("email"),
            name=claims.get("name") or claims.get("preferred_username"),
            scopes=scopes,
            is_machine_client=is_machine,
            client_id=client_id,
        )

    def has_scope(self, scope: str) -> bool:
        """Check if user has the required scope.

        Supports wildcard matching:
        - "*" matches everything (super admin)
        - "resource:*" matches any scope starting with "resource:" (multi-level)
        """
        if scope in self.scopes:
            return True

        for user_scope in self.scopes:
            if user_scope == "*":
                return True
            if user_scope.endswith(":*"):
                prefix = user_scope[:-1]  # e.g., "vpn:*" -> "vpn:"
                if scope.startswith(prefix):
                    return True

        return False

    def has_any_scope(self, required_scopes: list[str]) -> bool:
        """Check if user has any of the required scopes."""
        return any(self.has_scope(s) for s in required_scopes)

    def has_all_scopes(self, required_scopes: list[str]) -> bool:
        """Check if user has all of the required scopes."""
        return all(self.has_scope(s) for s in required_scopes)
