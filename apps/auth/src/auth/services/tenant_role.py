# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tenant role management service."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from auth.db.models.tenant import (
    DEFAULT_TENANT_ROLES,
    TENANT_SCOPES,
    Tenant,
    TenantCustomRole,
    TenantMember,
)
from auth.db.repositories.tenant_role import TenantRoleRepository

logger = logging.getLogger(__name__)


class TenantRoleService:
    """Service for managing tenant custom roles.

    Orchestrates tenant-role business flows. SQL access is delegated to
    :class:`TenantRoleRepository`; this service owns scope validation,
    default-role resolution and the cross-table checks before mutations.
    """

    def __init__(self, repository: TenantRoleRepository | None = None) -> None:
        self._repo = repository or TenantRoleRepository()

    async def create_default_roles(
        self,
        db: AsyncSession,
        tenant: Tenant,
    ) -> list[TenantCustomRole]:
        """Create default roles for a new tenant.

        Args:
            db: Database session.
            tenant: The tenant to create roles for.

        Returns:
            List of created roles.
        """
        roles = []
        for name, config in DEFAULT_TENANT_ROLES.items():
            role = TenantCustomRole(
                tenant_id=tenant.id,
                name=name,
                display_name=config["display_name"],
                description=config["description"],
                scopes=config["scopes"],
                is_system=config["is_system"],
                display_order=config["display_order"],
                # Mirror the migration-time backfill: "member" is the
                # out-of-the-box default for new registrants until an admin
                # picks another role.
                is_default=(name == "member"),
            )
            await self._repo.stage(db, role)
            roles.append(role)

        await self._repo.flush(db)
        logger.info("Created %d default roles for tenant %s", len(roles), tenant.id)
        return roles

    async def get_tenant_roles(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> list[TenantCustomRole]:
        """Get all roles for a tenant.

        Args:
            db: Database session.
            tenant_id: Tenant UUID.

        Returns:
            List of roles ordered by display_order.
        """
        return await self._repo.list_roles_for_tenant(db, tenant_id)

    async def get_role_by_id(
        self,
        db: AsyncSession,
        role_id: uuid.UUID,
    ) -> TenantCustomRole | None:
        """Get a role by its ID.

        Args:
            db: Database session.
            role_id: Role UUID.

        Returns:
            The role if found, None otherwise.
        """
        return await self._repo.find_by_id(db, role_id)

    async def get_role_by_name(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        name: str,
    ) -> TenantCustomRole | None:
        """Get a role by name within a tenant.

        Args:
            db: Database session.
            tenant_id: Tenant UUID.
            name: Role name.

        Returns:
            The role if found, None otherwise.
        """
        return await self._repo.find_by_name_in_tenant(db, tenant_id, name)

    async def get_owner_role(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> TenantCustomRole | None:
        """Get the owner role for a tenant.

        Args:
            db: Database session.
            tenant_id: Tenant UUID.

        Returns:
            The owner role.
        """
        return await self.get_role_by_name(db, tenant_id, "owner")

    async def resolve_default_registration_role(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> TenantCustomRole | None:
        """Return the role to assign on self-register / IdP auto-provision.

        Resolution order:
        1. The role with ``is_default=True`` on this tenant (at most one
           exists thanks to the partial unique index).
        2. Fallback: the role named ``member`` on this tenant, to preserve
           backwards compatibility with tenants that predate the flag.
        3. None: caller should log and skip the membership creation.
        """
        role = await self._repo.find_default_role(db, tenant_id)
        if role:
            return role
        return await self.get_role_by_name(db, tenant_id, "member")

    async def set_default_role(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        role_id: uuid.UUID,
    ) -> TenantCustomRole | None:
        """Atomically mark ``role_id`` as the tenant's default role.

        Clears any previous default in the same tenant first so the partial
        unique index never raises, then flips the target role on.
        Returns the updated role or ``None`` if it doesn't exist or belongs
        to another tenant.
        """
        role = await self.get_role_by_id(db, role_id)
        if not role or role.tenant_id != tenant_id:
            return None
        await self._repo.clear_default_flag(db, tenant_id, except_role_id=role.id)
        role.is_default = True
        await self._repo.flush(db)
        return role

    async def clear_default_role(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> None:
        """Remove the default flag from any role in this tenant."""
        await self._repo.clear_default_flag(db, tenant_id)
        await self._repo.flush(db)

    async def create_role(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        name: str,
        display_name: str,
        scopes: list[str],
        description: str | None = None,
        tenant: Tenant | None = None,
    ) -> TenantCustomRole:
        """Create a new custom role for a tenant.

        Args:
            db: Database session.
            tenant_id: Tenant UUID.
            name: Role name (lowercase, unique within tenant).
            display_name: Human-readable name.
            scopes: List of scope strings.
            description: Optional description.
            tenant: If provided, validate scopes against tenant's allowed list.

        Returns:
            The created role.

        Raises:
            ValueError: If role name already exists or scopes are invalid.
        """
        # Validate scopes
        await self._validate_scopes(db, scopes, tenant=tenant)

        # Normalize name
        name = name.lower().strip()
        if not name:
            raise ValueError("Role name cannot be empty")

        # Check uniqueness
        existing = await self.get_role_by_name(db, tenant_id, name)
        if existing:
            raise ValueError(f"Role '{name}' already exists")

        # Get highest display_order
        max_order = await self._repo.max_display_order(db, tenant_id)

        role = TenantCustomRole(
            tenant_id=tenant_id,
            name=name,
            display_name=display_name,
            description=description,
            scopes=scopes,
            is_system=False,
            display_order=max_order + 1,
        )
        await self._repo.add(db, role)

        logger.info("Created custom role %s for tenant %s", name, tenant_id)
        return role

    async def update_role(
        self,
        db: AsyncSession,
        role: TenantCustomRole,
        display_name: str | None = None,
        scopes: list[str] | None = None,
        description: str | None = None,
        tenant: Tenant | None = None,
    ) -> TenantCustomRole:
        """Update a custom role.

        Args:
            db: Database session.
            role: The role to update.
            display_name: New display name.
            scopes: New scopes list.
            description: New description.
            tenant: If provided, validate scopes against tenant's allowed list.

        Returns:
            The updated role.

        Raises:
            ValueError: If attempting to modify system role scopes.
        """
        if role.is_system and scopes is not None:
            raise ValueError("Cannot modify scopes of system roles")

        if display_name is not None:
            role.display_name = display_name

        if scopes is not None:
            await self._validate_scopes(db, scopes, tenant=tenant)
            role.scopes = scopes

        if description is not None:
            role.description = description

        await self._repo.flush(db)
        logger.info("Updated role %s", role.id)
        return role

    async def delete_role(
        self,
        db: AsyncSession,
        role: TenantCustomRole,
    ) -> None:
        """Delete a custom role.

        Args:
            db: Database session.
            role: The role to delete.

        Raises:
            ValueError: If role is a system role or has members assigned.
        """
        if role.is_system:
            raise ValueError("Cannot delete system roles")

        # Check if any members have this role
        member_count = await self._repo.count_members_for_role(db, role.id)

        if member_count > 0:
            raise ValueError(
                f"Cannot delete role with {member_count} assigned member(s). "
                "Reassign members first."
            )

        await self._repo.delete(db, role)
        await self._repo.flush(db)
        logger.info("Deleted role %s", role.id)

    async def get_role_member_count(
        self,
        db: AsyncSession,
        role: TenantCustomRole,
    ) -> int:
        """Get the number of members with a specific role.

        Args:
            db: Database session.
            role: The role to check.

        Returns:
            Number of members with this role.
        """
        return await self._repo.count_members_for_role(db, role.id)

    async def assign_role(
        self,
        db: AsyncSession,
        member: TenantMember,
        role: TenantCustomRole,
    ) -> TenantMember:
        """Assign a role to a tenant member.

        Args:
            db: Database session.
            member: The member to update.
            role: The new role to assign.

        Returns:
            The updated member.

        Raises:
            ValueError: If role doesn't belong to the same tenant.
        """
        if member.tenant_id != role.tenant_id:
            raise ValueError("Role does not belong to the same tenant as the member")

        member.role_id = role.id
        await self._repo.flush(db)

        logger.info(
            "Assigned role %s to member %s in tenant %s",
            role.name,
            member.user_id,
            member.tenant_id,
        )
        return member

    def get_available_scopes(self, tenant: Tenant | None = None) -> dict[str, str]:
        """Get available tenant scopes, optionally filtered by tenant config.

        Args:
            tenant: If provided, filter by tenant's allowed_scopes setting.

        Returns:
            Dictionary of scope name to description.
        """
        if tenant is None:
            return TENANT_SCOPES.copy()
        return self.get_tenant_allowed_scopes(tenant)

    def get_tenant_allowed_scopes(self, tenant: Tenant) -> dict[str, str]:
        """Get the scopes a tenant is allowed to use for custom roles.

        Reads tenant.settings["allowed_scopes"]. If absent or None,
        all TENANT_SCOPES are returned (backward compatible).
        The wildcard scope '*' is always included.

        Args:
            tenant: The tenant to check.

        Returns:
            Filtered dict of scope name to description.
        """
        settings = tenant.settings or {}
        allowed = settings.get("allowed_scopes")
        if allowed is None:
            return TENANT_SCOPES.copy()
        allowed_set = set(allowed)
        allowed_set.add("*")  # Owner wildcard always allowed
        return {k: v for k, v in TENANT_SCOPES.items() if k in allowed_set}

    async def _validate_scopes(
        self, db: AsyncSession, scopes: list[str], tenant: Tenant | None = None
    ) -> None:
        """Validate that all scopes are valid.

        Validates against tenant scopes (optionally filtered by tenant config)
        and application scopes from the database.

        Args:
            db: Database session.
            scopes: List of scopes to validate.
            tenant: If provided, restrict tenant scopes to allowed list.

        Raises:
            ValueError: If any scope is invalid.
        """
        # Get tenant scopes (filtered if tenant provided)
        if tenant:
            valid_scopes = set(self.get_tenant_allowed_scopes(tenant).keys())
        else:
            valid_scopes = set(TENANT_SCOPES.keys())

        # Get application scopes from database
        db_scope_names = await self._repo.list_active_scope_names(db)
        valid_scopes.update(db_scope_names)

        for scope in scopes:
            if scope not in valid_scopes:
                raise ValueError(f"Invalid scope: {scope}")

    def check_member_scope(
        self,
        member: TenantMember,
        required_scope: str,
    ) -> bool:
        """Check if a member has a required scope.

        Args:
            member: The tenant member.
            required_scope: The scope to check.

        Returns:
            True if member has the scope.
        """
        return member.has_scope(required_scope)

    def is_owner(self, member: TenantMember) -> bool:
        """Check if a member has owner privileges.

        Args:
            member: The tenant member.

        Returns:
            True if member is an owner (has * scope).
        """
        return member.has_scope("*")

    def is_admin_or_owner(self, member: TenantMember) -> bool:
        """Check if a member has admin or owner privileges.

        Args:
            member: The tenant member.

        Returns:
            True if member can manage the tenant.
        """
        return member.has_scope("settings:read")


# Singleton instance
tenant_role_service = TenantRoleService()
