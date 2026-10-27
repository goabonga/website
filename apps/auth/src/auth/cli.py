# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""The ``auth`` command line: deployment commands to run after the database migrations.

    auth catalog sync [--file PATH] [--dry-run] [--json]

Every command is idempotent and safe to run at each deployment. ``--dry-run`` does all the
work in a transaction that is rolled back, so that the report shows what would change. With
``--json`` the report is a JSON document on the standard output, whose ``changed`` key tells
whether anything changed (what a configuration tool needs to report a change). Exit status:
0 on success, 2 for an unusable catalog or arguments, 1 for any other failure.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Sequence

from auth.config import settings
from auth.core.database import async_session_factory, close_database
from auth.services.catalog import CatalogError, SyncReport, load_catalog, sync_catalog

logger = logging.getLogger(__name__)


async def _in_transaction(work, *, dry_run: bool) -> SyncReport:
    """Run ``work(db)`` in one transaction: committed, or rolled back for a dry run."""
    try:
        async with async_session_factory() as db:
            try:
                report = await work(db)
            except Exception:
                await db.rollback()
                raise
            if dry_run:
                await db.rollback()
            else:
                await db.commit()
    finally:
        await close_database()
    return report


async def run_catalog_sync(path: str, *, dry_run: bool) -> SyncReport:
    """Synchronise the catalog file ``path`` with the database in one transaction."""
    catalog = load_catalog(path)
    return await _in_transaction(lambda db: sync_catalog(db, catalog), dry_run=dry_run)


def _print_report(report: SyncReport, *, as_json: bool, dry_run: bool, title: str) -> None:
    if as_json:
        print(json.dumps({**report.to_dict(), "dry_run": dry_run}, indent=2))
        return
    for line in report.lines(dry_run=dry_run):
        print(line)
    if not report.changed:
        print(f"{title}: nothing to change")
    else:
        verb = "would change" if dry_run else "changed"
        print(f"{title}: {verb} {len(report.created) + len(report.updated)} item(s)")


def build_parser() -> argparse.ArgumentParser:
    """The argument parser of the ``auth`` command."""
    parser = argparse.ArgumentParser(prog="auth", description="Deployment commands of auth.")
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")

    catalog = commands.add_parser("catalog", help="manage the catalog of scopes and roles")
    catalog_commands = catalog.add_subparsers(dest="catalog_command", required=True)
    sync = catalog_commands.add_parser(
        "sync",
        help="create the missing scopes and roles of the catalog, update their descriptions",
        description=(
            "Make the database match the catalog file: create the missing scopes and roles, "
            "update descriptions, add the listed scopes to roles and the listed allowances to "
            "existing clients. Nothing is ever deleted."
        ),
    )
    sync.add_argument(
        "--file",
        default=None,
        help="catalog file (default: the CATALOG_FILE setting)",
    )
    sync.add_argument("--dry-run", action="store_true", help="report the changes, apply none")
    sync.add_argument("--json", action="store_true", dest="as_json", help="print a JSON report")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of the ``auth`` command; returns the exit status."""
    args = build_parser().parse_args(argv)
    try:
        if args.command == "catalog" and args.catalog_command == "sync":
            path = args.file or settings.catalog_file
            if not path:
                print("auth: no catalog file: pass --file or set CATALOG_FILE", file=sys.stderr)
                return 2
            report = asyncio.run(run_catalog_sync(path, dry_run=args.dry_run))
            _print_report(report, as_json=args.as_json, dry_run=args.dry_run, title="catalog")
            return 0
    except CatalogError as exc:
        print(f"auth: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        logger.debug("command failed", exc_info=True)
        print(f"auth: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
