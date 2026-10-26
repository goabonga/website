# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Command line administration of Mailler.

Registers the clients (applications) and imports their email templates
straight into the database, for operators who deploy a new application and for
provisioning scripts. It uses the same settings (``DATABASE_URL``) and the same
validation as the API.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select

from mailler.database import get_sync_db
from mailler.models.client import AuthorizedClient
from mailler.models.template import EmailTemplate, TemplateStatus
from mailler.routes.templates import extract_variables
from mailler.schemas.client import ClientCreate, ClientUpdate
from mailler.schemas.template import TemplateCreate
from mailler.services import clients as client_service
from mailler.services.mjml import compile_mjml

# keys of the <slug>.json description of a template
DESCRIPTION_KEYS = {
    "name",
    "subject_template",
    "description",
    "plain_text",
    "variables",
    "metadata",
    "status",
}

SUCCESS = 0
FAILURE = 1
USAGE = 2


class CliError(Exception):
    """An error reported to the operator, with the exit code to use."""

    def __init__(self, message: str, code: int = FAILURE) -> None:
        super().__init__(message)
        self.code = code


# -- helpers -----------------------------------------------------------------


def _describe_validation_error(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in item['loc']) or 'value'}: {item['msg']}"
        for item in error.errors()
    )


def _parse_sender(value: str) -> dict:
    """Parse ``email`` or ``email=Display name`` into a sender identity."""
    email, _, name = value.partition("=")
    return {"email": email.strip(), "name": name.strip() or None}


def _client_as_dict(client: AuthorizedClient) -> dict:
    return {
        "client_id": client.client_id,
        "name": client.name,
        "is_active": client.is_active,
        "from_email": client.from_email,
        "from_name": client.from_name,
        "reply_to": client.reply_to,
        "allowed_senders": client.allowed_senders,
        "allowed_providers": client.allowed_providers,
        "default_provider": client.default_provider,
        "rate_limit_per_minute": client.rate_limit_per_minute,
        "daily_quota": client.daily_quota,
        "callback_url": client.callback_url,
        "has_callback_secret": client.has_callback_secret,
    }


def _client_options(args: argparse.Namespace) -> dict:
    """The fields of a client given on the command line (absent options are left out).

    An empty value (``--reply-to ""``) clears an optional field.
    """
    fields: dict = {}
    for option in ("name", "from_email", "from_name", "reply_to", "default_provider"):
        value = getattr(args, option)
        if value is not None:
            fields[option] = value or None
    if args.allowed_sender is not None:
        fields["allowed_senders"] = [_parse_sender(item) for item in args.allowed_sender if item]
    if args.allowed_provider is not None:
        fields["allowed_providers"] = [item for item in args.allowed_provider if item]
    for option in ("rate_limit_per_minute", "daily_quota"):
        value = getattr(args, option)
        if value is not None:
            fields[option] = value or None
    if args.callback_url is not None:
        fields["callback_url"] = args.callback_url or None
    if args.callback_secret_file is not None:
        secret_file = Path(args.callback_secret_file)
        try:
            fields["callback_secret"] = secret_file.read_text().strip() or None
        except OSError as error:
            raise CliError(f"Cannot read {secret_file}: {error.strerror}", USAGE) from error
    return fields


def _get_client(db, client_id: str) -> AuthorizedClient:
    client = db.execute(
        select(AuthorizedClient).where(AuthorizedClient.client_id == client_id)
    ).scalar_one_or_none()
    if client is None:
        raise CliError(f"Client '{client_id}' is not registered")
    return client


# -- clients -----------------------------------------------------------------


def cmd_clients_list(args: argparse.Namespace) -> int:
    with get_sync_db() as db:
        stmt = select(AuthorizedClient).order_by(AuthorizedClient.client_id.asc())
        if args.inactive:
            stmt = stmt.where(AuthorizedClient.is_active.is_(False))
        for client in db.execute(stmt).scalars():
            state = "active" if client.is_active else "inactive"
            print(
                "\t".join(
                    [
                        client.client_id,
                        state,
                        client.from_email or "-",
                        client.default_provider or "-",
                    ]
                )
            )
    return SUCCESS


def cmd_clients_show(args: argparse.Namespace) -> int:
    with get_sync_db() as db:
        print(json.dumps(_client_as_dict(_get_client(db, args.client_id)), indent=2))
    return SUCCESS


def cmd_clients_register(args: argparse.Namespace) -> int:
    try:
        data = ClientCreate(
            client_id=args.client_id, is_active=not args.inactive, **_client_options(args)
        )
    except ValidationError as error:
        raise CliError(_describe_validation_error(error), USAGE) from error

    with get_sync_db() as db:
        exists = db.execute(
            select(AuthorizedClient.id).where(AuthorizedClient.client_id == data.client_id)
        ).first()
        if exists:
            raise CliError(f"Client '{data.client_id}' is already registered")
        db.add(client_service.new_client(data))
        db.commit()
    print(f"Registered client '{data.client_id}'")
    return SUCCESS


def cmd_clients_update(args: argparse.Namespace) -> int:
    fields = _client_options(args)
    if not fields:
        raise CliError("Nothing to update: give at least one option", USAGE)
    try:
        update = ClientUpdate(**fields)
    except ValidationError as error:
        raise CliError(_describe_validation_error(error), USAGE) from error

    with get_sync_db() as db:
        client = _get_client(db, args.client_id)
        client_service.apply_update(client, update)
        try:
            client_service.validate_callback(client)
        except ValueError as error:
            db.rollback()
            raise CliError(str(error), USAGE) from error
        db.commit()
    print(f"Updated client '{args.client_id}'")
    return SUCCESS


def _set_active(args: argparse.Namespace, active: bool) -> int:
    with get_sync_db() as db:
        client = _get_client(db, args.client_id)
        client.is_active = active
        db.commit()
    print(f"Client '{args.client_id}' is now {'active' if active else 'inactive'}")
    return SUCCESS


def cmd_clients_activate(args: argparse.Namespace) -> int:
    return _set_active(args, True)


def cmd_clients_deactivate(args: argparse.Namespace) -> int:
    return _set_active(args, False)


# -- templates ---------------------------------------------------------------


def _load_template_files(directory: Path, default_status: str) -> list[tuple[TemplateCreate, str]]:
    """Read ``<slug>.mjml`` files and their ``<slug>.json`` descriptions.

    The description holds ``subject_template`` (required) and optionally
    ``name`` (the slug by default), ``description``, ``plain_text``,
    ``variables``, ``metadata`` and ``status`` (``--status`` by default).
    """
    sources = sorted(directory.glob("*.mjml"))
    if not sources:
        raise CliError(f"No .mjml file in {directory}")

    templates = []
    for source in sources:
        description_file = source.with_suffix(".json")
        if not description_file.exists():
            raise CliError(f"{source.name}: missing {description_file.name}")
        try:
            description = json.loads(description_file.read_text())
        except json.JSONDecodeError as error:
            raise CliError(f"{description_file.name}: invalid JSON ({error})") from error
        unknown = sorted(set(description) - DESCRIPTION_KEYS)
        if unknown:
            raise CliError(f"{description_file.name}: unknown key(s) {', '.join(unknown)}", USAGE)
        status = description.pop("status", default_status)
        if status not in {s.value for s in TemplateStatus}:
            raise CliError(f"{description_file.name}: unknown status '{status}'")
        try:
            template = TemplateCreate(
                slug=source.stem,
                name=description.pop("name", source.stem),
                mjml_source=source.read_text(),
                **description,
            )
        except (ValidationError, TypeError) as error:
            detail = (
                _describe_validation_error(error) if isinstance(error, ValidationError) else error
            )
            raise CliError(f"{description_file.name}: {detail}", USAGE) from error
        templates.append((template, status))
    return templates


def cmd_templates_import(args: argparse.Namespace) -> int:
    templates = _load_template_files(Path(args.directory), args.status)

    # Compile everything first: nothing is written when one template is invalid
    compiled = {}
    for template, _ in templates:
        result = asyncio.run(compile_mjml(template.mjml_source))
        if result.get("errors"):
            raise CliError(f"{template.slug}: MJML compilation failed: {result['errors']}")
        compiled[template.slug] = result["html"]

    created = updated = 0
    with get_sync_db() as db:
        for template, status in templates:
            variables = template.variables
            if variables is None:
                variables = extract_variables(template.mjml_source, template.subject_template)
            existing = db.execute(
                select(EmailTemplate).where(
                    EmailTemplate.client_id == args.client_id, EmailTemplate.slug == template.slug
                )
            ).scalar_one_or_none()
            if existing is None:
                existing = EmailTemplate(client_id=args.client_id, slug=template.slug)
                db.add(existing)
                created += 1
            else:
                updated += 1
            existing.name = template.name
            existing.description = template.description
            existing.subject_template = template.subject_template
            existing.mjml_source = template.mjml_source
            existing.html_compiled = compiled[template.slug]
            existing.plain_text = template.plain_text
            existing.variables = variables
            existing.metadata_ = template.metadata or {}
            existing.status = status
        if args.dry_run:
            db.rollback()
        else:
            db.commit()

    prefix = "Would import" if args.dry_run else "Imported"
    print(
        f"{prefix} {len(templates)} template(s) for '{args.client_id}': {created} new, {updated} updated"
    )
    return SUCCESS


def cmd_templates_list(args: argparse.Namespace) -> int:
    with get_sync_db() as db:
        stmt = (
            select(EmailTemplate)
            .where(EmailTemplate.client_id == args.client_id)
            .order_by(EmailTemplate.slug.asc())
        )
        for template in db.execute(stmt).scalars():
            print("\t".join([template.slug, template.status, template.name]))
    return SUCCESS


# -- parser ------------------------------------------------------------------


def _add_client_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--name", help="display name of the application")
    parser.add_argument("--from-email", help="default sender address")
    parser.add_argument("--from-name", help="default sender name")
    parser.add_argument("--reply-to", help="reply-to address that emails must use")
    parser.add_argument(
        "--allowed-sender",
        action="append",
        metavar="EMAIL[=NAME]",
        help="other sender identity the client may use (repeatable)",
    )
    parser.add_argument(
        "--allowed-provider",
        action="append",
        metavar="PROVIDER",
        help="provider the client may use (repeatable)",
    )
    parser.add_argument("--default-provider", help="provider used when a request names none")
    parser.add_argument("--rate-limit-per-minute", type=int, help="emails per minute (0 removes)")
    parser.add_argument("--daily-quota", type=int, help="emails per UTC day (0 removes)")
    parser.add_argument(
        "--callback-url", help="URL notified of the status of the emails (empty removes)"
    )
    parser.add_argument(
        "--callback-secret-file",
        metavar="FILE",
        help="file holding the secret that signs the notifications (an empty file removes it)",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser of the ``mailler`` command."""
    parser = argparse.ArgumentParser(prog="mailler", description="Administer Mailler.")
    groups = parser.add_subparsers(dest="group", required=True)

    clients = groups.add_parser("clients", help="manage the authorized clients").add_subparsers(
        dest="command", required=True
    )
    command = clients.add_parser("list", help="list the clients")
    command.add_argument("--inactive", action="store_true", help="only the inactive clients")
    command.set_defaults(handler=cmd_clients_list)

    command = clients.add_parser("show", help="show a client as JSON")
    command.add_argument("client_id")
    command.set_defaults(handler=cmd_clients_show)

    command = clients.add_parser("register", help="register a client")
    command.add_argument("client_id", help="OAuth2 client the tokens of the application belong to")
    command.add_argument("--inactive", action="store_true", help="register it deactivated")
    _add_client_options(command)
    command.set_defaults(handler=cmd_clients_register)

    command = clients.add_parser("update", help="change a client (only the given options)")
    command.add_argument("client_id")
    _add_client_options(command)
    command.set_defaults(handler=cmd_clients_update)

    for name, handler in (
        ("activate", cmd_clients_activate),
        ("deactivate", cmd_clients_deactivate),
    ):
        command = clients.add_parser(name, help=f"{name} a client")
        command.add_argument("client_id")
        command.set_defaults(handler=handler)

    templates = groups.add_parser(
        "templates", help="manage the templates of a client"
    ).add_subparsers(dest="command", required=True)
    command = templates.add_parser(
        "import",
        help="import <slug>.mjml / <slug>.json files of a directory as templates of a client",
    )
    command.add_argument("--client-id", required=True, help="client that owns the templates")
    command.add_argument("directory", help="directory with the .mjml and .json files")
    command.add_argument(
        "--status",
        default=TemplateStatus.ACTIVE.value,
        choices=[s.value for s in TemplateStatus],
        help="status of the templates whose description has none (default: active)",
    )
    command.add_argument(
        "--dry-run", action="store_true", help="validate and compile, write nothing"
    )
    command.set_defaults(handler=cmd_templates_import)

    command = templates.add_parser("list", help="list the templates of a client")
    command.add_argument("--client-id", required=True)
    command.set_defaults(handler=cmd_templates_list)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line; returns the exit code."""
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except CliError as error:
        print(f"error: {error}", file=sys.stderr)
        return error.code


if __name__ == "__main__":
    sys.exit(main())
