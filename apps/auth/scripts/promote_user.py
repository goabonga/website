#!/usr/bin/env python3

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Promote a user by assigning a role.

Usage:
    cd /opt/auth
    source venv/bin/activate
    uv run --package auth python apps/auth/scripts/promote_user.py --email "user@example.com" --role "super_admin"

Examples:
    # Promote user to super_admin
    uv run --package auth python apps/auth/scripts/promote_user.py \
        --email "admin@example.com" \
        --role "super_admin"

    # Promote user to admin role
    uv run --package auth python apps/auth/scripts/promote_user.py \
        --email "manager@example.com" \
        --role "admin"

    # List available roles
    uv run --package auth python apps/auth/scripts/promote_user.py --list-roles

    # Show user's current roles
    uv run --package auth python apps/auth/scripts/promote_user.py --email "user@example.com" --show

    # Remove a role from user
    uv run --package auth python apps/auth/scripts/promote_user.py \
        --email "user@example.com" \
        --role "admin" \
        --remove

    # Output as JSON
    uv run --package auth python apps/auth/scripts/promote_user.py \
        --email "user@example.com" \
        --role "admin" \
        --json
"""

import argparse
import asyncio
import json
import sys


async def list_roles(output_json: bool) -> None:
    """List all available roles.

    Args:
        output_json: Output as JSON.
    """
    from auth.core.database import async_session_factory
    from auth.db.models.rbac import Role, RoleScope
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    async with async_session_factory() as db:
        result = await db.execute(
            select(Role)
            .options(selectinload(Role.role_scopes).selectinload(RoleScope.scope))
            .order_by(Role.is_system.desc(), Role.name)
        )
        roles = result.scalars().all()

        if output_json:
            roles_data = [
                {
                    "name": role.name,
                    "description": role.description,
                    "scopes": role.get_all_scope_names(),
                    "is_system": role.is_system,
                }
                for role in roles
            ]
            print(json.dumps({"roles": roles_data}, indent=2))
        else:
            print("\nAvailable Roles:")
            print("=" * 60)
            for role in roles:
                role_type = "[SYSTEM]" if role.is_system else "[CUSTOM]"
                print(f"  {role.name:20} {role_type}")
                if role.description:
                    print(f"    {role.description}")
                scopes = role.get_all_scope_names()
                if scopes:
                    print(f"    Scopes: {', '.join(scopes)}")
                print()


async def show_user_roles(email: str, output_json: bool) -> None:
    """Show roles assigned to a user.

    Args:
        email: User email address.
        output_json: Output as JSON.
    """
    from auth.core.database import async_session_factory
    from auth.db.models.rbac import Role, RoleScope, UserRole
    from auth.db.models.user import User, UserEmail
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    async with async_session_factory() as db:
        # Find user by email
        result = await db.execute(
            select(User)
            .join(UserEmail, UserEmail.user_id == User.id)
            .where(UserEmail.email == email.lower())
        )
        user = result.scalar_one_or_none()

        if not user:
            print(f"Error: User with email '{email}' not found", file=sys.stderr)
            sys.exit(1)

        # Get user's roles with their scopes
        roles_result = await db.execute(
            select(Role, UserRole)
            .join(UserRole, UserRole.role_id == Role.id)
            .options(selectinload(Role.role_scopes).selectinload(RoleScope.scope))
            .where(UserRole.user_id == user.id)
            .order_by(Role.name)
        )
        roles_data = roles_result.all()

        if output_json:
            roles_list = [
                {
                    "name": role.name,
                    "description": role.description,
                    "scopes": role.get_all_scope_names(),
                    "is_system": role.is_system,
                    "assigned_at": user_role.created_at.isoformat()
                    if user_role.created_at
                    else None,
                    "expires_at": user_role.expires_at.isoformat()
                    if user_role.expires_at
                    else None,
                }
                for role, user_role in roles_data
            ]
            print(
                json.dumps(
                    {
                        "user_id": str(user.id),
                        "email": email,
                        "roles": roles_list,
                    },
                    indent=2,
                )
            )
        else:
            print(f"\nRoles for {email}:")
            print("=" * 60)
            if roles_data:
                for role, user_role in roles_data:
                    role_type = "[SYSTEM]" if role.is_system else "[CUSTOM]"
                    print(f"  {role.name:20} {role_type}")
                    if role.description:
                        print(f"    {role.description}")
                    if user_role.expires_at:
                        print(f"    Expires: {user_role.expires_at}")
            else:
                print("  No roles assigned")
            print()


async def assign_role(email: str, role_name: str, output_json: bool) -> None:
    """Assign a role to a user.

    Args:
        email: User email address.
        role_name: Role name to assign.
        output_json: Output as JSON.
    """
    from auth.core.database import async_session_factory
    from auth.db.models.rbac import Role, RoleScope, UserRole
    from auth.db.models.user import User, UserEmail
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    async with async_session_factory() as db:
        # Find user by email
        result = await db.execute(
            select(User)
            .join(UserEmail, UserEmail.user_id == User.id)
            .where(UserEmail.email == email.lower())
        )
        user = result.scalar_one_or_none()

        if not user:
            print(f"Error: User with email '{email}' not found", file=sys.stderr)
            sys.exit(1)

        # Find role by name with scopes
        role_result = await db.execute(
            select(Role)
            .options(selectinload(Role.role_scopes).selectinload(RoleScope.scope))
            .where(Role.name == role_name)
        )
        role = role_result.scalar_one_or_none()

        if not role:
            print(f"Error: Role '{role_name}' not found", file=sys.stderr)
            print("Use --list-roles to see available roles", file=sys.stderr)
            sys.exit(1)

        # Check if already assigned
        existing = await db.execute(
            select(UserRole).where(UserRole.user_id == user.id).where(UserRole.role_id == role.id)
        )
        if existing.scalar_one_or_none():
            print(f"Error: User already has role '{role_name}'", file=sys.stderr)
            sys.exit(1)

        # Assign role
        user_role = UserRole(
            user_id=user.id,
            role_id=role.id,
        )
        db.add(user_role)
        await db.commit()

        scopes = role.get_all_scope_names()
        if output_json:
            print(
                json.dumps(
                    {
                        "success": True,
                        "user_id": str(user.id),
                        "email": email,
                        "role": role_name,
                        "scopes": scopes,
                    },
                    indent=2,
                )
            )
        else:
            print("\nRole assigned successfully!")
            print("=" * 50)
            print(f"  User:    {email}")
            print(f"  Role:    {role_name}")
            print(f"  Scopes:  {', '.join(scopes)}")
            print("=" * 50)


async def remove_role(email: str, role_name: str, output_json: bool) -> None:
    """Remove a role from a user.

    Args:
        email: User email address.
        role_name: Role name to remove.
        output_json: Output as JSON.
    """
    from auth.core.database import async_session_factory
    from auth.db.models.rbac import Role, UserRole
    from auth.db.models.user import User, UserEmail
    from sqlalchemy import select

    async with async_session_factory() as db:
        # Find user by email
        result = await db.execute(
            select(User)
            .join(UserEmail, UserEmail.user_id == User.id)
            .where(UserEmail.email == email.lower())
        )
        user = result.scalar_one_or_none()

        if not user:
            print(f"Error: User with email '{email}' not found", file=sys.stderr)
            sys.exit(1)

        # Find role by name
        role_result = await db.execute(select(Role).where(Role.name == role_name))
        role = role_result.scalar_one_or_none()

        if not role:
            print(f"Error: Role '{role_name}' not found", file=sys.stderr)
            sys.exit(1)

        # Find assignment
        assignment = await db.execute(
            select(UserRole).where(UserRole.user_id == user.id).where(UserRole.role_id == role.id)
        )
        user_role = assignment.scalar_one_or_none()

        if not user_role:
            print(f"Error: User does not have role '{role_name}'", file=sys.stderr)
            sys.exit(1)

        # Remove role
        await db.delete(user_role)
        await db.commit()

        if output_json:
            print(
                json.dumps(
                    {
                        "success": True,
                        "user_id": str(user.id),
                        "email": email,
                        "role_removed": role_name,
                    },
                    indent=2,
                )
            )
        else:
            print("\nRole removed successfully!")
            print("=" * 50)
            print(f"  User:    {email}")
            print(f"  Role:    {role_name} (removed)")
            print("=" * 50)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Promote a user by assigning a role",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --email "user@example.com" --role "super_admin"
  %(prog)s --email "user@example.com" --role "admin" --remove
  %(prog)s --email "user@example.com" --show
  %(prog)s --list-roles
        """,
    )

    parser.add_argument(
        "--email",
        help="User email address",
    )
    parser.add_argument(
        "--role",
        help="Role name to assign/remove",
    )
    parser.add_argument(
        "--remove",
        action="store_true",
        help="Remove the role instead of assigning",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Show user's current roles",
    )
    parser.add_argument(
        "--list-roles",
        action="store_true",
        help="List all available roles",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    args = parser.parse_args()

    # List roles mode
    if args.list_roles:
        asyncio.run(list_roles(output_json=args.json))
        return

    # Email is required for other operations
    if not args.email:
        parser.error("--email is required (unless using --list-roles)")

    # Show user roles mode
    if args.show:
        asyncio.run(show_user_roles(email=args.email, output_json=args.json))
        return

    # Role is required for assign/remove
    if not args.role:
        parser.error("--role is required (unless using --show or --list-roles)")

    # Remove or assign role
    if args.remove:
        asyncio.run(remove_role(email=args.email, role_name=args.role, output_json=args.json))
    else:
        asyncio.run(assign_role(email=args.email, role_name=args.role, output_json=args.json))


if __name__ == "__main__":
    main()
