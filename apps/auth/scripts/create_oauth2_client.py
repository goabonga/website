#!/usr/bin/env python3

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Create an OAuth2 client in the database.

Usage:
    cd /opt/auth
    source venv/bin/activate
    uv run --package auth python apps/auth/scripts/create_oauth2_client.py --name "My App" --redirect-uri "https://example.com/callback"

Examples:
    # Create a confidential client (with secret) for web apps
    uv run --package auth python apps/auth/scripts/create_oauth2_client.py \
        --name "Swagger API" \
        --redirect-uri "https://api.example.com/docs/oauth2-redirect" \
        --scopes openid,profile,email \
        --grant-types authorization_code,refresh_token

    # Create a public client (no secret) for SPAs with CORS origins
    uv run --package auth python apps/auth/scripts/create_oauth2_client.py \
        --name "SPA Frontend" \
        --redirect-uri "https://app.example.com/callback" \
        --allowed-origin "https://app.example.com" \
        --public

    # Create a client with client_credentials grant (machine-to-machine)
    uv run --package auth python apps/auth/scripts/create_oauth2_client.py \
        --name "Backend Service" \
        --redirect-uri "https://internal.example.com/callback" \
        --grant-types authorization_code,client_credentials,refresh_token

    # Create a Swagger UI client for an API
    uv run --package auth python apps/auth/scripts/create_oauth2_client.py \
        --name "Swagger fastapi-api" \
        --redirect-uri "https://api.example.com/docs/oauth2-redirect" \
        --allowed-origin "https://api.example.com" \
        --scopes openid,profile,email \
        --grant-types authorization_code,client_credentials,refresh_token \
        --no-consent
"""

import argparse
import asyncio
import json
import sys


async def create_client(
    name: str,
    redirect_uris: list[str],
    scopes: list[str],
    grant_types: list[str],
    is_public: bool,
    require_pkce: bool,
    require_consent: bool,
    description: str | None,
    allowed_origins: list[str] | None,
    output_json: bool,
) -> None:
    """Create a new OAuth2 client.

    Args:
        name: Client name.
        redirect_uris: List of allowed redirect URIs.
        scopes: List of allowed scopes.
        grant_types: List of allowed grant types.
        is_public: Whether this is a public client (no secret).
        require_pkce: Whether PKCE is required.
        require_consent: Whether user consent is required.
        description: Client description.
        allowed_origins: List of allowed CORS origins.
        output_json: Output as JSON.
    """
    from auth.core.database import async_session_factory
    from auth.services.oauth2_client import OAuth2ClientService

    service = OAuth2ClientService()

    async with async_session_factory() as db:
        client, client_secret = await service.create_client(
            db=db,
            name=name,
            redirect_uris=redirect_uris,
            allowed_scopes=scopes,
            allowed_grant_types=grant_types,
            is_confidential=not is_public,
            require_pkce=require_pkce,
            require_consent=require_consent,
            description=description,
            allowed_origins=allowed_origins,
        )
        await db.commit()

        if output_json:
            result = {
                "client_id": client.client_id,
                "client_secret": client_secret,
                "name": client.name,
                "redirect_uris": client.redirect_uris,
                "allowed_scopes": client.allowed_scopes,
                "allowed_grant_types": client.allowed_grant_types,
                "allowed_origins": client.allowed_origins,
                "is_confidential": client.is_confidential,
                "require_pkce": client.require_pkce,
                "require_consent": client.require_consent,
            }
            print(json.dumps(result, indent=2))
        else:
            print("\nOAuth2 Client created successfully!")
            print("=" * 50)
            print(f"  Name:            {client.name}")
            print(f"  Client ID:       {client.client_id}")
            if client_secret:
                print(f"  Client Secret:   {client_secret}")
                print()
                print("  WARNING: Save the client secret now!")
                print("           It cannot be retrieved later.")
            else:
                print("  Client Secret:   (none - public client)")
            print()
            print(f"  Redirect URIs:   {', '.join(client.redirect_uris)}")
            print(f"  Scopes:          {', '.join(client.allowed_scopes)}")
            print(f"  Grant Types:     {', '.join(client.allowed_grant_types)}")
            if client.allowed_origins:
                print(f"  CORS Origins:    {', '.join(client.allowed_origins)}")
            print(f"  Confidential:    {client.is_confidential}")
            print(f"  Require PKCE:    {client.require_pkce}")
            print(f"  Require Consent: {client.require_consent}")
            print("=" * 50)

            if "client_credentials" in client.allowed_grant_types:
                print()
                print("Client Credentials flow example:")
                print("  curl -X POST https://auth.example.com/oauth2/token \\")
                print("    -d 'grant_type=client_credentials' \\")
                print(f"    -d 'client_id={client.client_id}' \\")
                if client_secret:
                    print(f"    -d 'client_secret={client_secret}' \\")
                print("    -d 'scope=openid'")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create an OAuth2 client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --name "My App" --redirect-uri "https://example.com/callback"
  %(prog)s --name "SPA" --redirect-uri "https://app.com/cb" --public
  %(prog)s --name "API" --redirect-uri "https://api.com/docs/oauth2-redirect" --grant-types authorization_code,client_credentials
        """,
    )

    parser.add_argument(
        "--name",
        required=True,
        help="Client name (e.g., 'My Application')",
    )
    parser.add_argument(
        "--redirect-uri",
        action="append",
        dest="redirect_uris",
        required=True,
        help="Redirect URI (can be specified multiple times)",
    )
    parser.add_argument(
        "--scopes",
        default="openid,profile,email",
        help="Comma-separated list of allowed scopes (default: openid,profile,email)",
    )
    parser.add_argument(
        "--grant-types",
        default="authorization_code,refresh_token",
        help="Comma-separated list of allowed grant types (default: authorization_code,refresh_token)",
    )
    parser.add_argument(
        "--public",
        action="store_true",
        help="Create a public client (no client secret, for SPAs)",
    )
    parser.add_argument(
        "--no-pkce",
        action="store_true",
        help="Don't require PKCE (not recommended)",
    )
    parser.add_argument(
        "--no-consent",
        action="store_true",
        help="Don't require user consent (for trusted first-party apps)",
    )
    parser.add_argument(
        "--description",
        help="Client description",
    )
    parser.add_argument(
        "--allowed-origin",
        action="append",
        dest="allowed_origins",
        help="Allowed CORS origin (can be specified multiple times, e.g., https://app.example.com)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    args = parser.parse_args()

    # Parse comma-separated values
    scopes = [s.strip() for s in args.scopes.split(",") if s.strip()]
    grant_types = [g.strip() for g in args.grant_types.split(",") if g.strip()]

    # Validate grant types
    valid_grant_types = {
        "authorization_code",
        "refresh_token",
        "client_credentials",
        "urn:ietf:params:oauth:grant-type:device_code",
        "urn:ietf:params:oauth:grant-type:token-exchange",
    }
    for gt in grant_types:
        if gt not in valid_grant_types:
            print(f"Error: Invalid grant type '{gt}'")
            print(f"Valid grant types: {', '.join(sorted(valid_grant_types))}")
            sys.exit(1)

    # Validate scopes
    valid_scopes = {"openid", "profile", "email", "offline_access"}
    for scope in scopes:
        if scope not in valid_scopes:
            print(f"Error: Invalid scope '{scope}'")
            print(f"Valid scopes: {', '.join(sorted(valid_scopes))}")
            sys.exit(1)

    asyncio.run(
        create_client(
            name=args.name,
            redirect_uris=args.redirect_uris,
            scopes=scopes,
            grant_types=grant_types,
            is_public=args.public,
            require_pkce=not args.no_pkce,
            require_consent=not args.no_consent,
            description=args.description,
            allowed_origins=args.allowed_origins,
            output_json=args.json,
        )
    )


if __name__ == "__main__":
    main()
