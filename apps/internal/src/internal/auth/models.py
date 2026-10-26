# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Authentication models."""

from uuid import UUID

from pydantic import BaseModel


class User(BaseModel):
    """Authenticated user extracted from JWT claims."""

    id: UUID
    email: str | None = None
    name: str | None = None
    scopes: list[str] = []

    @classmethod
    def from_jwt_claims(cls, claims: dict) -> "User":
        """Create User from JWT claims."""
        user_id = claims.get("sub")
        if not user_id:
            raise ValueError("JWT missing 'sub' claim")

        # Extract scopes from token
        scope_str = claims.get("scope", "")
        scopes = scope_str.split() if scope_str else []

        return cls(
            id=UUID(user_id) if isinstance(user_id, str) else user_id,
            email=claims.get("email"),
            name=claims.get("name") or claims.get("preferred_username"),
            scopes=scopes,
        )

    def has_scope(self, required_scope: str) -> bool:
        """Check if user has the required scope.

        Supports wildcard matching:
        - "*" matches everything (super admin)
        - "resource:*" matches "resource:read", "resource:write", etc.
        - "internal:*" matches all internal resources (namespaces, prompts, knowledge, conversations)
        - Exact match: "knowledge:read" only matches "knowledge:read"
        """
        resource = required_scope.split(":")[0] if ":" in required_scope else required_scope

        # Internal resources that internal:* covers
        internal_resources = ("namespaces", "prompts", "knowledge", "conversations")

        for scope in self.scopes:
            # Global wildcard
            if scope == "*":
                return True
            # Exact match
            if scope == required_scope:
                return True
            # Resource wildcard (e.g., "knowledge:*" matches "knowledge:read")
            if scope == f"{resource}:*":
                return True
            # Internal wildcard matches all internal resources
            if scope == "internal:*" and resource in internal_resources:
                return True

        return False

    def has_any_scope(self, required_scopes: list[str]) -> bool:
        """Check if user has any of the required scopes."""
        return any(self.has_scope(scope) for scope in required_scopes)

    def has_all_scopes(self, required_scopes: list[str]) -> bool:
        """Check if user has all of the required scopes."""
        return all(self.has_scope(scope) for scope in required_scopes)

    def can_write(self, resource: str) -> bool:
        """Check if user can create/update a resource."""
        return self.has_scope(f"{resource}:write")

    def can_delete(self, resource: str) -> bool:
        """Check if user can delete a resource."""
        return self.has_scope(f"{resource}:delete")
