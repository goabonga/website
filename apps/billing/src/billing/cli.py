# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Administration command line: SaaS applications and client bindings.

``billing-admin`` talks to the database directly (``DATABASE_URL``), so it
works before any OAuth client can reach the API: it creates the first SaaS
application and binds the clients that will manage the others.

    billing-admin saas create --name "Example App" --slug example-app
    billing-admin saas list
    billing-admin client bind --saas example-app --client-id <oauth client id>
    billing-admin client unbind --saas example-app --client-id <oauth client id>
    billing-admin client list [--saas example-app] [--client-id <oauth client id>]

``--saas`` accepts the slug or the identifier of the application. Every
command prints JSON and exits with 0 on success, 1 when the request cannot be
satisfied (unknown application, duplicate slug, missing binding).
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Callable, Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from billing.database import async_session_factory
from billing.models import SaasApp, SaasClientBinding
from billing.schemas.saas_app import SaasAppCreate


class CliError(Exception):
    """A request that cannot be satisfied (reported on stderr, exit code 1)."""


def _saas_json(saas_app: SaasApp) -> dict[str, Any]:
    return {
        "id": saas_app.id,
        "slug": saas_app.slug,
        "name": saas_app.name,
        "is_active": saas_app.is_active,
        "webhook_url": saas_app.webhook_url,
        "checkout_url_allowlist": saas_app.checkout_url_allowlist,
    }


def _binding_json(binding: SaasClientBinding, slug: str | None = None) -> dict[str, Any]:
    return {
        "saas_id": binding.saas_app_id,
        "saas_slug": slug,
        "client_id": binding.client_id,
    }


async def find_saas(db: AsyncSession, reference: str) -> SaasApp:
    """Find a SaaS application by slug or by identifier."""
    for column in (SaasApp.slug, SaasApp.id):
        result = await db.execute(select(SaasApp).where(column == reference))
        saas_app = result.scalar_one_or_none()
        if saas_app:
            return saas_app
    raise CliError(f"SaaS app '{reference}' not found")


async def cmd_saas_create(db: AsyncSession, args: argparse.Namespace) -> Any:
    data = SaasAppCreate(
        name=args.name,
        slug=args.slug,
        description=args.description,
        webhook_url=args.webhook_url,
        checkout_url_allowlist=args.checkout_url or None,
    )
    existing = await db.execute(select(SaasApp).where(SaasApp.slug == data.slug))
    if existing.scalar_one_or_none():
        raise CliError(f"SaaS app with slug '{data.slug}' already exists")
    saas_app = SaasApp(
        name=data.name,
        slug=data.slug,
        description=data.description,
        webhook_url=data.webhook_url,
        checkout_url_allowlist=data.checkout_url_allowlist,
    )
    db.add(saas_app)
    await db.flush()
    await db.refresh(saas_app)
    return _saas_json(saas_app)


async def cmd_saas_list(db: AsyncSession, args: argparse.Namespace) -> Any:
    result = await db.execute(select(SaasApp).order_by(SaasApp.created_at, SaasApp.slug))
    return [_saas_json(saas_app) for saas_app in result.scalars().all()]


async def cmd_client_bind(db: AsyncSession, args: argparse.Namespace) -> Any:
    saas_app = await find_saas(db, args.saas)
    result = await db.execute(
        select(SaasClientBinding).where(
            SaasClientBinding.saas_app_id == saas_app.id,
            SaasClientBinding.client_id == args.client_id,
        )
    )
    binding = result.scalar_one_or_none()
    if not binding:
        binding = SaasClientBinding(saas_app_id=saas_app.id, client_id=args.client_id)
        db.add(binding)
        await db.flush()
    return _binding_json(binding, saas_app.slug)


async def cmd_client_unbind(db: AsyncSession, args: argparse.Namespace) -> Any:
    saas_app = await find_saas(db, args.saas)
    result = await db.execute(
        select(SaasClientBinding).where(
            SaasClientBinding.saas_app_id == saas_app.id,
            SaasClientBinding.client_id == args.client_id,
        )
    )
    binding = result.scalar_one_or_none()
    if not binding:
        raise CliError(f"Client '{args.client_id}' is not bound to '{saas_app.slug}'")
    await db.delete(binding)
    return _binding_json(binding, saas_app.slug)


async def cmd_client_list(db: AsyncSession, args: argparse.Namespace) -> Any:
    query = select(SaasClientBinding, SaasApp.slug).join(
        SaasApp, SaasApp.id == SaasClientBinding.saas_app_id
    )
    if args.saas:
        query = query.where(SaasClientBinding.saas_app_id == (await find_saas(db, args.saas)).id)
    if args.client_id:
        query = query.where(SaasClientBinding.client_id == args.client_id)
    result = await db.execute(query.order_by(SaasApp.slug, SaasClientBinding.client_id))
    return [_binding_json(binding, slug) for binding, slug in result.all()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="billing-admin", description="Manage SaaS applications and client bindings."
    )
    groups = parser.add_subparsers(dest="group", required=True)

    saas = groups.add_parser("saas", help="SaaS applications").add_subparsers(
        dest="action", required=True
    )
    create = saas.add_parser("create", help="create a SaaS application")
    create.add_argument("--name", required=True)
    create.add_argument("--slug", required=True)
    create.add_argument("--description")
    create.add_argument("--webhook-url")
    create.add_argument(
        "--checkout-url",
        action="append",
        help="allowed checkout redirect prefix, repeatable (checkout_url_allowlist)",
    )
    create.set_defaults(handler=cmd_saas_create)
    saas.add_parser("list", help="list SaaS applications").set_defaults(handler=cmd_saas_list)

    client = groups.add_parser("client", help="OAuth client bindings").add_subparsers(
        dest="action", required=True
    )
    for name, handler, help_text in (
        ("bind", cmd_client_bind, "allow a client to act on a SaaS application"),
        ("unbind", cmd_client_unbind, "remove the binding of a client"),
    ):
        sub = client.add_parser(name, help=help_text)
        sub.add_argument("--saas", required=True, help="slug or identifier")
        sub.add_argument("--client-id", required=True)
        sub.set_defaults(handler=handler)
    listing = client.add_parser("list", help="list the bindings")
    listing.add_argument("--saas", help="slug or identifier")
    listing.add_argument("--client-id")
    listing.set_defaults(handler=cmd_client_list)
    return parser


async def run(
    argv: Sequence[str],
    session_factory: Callable[[], AsyncSession] | None = None,
) -> Any:
    """Parse ``argv``, run the command in one transaction and return its result."""
    args = build_parser().parse_args(argv)
    factory = session_factory or async_session_factory
    async with factory() as db:
        try:
            result = await args.handler(db, args)
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    return result


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of ``billing-admin``."""
    try:
        result = asyncio.run(run(sys.argv[1:] if argv is None else argv))
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
