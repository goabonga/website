#!/usr/bin/env python3

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Create a user in the database.

Usage:
    cd /opt/auth
    source venv/bin/activate
    uv run --package auth python apps/auth/scripts/create_user.py --email "user@example.com" --password "securepassword"

Examples:
    # Create a basic user
    uv run --package auth python apps/auth/scripts/create_user.py \
        --email "admin@example.com" \
        --password "MySecurePassword123"

    # Create a user with profile information
    uv run --package auth python apps/auth/scripts/create_user.py \
        --email "john@example.com" \
        --password "MySecurePassword123" \
        --name "John Doe" \
        --given-name "John" \
        --family-name "Doe"

    # Create a user with verified email
    uv run --package auth python apps/auth/scripts/create_user.py \
        --email "verified@example.com" \
        --password "MySecurePassword123" \
        --verified

    # Create a user and output as JSON
    uv run --package auth python apps/auth/scripts/create_user.py \
        --email "api@example.com" \
        --password "MySecurePassword123" \
        --json
"""

import argparse
import asyncio
import getpass
import json
import sys
from datetime import UTC, datetime


async def create_user(
    email: str,
    password: str,
    is_verified: bool,
    name: str | None,
    given_name: str | None,
    family_name: str | None,
    nickname: str | None,
    output_json: bool,
) -> None:
    """Create a new user.

    Args:
        email: User email address.
        password: User password (will be hashed).
        is_verified: Whether the email is pre-verified.
        name: Full name.
        given_name: First name.
        family_name: Last name.
        nickname: Nickname.
        output_json: Output as JSON.
    """
    from auth.core.database import async_session_factory
    from auth.core.security import hash_password
    from auth.db.models.user import User, UserEmail, UserPassword, UserProfile
    from sqlalchemy import select

    async with async_session_factory() as db:
        # Check if email already exists
        existing = await db.execute(select(UserEmail).where(UserEmail.email == email.lower()))
        if existing.scalar_one_or_none():
            print(f"Error: Email '{email}' already exists", file=sys.stderr)
            sys.exit(1)

        # Create user
        user = User(is_active=True)
        db.add(user)
        await db.flush()

        # Create email
        user_email = UserEmail(
            user_id=user.id,
            email=email.lower(),
            is_verified=is_verified,
            is_primary=True,
            verified_at=datetime.now(UTC) if is_verified else None,
        )
        db.add(user_email)

        # Create password
        user_password = UserPassword(
            user_id=user.id,
            password_hash=hash_password(password),
            is_current=True,
        )
        db.add(user_password)

        # Create profile if any profile field is provided
        if any([name, given_name, family_name, nickname]):
            user_profile = UserProfile(
                user_id=user.id,
                name=name,
                given_name=given_name,
                family_name=family_name,
                nickname=nickname,
            )
            db.add(user_profile)

        await db.commit()

        if output_json:
            result = {
                "id": str(user.id),
                "email": user_email.email,
                "is_active": user.is_active,
                "is_verified": user_email.is_verified,
                "profile": {
                    "name": name,
                    "given_name": given_name,
                    "family_name": family_name,
                    "nickname": nickname,
                }
                if any([name, given_name, family_name, nickname])
                else None,
            }
            print(json.dumps(result, indent=2))
        else:
            print("\nUser created successfully!")
            print("=" * 50)
            print(f"  User ID:       {user.id}")
            print(f"  Email:         {user_email.email}")
            print(f"  Active:        {user.is_active}")
            print(f"  Verified:      {user_email.is_verified}")
            if any([name, given_name, family_name, nickname]):
                print()
                print("  Profile:")
                if name:
                    print(f"    Name:        {name}")
                if given_name:
                    print(f"    Given Name:  {given_name}")
                if family_name:
                    print(f"    Family Name: {family_name}")
                if nickname:
                    print(f"    Nickname:    {nickname}")
            print("=" * 50)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a user",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --email "user@example.com" --password "secret"
  %(prog)s --email "user@example.com" --password "secret" --verified
  %(prog)s --email "user@example.com" --password "secret" --name "John Doe"
        """,
    )

    parser.add_argument(
        "--email",
        required=True,
        help="User email address",
    )
    parser.add_argument(
        "--password",
        help="User password (will prompt if not provided)",
    )
    parser.add_argument(
        "--verified",
        action="store_true",
        help="Mark email as verified",
    )
    parser.add_argument(
        "--name",
        help="Full name",
    )
    parser.add_argument(
        "--given-name",
        help="First name",
    )
    parser.add_argument(
        "--family-name",
        help="Last name",
    )
    parser.add_argument(
        "--nickname",
        help="Nickname",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    args = parser.parse_args()

    # Prompt for password if not provided
    password = args.password
    if not password:
        password = getpass.getpass("Password: ")
        password_confirm = getpass.getpass("Confirm password: ")
        if password != password_confirm:
            print("Error: Passwords do not match", file=sys.stderr)
            sys.exit(1)

    if not password:
        print("Error: Password is required", file=sys.stderr)
        sys.exit(1)

    # Basic password validation
    if len(password) < 8:
        print("Error: Password must be at least 8 characters", file=sys.stderr)
        sys.exit(1)

    asyncio.run(
        create_user(
            email=args.email,
            password=password,
            is_verified=args.verified,
            name=args.name,
            given_name=args.given_name,
            family_name=args.family_name,
            nickname=args.nickname,
            output_json=args.json,
        )
    )


if __name__ == "__main__":
    main()
