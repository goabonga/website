# Command line interface

The package installs a `custom-domain` command (a Click group,
`custom_domain.cli:cli`) for the tasks that must happen before the API has
anyone to authorize: preparing a local database, loading the default nginx
template and registering the first clients. The commands talk to the database
directly, with `DATABASE_URL`, and do not need the API, Redis or Celery.

```bash
uv run --package custom-domain custom-domain --help
# or
uv run --package custom-domain python -m custom_domain.cli --help
```

## Commands

| Command | Description |
| --- | --- |
| `init-db` | Create the `domainstatus` enum and every table from the models. For local development only: it does not record an alembic revision, so use `alembic upgrade head` (data model page) on servers. |
| `seed` | Create the default nginx template (slug `default`, flagged as default and active) from the two files shipped in `custom_domain/templates`. Does nothing when a default template already exists. |
| `create-client` | Register an authorized client. |
| `list-clients` | List the clients with their status, upstream, CNAME and quota. |
| `list-templates` | List the nginx templates, marking the default one. |
| `sudoers --user <user>` | Print the sudoers rules that let the Celery worker run the privileged helper (nginx rendering page). |

`create-client` options:

| Option | Required | Description |
| --- | --- | --- |
| `--client-id` | yes | OAuth2 client identifier. |
| `--name` | yes | Display name. |
| `--description` | no | Free text. |
| `--upstream` | no | Default upstream socket or URL of the client's domains. |
| `--cname` | no | Default CNAME target. |
| `--max-domains` | no | Domain quota. |
| `--webhook-url` | no | `https://` URL that receives signed status notifications. |
| `--webhook-secret` | with the URL | HMAC secret, at least 32 characters. Prefer the environment variable `CUSTOM_DOMAIN_WEBHOOK_SECRET`, which keeps it out of the process list. |

Failures (a client that already exists, missing template files, a database
error) print a message on stderr and exit with status 1.

`sudoers` does not touch the database. It builds one rule per helper command from
the current settings (`NGINX_*`, `CERTBOT_*`, `PRIVILEGED_*`, ...), so run it
with the same environment as the worker; it prints the same lines as `python -m
custom_domain.services.privileged --user <user>`. When a setting is missing it
exits with status 1 and names the variable.

A typical bootstrap of a new environment:

```bash
export DATABASE_URL=postgresql://user:password@localhost/custom_domain
uv run --package custom-domain alembic -c apps/custom-domain/alembic.ini upgrade head
uv run --package custom-domain custom-domain seed
uv run --package custom-domain custom-domain create-client \
    --client-id my-app --name "My app" \
    --upstream /run/my-app.sock --cname apps.example.com
```

## Settings

The database commands only use `DATABASE_URL`; a plain `postgresql://` URL is
converted to the `asyncpg` driver, as in the API. `sudoers` reads the privileged
helper settings listed in the nginx rendering and SSL provisioning pages.

`init-db` creates the enum explicitly before `create_all`: the model declares
the enum with `create_type=False`, so `create_all` alone fails on an empty
database. That path is covered by a unit test with the SQLAlchemy calls
mocked; it has not been run against a live PostgreSQL server.

## How it is tested

- pytest: `test_cli.py` invokes every command through Click's test runner with
  the database layer mocked, covering success and failure paths, option parsing
  and the enum-then-tables order of `init-db`, and the `sudoers` command.
- behave: `features/cli.feature` runs the commands in-process on an in-memory
  database: seeding (and seeding twice), creating a client, creating the same
  client twice, listing clients and templates, listing an empty database and
  printing the sudoers rules.
