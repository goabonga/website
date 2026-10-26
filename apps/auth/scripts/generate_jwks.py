#!/usr/bin/env python3

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Generate initial JWKS key pair in database.

Usage:
    uv run --package auth python apps/auth/scripts/generate_jwks.py

Or with options:
    uv run --package auth python apps/auth/scripts/generate_jwks.py --key-size 4096
    uv run --package auth python apps/auth/scripts/generate_jwks.py --no-activate

The JWKS_ENCRYPTION_KEY secret is read from the environment or from a
systemd credential (see ``auth.config.get_credential``).
"""

import argparse
import asyncio
import sys


async def generate_key(key_size: int, activate: bool) -> None:
    """Generate a new JWKS key pair.

    Args:
        key_size: RSA key size in bits (2048 or 4096).
        activate: Whether to activate the key immediately.
    """
    from auth.config import settings
    from auth.core.database import async_session_factory
    from auth.core.security import AESEncryption
    from auth.services.jwks import JWKSService

    # Validate encryption key is configured
    if not settings.jwks_encryption_key:
        print("Error: JWKS_ENCRYPTION_KEY is not configured")
        print()
        print("Set it via environment variable or a systemd credential.")
        print()
        print("Generate a new key with:")
        print('  python3 -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"')
        sys.exit(1)

    # Create services
    encryption = AESEncryption.from_base64(settings.jwks_encryption_key)
    jwks_service = JWKSService(encryption)

    async with async_session_factory() as db:
        # Check if active key already exists
        existing = await jwks_service.get_active_key(db)
        if existing and activate:
            print(f"Warning: An active key already exists (kid: {existing.kid})")
            response = input("Do you want to deactivate it and create a new one? [y/N]: ")
            if response.lower() != "y":
                print("Aborted.")
                return

        # Generate new key
        print(f"Generating {key_size}-bit RSA key pair...")
        jwk = await jwks_service.generate_key(db, key_size=key_size, activate=activate)

        print("\nKey generated successfully!")
        print(f"  kid: {jwk.kid}")
        print(f"  algorithm: {jwk.alg}")
        print(f"  key size: {key_size} bits")
        print(f"  active: {jwk.is_active}")
        print(f"  created: {jwk.created_at}")

        if activate:
            print("\nThis key is now active and will be used for signing tokens.")
        else:
            print("\nThis key is NOT active. Activate it from the admin JWKS page.")


def main() -> None:
    from auth.config import settings

    parser = argparse.ArgumentParser(description="Generate JWKS key pair in database")
    parser.add_argument(
        "--key-size",
        type=int,
        default=settings.jwks_key_size,
        choices=[2048, 4096],
        help=f"RSA key size in bits (default: {settings.jwks_key_size})",
    )
    parser.add_argument(
        "--no-activate",
        action="store_true",
        help="Don't activate the key (just generate)",
    )

    args = parser.parse_args()

    asyncio.run(
        generate_key(
            key_size=args.key_size,
            activate=not args.no_activate,
        )
    )


if __name__ == "__main__":
    main()
