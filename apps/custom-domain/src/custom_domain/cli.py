# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""CLI commands for custom-domain service."""

import asyncio
import sys
from pathlib import Path

import click
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from custom_domain.config import settings
from custom_domain.models import AuthorizedClient, Base, DomainStatus, NginxTemplate


def get_async_url() -> str:
    """Convert PostgreSQL URL to async format (asyncpg)."""
    url = settings.database_url
    return url.replace("postgresql://", "postgresql+asyncpg://").replace(
        "postgresql:///", "postgresql+asyncpg:///"
    )


async def get_session() -> AsyncSession:
    """Create an async database session."""
    engine = create_async_engine(get_async_url())
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return async_session()


def _check_upstream(value: str | None) -> str | None:
    """Click callback: reject an upstream that is neither a socket path nor host:port."""
    from custom_domain.services.upstream import InvalidUpstreamError, parse_upstream

    if value is None:
        return value
    try:
        parse_upstream(value)
    except InvalidUpstreamError as error:
        raise click.BadParameter(str(error)) from error
    return value.strip()


@click.group()
def cli():
    """Custom Domain Service CLI."""
    pass


@cli.command()
@click.option("--user", required=True, help="System user that runs the Celery worker")
def sudoers(user: str):
    """Print the sudoers rules that allow the worker to run the privileged helper.

    The rules are built from the current settings, so run this with the same
    environment as the worker.
    """
    from custom_domain.config import ConfigurationError
    from custom_domain.services.privileged import sudoers_lines

    try:
        lines = sudoers_lines(user)
    except ConfigurationError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    for line in lines:
        click.echo(line)


@cli.command("init-db")
def init_db():
    """Create all database tables (for local development)."""
    asyncio.run(_init_db())


def _create_schema(connection) -> None:
    """Create the domainstatus enum and then every table.

    ``create_all`` does not create the PostgreSQL enum type used by the domains table
    (the model declares ``create_type=False``), so it is created explicitly first.
    """
    postgresql.ENUM(*(status.value for status in DomainStatus), name="domainstatus").create(
        connection, checkfirst=True
    )
    Base.metadata.create_all(connection)


async def _init_db():
    """Create all database tables."""
    engine = create_async_engine(get_async_url())

    async with engine.begin() as conn:
        await conn.run_sync(_create_schema)

    await engine.dispose()
    click.echo("Database tables created successfully")


@cli.command()
def seed():
    """Seed the database with initial data."""
    asyncio.run(_seed())


async def _seed():
    """Seed database with default templates and optionally a client."""
    session = await get_session()

    try:
        # Check if default template exists
        result = await session.execute(
            select(NginxTemplate).where(NginxTemplate.is_default == True)  # noqa: E712
        )
        existing_default = result.scalar_one_or_none()

        if existing_default:
            click.echo(f"Default template already exists: {existing_default.name}")
        else:
            # Load templates from files
            templates_dir = Path(__file__).parent / "templates"

            http_template_path = templates_dir / "nginx_http.conf.j2"
            https_template_path = templates_dir / "nginx_https.conf.j2"

            if not http_template_path.exists() or not https_template_path.exists():
                click.echo("Error: Template files not found", err=True)
                sys.exit(1)

            http_template = http_template_path.read_text()
            https_template = https_template_path.read_text()

            template = NginxTemplate(
                slug="default",
                name="Default Template",
                description="Default nginx template with standard proxy configuration",
                http_template=http_template,
                https_template=https_template,
                is_default=True,
                is_active=True,
            )

            session.add(template)
            await session.commit()
            click.echo("Created default nginx template")

        click.echo("Seed completed successfully")

    except Exception as e:
        click.echo(f"Error seeding database: {e}", err=True)
        sys.exit(1)
    finally:
        await session.close()


@cli.command()
@click.option("--client-id", required=True, help="OAuth2 client ID")
@click.option("--name", required=True, help="Client display name")
@click.option("--description", default=None, help="Client description")
@click.option(
    "--upstream",
    default=None,
    callback=lambda _ctx, _param, value: _check_upstream(value),
    help="Default upstream: absolute socket path or host:port",
)
@click.option("--cname", default=None, help="Default CNAME target")
@click.option("--max-domains", default=None, type=int, help="Maximum domains allowed")
def create_client(
    client_id: str,
    name: str,
    description: str,
    upstream: str,
    cname: str,
    max_domains: int,
):
    """Create a new authorized client."""
    asyncio.run(_create_client(client_id, name, description, upstream, cname, max_domains))


async def _create_client(
    client_id: str,
    name: str,
    description: str,
    upstream: str,
    cname: str,
    max_domains: int,
):
    """Create a new authorized client."""
    session = await get_session()

    try:
        # Check if client already exists
        result = await session.execute(
            select(AuthorizedClient).where(AuthorizedClient.client_id == client_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            click.echo(f"Client already exists: {client_id}", err=True)
            sys.exit(1)

        client = AuthorizedClient(
            client_id=client_id,
            name=name,
            description=description,
            default_upstream_target=upstream,
            default_cname_target=cname,
            max_domains=max_domains,
            is_active=True,
        )

        session.add(client)
        await session.commit()
        click.echo(f"Created client: {client_id} (ID: {client.id})")

    except Exception as e:
        click.echo(f"Error creating client: {e}", err=True)
        sys.exit(1)
    finally:
        await session.close()


@cli.command()
def list_clients():
    """List all authorized clients."""
    asyncio.run(_list_clients())


async def _list_clients():
    """List all authorized clients."""
    session = await get_session()

    try:
        result = await session.execute(select(AuthorizedClient).order_by(AuthorizedClient.name))
        clients = result.scalars().all()

        if not clients:
            click.echo("No clients found")
            return

        click.echo("\nAuthorized Clients:")
        click.echo("-" * 60)
        for client in clients:
            status = "active" if client.is_active else "inactive"
            click.echo(f"  {client.client_id} ({client.name}) - {status}")
            if client.default_upstream_target:
                click.echo(f"    Upstream: {client.default_upstream_target}")
            if client.default_cname_target:
                click.echo(f"    CNAME: {client.default_cname_target}")
            if client.max_domains:
                click.echo(f"    Max domains: {client.max_domains}")
        click.echo()

    except Exception as e:
        click.echo(f"Error listing clients: {e}", err=True)
        sys.exit(1)
    finally:
        await session.close()


@cli.command()
def list_templates():
    """List all nginx templates."""
    asyncio.run(_list_templates())


async def _list_templates():
    """List all nginx templates."""
    session = await get_session()

    try:
        result = await session.execute(select(NginxTemplate).order_by(NginxTemplate.name))
        templates = result.scalars().all()

        if not templates:
            click.echo("No templates found")
            return

        click.echo("\nNginx Templates:")
        click.echo("-" * 60)
        for template in templates:
            default = " (DEFAULT)" if template.is_default else ""
            status = "active" if template.is_active else "inactive"
            click.echo(f"  {template.name}{default} - {status}")
            if template.description:
                click.echo(f"    {template.description}")
        click.echo()

    except Exception as e:
        click.echo(f"Error listing templates: {e}", err=True)
        sys.exit(1)
    finally:
        await session.close()


if __name__ == "__main__":
    cli()
